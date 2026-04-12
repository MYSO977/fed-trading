#!/usr/bin/env python3
import sys, os, yaml; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.strategy_engine import StrategyEngine
from src.backtester import Backtester
from src.report_generator import ReportGenerator
import pandas as pd, numpy as np, logging
logging.basicConfig(level=logging.INFO)

def generate_mock_ohlcv(n=500):
    np.random.seed(42); rets = np.zeros(n); seg = n//5
    rets[0:seg] = np.random.normal(0, 0.008, seg)
    rets[seg:2*seg] = np.random.normal(0.0015, 0.01, seg)
    rets[2*seg:3*seg] = np.random.normal(0, 0.006, seg)
    rets[3*seg:4*seg] = np.random.normal(-0.002, 0.012, seg)
    rets[4*seg:] = np.random.normal(0.001, 0.009, n-4*seg)
    prices = 150 * np.exp(np.cumsum(rets))
    df = pd.DataFrame({"close": prices})
    df["high"] = df["close"] * (1 + np.abs(np.random.normal(0, 0.005, n)))
    df["low"] = df["close"] * (1 - np.abs(np.random.normal(0, 0.005, n)))
    vol = np.random.lognormal(14, 1.0, n)
    vol[seg:2*seg] *= 1.8; vol[3*seg:4*seg] *= 1.6
    df["volume"] = vol * (1 + np.abs(rets)*20)
    return df

def run_backtest(params):
    eng = StrategyEngine(params); bt = Backtester()
    df = generate_mock_ohlcv(500); feat = eng.compute_features(df)
    equity, trades = [bt.capital], []
    cash, pos, entry, sl, tp, hold = bt.capital, 0, 0, 0, np.inf, 0
    for i, row in feat.iterrows():
        sig = eng.get_signal(row.to_dict()); price = row["close"]
        exec_p = price * (1+bt.slippage) if sig["action"]=="BUY" else price * (1-bt.slippage)
        if pos > 0:
            hold += 1
            if hold >= 3 and (row["low"] <= sl or row["high"] >= tp):
                exit_p = row["close"] * (1-bt.slippage)
                pnl = (exit_p - entry) * pos - (exit_p * pos * bt.commission * 2)
                cash += pnl; trades.append({"exit":i, "pnl":pnl, "hold":hold})
                pos, hold, sl, tp = 0, 0, 0, np.inf
        if sig["action"]=="BUY" and pos==0 and hold==0 and cash>exec_p:
            qty = int(cash * 0.2 / exec_p)
            cash -= qty * exec_p * (1+bt.commission)
            pos, entry = qty, exec_p
            sl, tp = sig.get("stop_loss", entry*0.98), sig.get("take_profit", entry*1.06)
            hold = 0; trades.append({"entry":i, "price":exec_p, "qty":qty})
        equity.append(cash + pos * price)
    return equity, trades, bt._calc_metrics()

if __name__ == "__main__":
    logging.info("🚀 启动回测报告生成...")
    # 健壮加载配置（处理 numpy 标量等边缘情况）
    try:
        import yaml
        with open("config/strategy_params.yaml") as f:
            cfg = yaml.safe_load(f) or {}
        params = cfg.get("best_params", {})
        # 确保参数是纯 Python 类型
        params = {k: float(v) if isinstance(v, (int, float, str)) else v for k, v in 
                  ({"ma_fast":5,"ma_slow":20,"roc_period":10,"vol_threshold":1.2,"min_confidence":0.6} | params).items()}
    except Exception as e:
        print(f"⚠️ 配置加载失败: {e}，使用默认参数")
        params = {"ma_fast":5,"ma_slow":20,"roc_period":10,"vol_threshold":1.2,"min_confidence":0.6}
    equity, trades, metrics = run_backtest(params)
    reporter = ReportGenerator()
    path = reporter.generate(equity, trades, params, metrics, "FED_TRADING")
    logging.info("🏆 报告已生成: "+path+".md | 收益:"+str(metrics.get("total_return"))+" | 夏普:"+str(metrics.get("sharpe")))
