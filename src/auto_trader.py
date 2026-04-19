"""
auto_trader.py v1.0
模拟盘自动交易 + 三层风控
流程: 新闻融合信号 → 风控过滤 → 仓位计算 → IB下单(dry_run)
"""
import logging
import time
import psycopg2
import psycopg2.extras
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.strategy_engine import StrategyEngine
from src.news_fusion import scan_with_news
from src.position_sizer import PositionSizer
from src.data_loader import filter_by_volume, get_russell2000_tickers

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

DB_URL = "host=192.168.0.18 port=5432 dbname=quantforce user=postgres password=newpassword123"

# ── 风控参数 ──────────────────────────────────────────────
RISK_CONFIG = {
    "max_positions":      5,      # 最多同时持仓
    "max_single_pct":     0.10,   # 单只最大仓位10%
    "min_confidence":     0.58,   # 最低信号置信度
    "min_vol_ratio":      1.2,    # 最低量比
    "max_rsi":            75,     # RSI超买上限
    "min_rsi":            25,     # RSI超卖下限（空头）
    "min_price":          5.0,    # 最低股价过滤垃圾股
    "max_daily_trades":   10,     # 每日最大交易次数
    "dry_run":            True,   # 模拟盘开关
    "account_balance":    100000, # 模拟账户资金
}

# ── 交易时间检查 ──────────────────────────────────────────
def is_market_open() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    market_open  = now.replace(hour=9,  minute=35, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=45, second=0, microsecond=0)
    return market_open <= now <= market_close

# ── 风控层1: 信号质量过滤 ────────────────────────────────
def risk_layer1_signal(signal: dict) -> tuple[bool, str]:
    """信号质量检查"""
    if signal["final_score"] < RISK_CONFIG["min_confidence"]:
        return False, f"置信度不足({signal['final_score']:.3f}<{RISK_CONFIG['min_confidence']})"
    if signal["vol_ratio"] < RISK_CONFIG["min_vol_ratio"] and signal["vol_ratio"] > 0:
        return False, f"量比不足({signal['vol_ratio']:.2f}<{RISK_CONFIG['min_vol_ratio']})"
    rsi = signal.get("rsi", 50)
    if rsi > RISK_CONFIG["max_rsi"]:
        return False, f"RSI超买({rsi:.0f}>{RISK_CONFIG['max_rsi']})"
    if rsi < RISK_CONFIG["min_rsi"]:
        return False, f"RSI超卖({rsi:.0f}<{RISK_CONFIG['min_rsi']})"
    return True, "L1通过"

# ── 风控层2: 持仓/频率控制 ───────────────────────────────
def risk_layer2_position(ticker: str, conn) -> tuple[bool, str]:
    """持仓数量和今日交易次数检查"""
    try:
        with conn.cursor() as cur:
            # 当前持仓数
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM executions
                WHERE status='filled' AND created_at > NOW() - INTERVAL '1 day'
            """)
            positions = cur.fetchone()[0] or 0
            if positions >= RISK_CONFIG["max_positions"]:
                return False, f"持仓已满({positions}/{RISK_CONFIG['max_positions']})"

            # 今日交易次数
            cur.execute("""
                SELECT COUNT(*) FROM executions
                WHERE created_at > NOW() - INTERVAL '1 day'
            """)
            daily_trades = cur.fetchone()[0] or 0
            if daily_trades >= RISK_CONFIG["max_daily_trades"]:
                return False, f"今日交易次数已满({daily_trades})"

            # 该股票是否已有持仓
            cur.execute("""
                SELECT COUNT(*) FROM executions
                WHERE symbol=%s AND status='filled'
                AND created_at > NOW() - INTERVAL '1 day'
            """, (ticker,))
            existing = cur.fetchone()[0] or 0
            if existing > 0:
                return False, f"{ticker}今日已有持仓"

    except Exception as e:
        log.warning(f"L2风控查询失败: {e}")
    return True, "L2通过"

# ── 风控层3: 仓位计算 ────────────────────────────────────
def risk_layer3_sizing(signal: dict, sizer: PositionSizer) -> tuple[bool, str, dict]:
    """Kelly + ATR仓位计算"""
    price = signal.get("take_profit", 0)  # 用TP作为目标价
    entry = signal.get("stop_loss", 0)

    # 从signal反推entry price（SL和TP之间）
    sl = signal["stop_loss"]
    tp = signal["take_profit"]
    if sl == 0 or tp == 0:
        return False, "止损/止盈未设置", {}

    # 估算entry（SL和TP之间，偏SL侧）
    entry_price = sl + (tp - sl) * 0.25
    if entry_price <= RISK_CONFIG["min_price"]:
        return False, f"股价过低({entry_price:.2f})", {}

    vol = signal.get("bb_width", 0.02)  # 用BB宽度作为波动率代理
    sizing = sizer.calculate_size(
        entry_price=entry_price,
        stop_loss=sl,
        volatility=vol,
        win_rate=0.55,
        payoff_ratio=abs(tp - entry_price) / max(abs(entry_price - sl), 0.01)
    )

    pos_pct = (sizing["quantity"] * entry_price) / RISK_CONFIG["account_balance"]
    if pos_pct > RISK_CONFIG["max_single_pct"]:
        sizing["quantity"] = int(
            RISK_CONFIG["account_balance"] * RISK_CONFIG["max_single_pct"] / entry_price
        )

    if sizing["quantity"] < 1:
        return False, "仓位计算为0股", {}

    return True, "L3通过", {**sizing, "entry_price": round(entry_price, 2)}

# ── 模拟下单 ─────────────────────────────────────────────
def place_order(signal: dict, sizing: dict, conn, dry_run: bool = True) -> dict:
    """写入executions表（dry_run模式）"""
    order = {
        "execution_id": str(uuid.uuid4()),
        "symbol":       signal["ticker"],
        "action":       signal["action"],
        "quantity":     sizing["quantity"],
        "entry_price":  sizing["entry_price"],
        "stop_loss":    signal["stop_loss"],
        "take_profit":  signal["take_profit"],
        "confidence":   signal["final_score"],
        "dry_run":      dry_run,
        "status":       "dry_run" if dry_run else "pending",
        "reason":       signal["reason"][:200],
    }

    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO executions
                (execution_id, symbol, action, quantity, fill_price,
                 stop_loss, take_profit, confidence, status, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """, (
                order["execution_id"], order["symbol"], order["action"],
                order["quantity"], order["entry_price"],
                order["stop_loss"], order["take_profit"],
                order["confidence"], order["status"]
            ))
        conn.commit()
        log.info(f"{'[DRY]' if dry_run else '[LIVE]'} {order['action']} {order['symbol']} "
                 f"x{order['quantity']}股 @{order['entry_price']:.2f} "
                 f"SL={order['stop_loss']:.2f} TP={order['take_profit']:.2f} "
                 f"confidence={order['confidence']:.3f}")
    except Exception as e:
        log.error(f"下单写入失败: {e}")
        conn.rollback()

    return order

# ── 主扫描循环 ────────────────────────────────────────────
def run_auto_trader(tickers: list = None, dry_run: bool = True):
    engine = StrategyEngine()
    sizer  = PositionSizer(
        account_balance=RISK_CONFIG["account_balance"],
        max_risk_pct=0.02
    )

    if tickers is None:
        raw = get_russell2000_tickers()
        tickers = filter_by_volume(raw[:200], top_n=50)

    log.info(f"AutoTrader启动 | 股票池:{len(tickers)}只 | dry_run={dry_run}")

    while True:
        if not is_market_open():
            now = datetime.now(ET)
            log.info(f"非交易时间 {now.strftime('%H:%M ET')} | 等待300s...")
            time.sleep(300)
            continue

        log.info("=== 开始扫描 ===")
        try:
            conn = psycopg2.connect(DB_URL)
            signals = scan_with_news(tickers, engine)
            buy_signals = [s for s in signals if s["action"] == "BUY"]
            log.info(f"BUY信号: {len(buy_signals)}只")

            for sig in buy_signals:
                ticker = sig["ticker"]
                # L1: 信号质量
                ok, msg = risk_layer1_signal(sig)
                if not ok:
                    log.info(f"  {ticker} L1拒绝: {msg}")
                    continue
                # L2: 持仓频率
                ok, msg = risk_layer2_position(ticker, conn)
                if not ok:
                    log.info(f"  {ticker} L2拒绝: {msg}")
                    continue
                # L3: 仓位计算
                ok, msg, sizing = risk_layer3_sizing(sig, sizer)
                if not ok:
                    log.info(f"  {ticker} L3拒绝: {msg}")
                    continue

                # 下单
                order = place_order(sig, sizing, conn, dry_run=dry_run)
                log.info(f"  ✅ {ticker} 下单成功: {order['status']}")

            conn.close()
        except Exception as e:
            log.error(f"扫描异常: {e}")

        log.info("等待300s下一轮...")
        time.sleep(300)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    # 快速测试：用5只股票
    tickers = ["TSLA", "NVDA", "AAPL", "AMZN", "PLTR"]
    run_auto_trader(tickers=tickers, dry_run=RISK_CONFIG["dry_run"])
