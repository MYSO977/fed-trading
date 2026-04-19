"""
news_fusion.py
新闻加分模块 - 从signals_raw读取news信号，叠加strategy_engine技术评分
"""
import logging
import psycopg2
import psycopg2.extras
import pandas as pd
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

DB_URL = "host=192.168.0.18 port=5432 dbname=quantforce user=postgres password=newpassword123"

# 权重配置
WEIGHT_TECH   = 0.65  # 技术评分权重
WEIGHT_NEWS   = 0.35  # 新闻评分权重
NEWS_DECAY_H  = 6     # 新闻信号衰减小时数（超过则降权）

def get_news_scores(tickers: list, hours: int = 24) -> dict:
    """
    从signals_raw拉取最近N小时的news信号
    返回 {ticker: news_score(0-1)}
    """
    if not tickers:
        return {}
    try:
        conn = psycopg2.connect(DB_URL)
        placeholders = ",".join(["%s"] * len(tickers))
        sql = f"""
            SELECT symbol, score, created_at
            FROM signals_raw
            WHERE signal_type = 'news'
              AND symbol IN ({placeholders})
              AND created_at > NOW() - INTERVAL '{hours} hours'
              AND status = 'pending'
            ORDER BY created_at DESC
        """
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, tickers)
            rows = cur.fetchall()
        conn.close()

        # 每个ticker取最高分，并做时间衰减
        scores = {}
        now = datetime.utcnow()
        for row in rows:
            sym = row["symbol"]
            raw_score = float(row["score"]) / 10.0  # 归一化到0-1
            # 时间衰减：超过NEWS_DECAY_H小时线性降权
            age_h = (now - row["created_at"].replace(tzinfo=None)).total_seconds() / 3600
            decay = max(0.3, 1.0 - (age_h / NEWS_DECAY_H) * 0.7)
            adjusted = raw_score * decay
            if sym not in scores or adjusted > scores[sym]:
                scores[sym] = round(adjusted, 3)

        log.info(f"新闻信号: {len(scores)}只有效 | 样本: {dict(list(scores.items())[:5])}")
        return scores

    except Exception as e:
        log.warning(f"news_scores拉取失败: {e}")
        return {}


def fuse_signal(ticker: str, tech_score: float, tech_signal: dict,
                news_scores: dict = None) -> dict:
    """
    融合技术评分 + 新闻评分
    tech_score: strategy_engine的confidence(0-1)
    tech_signal: strategy_engine.get_signal()的完整返回
    news_scores: {ticker: score(0-1)}，可预先批量拉取
    """
    news_score = 0.0
    news_boost = False

    if news_scores and ticker in news_scores:
        news_score = news_scores[ticker]
        news_boost = True

    # 加权融合
    if news_boost:
        final_score = tech_score * WEIGHT_TECH + news_score * WEIGHT_NEWS
    else:
        final_score = tech_score  # 无新闻时纯技术

    final_score = round(min(final_score, 1.0), 3)

    # 重新判断action
    min_conf = 0.55
    if final_score >= min_conf:
        action = "BUY"
    elif final_score <= 0.25:
        action = "SELL"
    else:
        action = "HOLD"

    # 新闻加分提升止盈（新闻利好时激进一点）
    tp = tech_signal.get("take_profit", 0)
    sl = tech_signal.get("stop_loss", 0)
    if news_boost and news_score > 0.7 and action == "BUY":
        atr = tech_signal.get("atr", 0)
        tp = tp  # 保持原止盈，可扩展

    return {
        "ticker":       ticker,
        "action":       action,
        "final_score":  final_score,
        "tech_score":   round(tech_score, 3),
        "news_score":   round(news_score, 3),
        "news_boost":   news_boost,
        "stop_loss":    sl,
        "take_profit":  tp,
        "rsi":          tech_signal.get("rsi", 0),
        "macd_hist":    tech_signal.get("macd_hist", 0),
        "vol_ratio":    tech_signal.get("vol_ratio", 0),
        "reason":       tech_signal.get("reason", "") +
                        (f" | 新闻加分+{news_score:.2f}" if news_boost else " | 无新闻信号"),
    }


def scan_with_news(tickers: list, engine) -> list:
    """
    批量扫描：技术信号 + 新闻加分
    engine: StrategyEngine实例
    返回按final_score排序的信号列表
    """
    from src.data_loader import fetch_ohlcv

    # 批量拉新闻分
    news_scores = get_news_scores(tickers)
    results = []

    for ticker in tickers:
        try:
            df = fetch_ohlcv(ticker, period="60d")
            if df.empty or len(df) < 30:
                continue
            df = engine.compute_features(df)
            if df.empty:
                continue
            tech_signal = engine.get_signal(df.iloc[-1])
            fused = fuse_signal(ticker, tech_signal["confidence"],
                               tech_signal, news_scores)
            results.append(fused)
        except Exception as e:
            log.warning(f"{ticker} 扫描失败: {e}")
            continue

    # 按final_score排序
    results.sort(key=lambda x: x["final_score"], reverse=True)
    log.info(f"融合扫描完成: {len(results)}只 | BUY: {sum(1 for r in results if r['action']=='BUY')}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from src.strategy_engine import StrategyEngine

    engine = StrategyEngine()
    tickers = ["TSLA", "NVDA", "AAPL", "AMZN", "PLTR"]

    print("=== 新闻融合测试 ===")
    results = scan_with_news(tickers, engine)
    for r in results[:5]:
        print(f"  {r['ticker']:6s} {r['action']:4s} "
              f"final={r['final_score']:.3f} "
              f"tech={r['tech_score']:.3f} "
              f"news={r['news_score']:.3f} "
              f"{'📰+' if r['news_boost'] else '  '} "
              f"{r['reason'][:60]}")
