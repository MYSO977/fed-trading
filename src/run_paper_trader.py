import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ib_connector import IBTrader

def run_cycle(dry_run=True):
    t = IBTrader(port=4002, paper=True)
    if not t.connect(): return
    print(f"\n🔄 开始交易循环 [{'安全模拟' if dry_run else '⚠️实盘'}]\n")
    for sym in ["TSLA","NVDA","AAPL"]:
        p = t.fetch_market_prompt(sym, duration='3 D', bar_size='1 hour')
        if not p: print(f"⚠️ {sym} 数据不足"); continue
        # 🔹 临时模拟信号（验证链路），实际使用时替换为: from inference import predict; signal = predict(p)
        signal = "BUY" if sym == "TSLA" else "HOLD"
        print(f"🧠 {sym}: {signal}")
        print(f"📦 {t.parse_and_place_order(sym, signal, dry_run)}\n")
    t.disconnect(); print("✅ 本轮循环完成")

if __name__ == "__main__": run_cycle(dry_run=True)
