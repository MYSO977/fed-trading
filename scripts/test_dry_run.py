#!/usr/bin/env python3
"""Fed-Trading 2.0 · Dry-Run 验证脚本（兼容版）"""
import sys, os, logging, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ========== 安全导入（带降级）==========
try:
    from src.data_loader import fetch_realtime_prompt, load_real_market_data
    _HAS_DATA_LOADER = True
    logging.info("✅ 已加载完整 data_loader")
except ImportError as e:
    _HAS_DATA_LOADER = False
    logging.warning(f"⚠️ data_loader 导入失败: {e}，启用本地兜底")

try:
    from src.notifier import get_notifier
    _HAS_NOTIFIER = True
except ImportError:
    _HAS_NOTIFIER = False
    logging.warning("⚠️ notifier 未加载，通知功能已禁用")

# ========== 兜底数据生成器 ==========
def _fallback_prompt(symbol):
    """本地高保真兜底，格式与训练数据 100% 一致"""
    price = random.uniform(100, 900)
    ma5 = price * random.uniform(0.98, 1.02)
    ma20 = price * random.uniform(0.95, 1.05)
    vr = random.uniform(0.8, 2.5)
    return f"Asset:{symbol}|Price:{price:.2f}|MA5/20:{ma5:.2f}/{ma20:.2f}|VolRatio:{vr:.1f}x|Node:rt|Action:"

# ========== 核心验证逻辑 ==========
def test_dry_run(symbols=["TSLA", "NVDA"], dry_run=True):
    logging.info("🧪 开始 Dry-Run 验证 (安全模式: %s)", "✅ 开启" if dry_run else "❌ 关闭")
    
    notifier = get_notifier() if _HAS_NOTIFIER else None
    
    for sym in symbols:
        logging.info("📡 拉取 %s 实时行情...", sym)
        
        # 尝试真实拉取，失败则用兜底
        if _HAS_DATA_LOADER:
            try:
                prompt = fetch_realtime_prompt(sym)
            except:
                prompt = None
        else:
            prompt = None
        
        if not prompt:
            logging.warning("⚠️ %s 拉取失败，启用本地兜底", sym)
            prompt = _fallback_prompt(sym)
        
        logging.info("🧠 推理输入: %s", prompt[:80] + "...")
        
        # 🔹 模拟推理逻辑（替换为真实 predict）
        # 规则: 价格 > MA20 且 量比 > 1.2 = BUY
        parts = dict(p.split(":") for p in prompt.split("|") if ":" in p)
        try:
            price = float(parts.get("Price", "0"))
            ma20 = float(parts.get("MA5/20", "0/0").split("/")[1])
            vr = float(parts.get("VolRatio", "1.0").replace("x", ""))
            action = "BUY" if price > ma20 and vr > 1.2 else "SELL" if price < ma20 and vr > 1.2 else "HOLD"
        except:
            action = "HOLD"
        
        logging.info("📤 信号: [%s] %s", sym, action)
        
        # 🔹 推送通知（若启用）
        if notifier and notifier.enabled and action in ["BUY", "SELL"]:
            try:
                notifier.send_trade_signal(sym, action, price, vr, dry_run=dry_run)
                logging.info("📱 通知已推送")
            except Exception as e:
                logging.warning("⚠️ 通知发送失败: %s", e)
        
        # 🔹 Dry-Run 拦截确认
        if dry_run:
            logging.info("✅ [DRY-RUN] 订单已安全拦截，未真实下单")
        else:
            logging.info("⚠️ [LIVE] 订单将真实执行（谨慎！）")
        
        print("-" * 60)
    
    logging.info("🎉 Dry-Run 验证完成")

if __name__ == "__main__":
    test_dry_run()
