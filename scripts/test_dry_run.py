#!/usr/bin/env python3
import sys, os, logging, random; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
from src.data_loader import fetch_realtime_prompt; from src.inference import predict; from src.notifier import get_notifier
def test_dry_run(symbols=["TSLA","NVDA"], dry_run=True):
    logging.info("🧪 开始 Dry-Run 验证 (安全模式: %s)", "✅ 开启" if dry_run else "❌ 关闭")
    notifier = get_notifier()
    for sym in symbols:
        prompt = fetch_realtime_prompt(sym) or f"Asset:{sym}|Price:{random.uniform(100,900):.2f}|MA5/20:400/420|VolRatio:1.5x|Node:rt|Action:"
        result = predict(prompt); logging.info(f"📤 [{sym}] {result['action']}")
        if notifier and notifier.enabled and result['action'] in ["BUY","SELL"]: notifier.send_trade_signal(sym, result['action'], 245.3, 1.5, dry_run)
        if dry_run: logging.info("✅ [DRY-RUN] 订单已安全拦截")
    logging.info("🎉 Dry-Run 验证完成")
if __name__ == "__main__": test_dry_run()