#!/usr/bin/env python3
"""策略优化与回测流水线：参数网格搜索 -> 回测评估 -> 保存最优配置"""
import sys, os, yaml, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data_loader import load_real_market_data
from src.strategy_engine import StrategyEngine
from src.backtester import Backtester
import pandas as pd, numpy as np, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def generate_mock_ohlcv(n=500):
    """生成带清晰市场结构的稳健版 OHLCV 数据（比例切片，永不越界）"""
    np.random.seed(42)
    rets = np.zeros(n)
    
    # 用比例定义阶段，自动适配任意 n
    seg = n // 5  # 每段约 20%
    
    # 阶段 1: 震荡筑底 (0-20%)
    rets[0:seg] = np.random.normal(0, 0.008, seg)
    # 阶段 2: 主升浪 (20-40%)
    rets[seg:2*seg] = np.random.normal(0.0015, 0.01, seg)
    # 阶段 3: 高位震荡 (40-60%)
    rets[2*seg:3*seg] = np.random.normal(0, 0.006, seg)
    # 阶段 4: 下跌趋势 (60-80%)
    rets[3*seg:4*seg] = np.random.normal(-0.002, 0.012, seg)
    # 阶段 5: 筑底反弹 (80-100%)
    rets[4*seg:] = np.random.normal(0.001, 0.009, n - 4*seg)
    
    prices = 150 * np.exp(np.cumsum(rets))
    df = pd.DataFrame({"close": prices})
    df["high"] = df["close"] * (1 + np.abs(np.random.normal(0, 0.005, n)))
    df["low"] = df["close"] * (1 - np.abs(np.random.normal(0, 0.005, n)))
    
    # 趋势段放量 (阶段 2 和 4)
    vol = np.random.lognormal(14, 1.0, n)
    vol[seg:2*seg] *= 1.8   # 主升浪放量
    vol[3*seg:4*seg] *= 1.6 # 下跌放量
    df["volume"] = vol * (1 + np.abs(rets)*20)
    return df

def grid_search(df):
    param_grid = [
        {"ma_fast": 5, "ma_slow": 20, "roc_period": 10, "vol_threshold": 1.2, "min_confidence": 0.6},
        {"ma_fast": 8, "ma_slow": 21, "roc_period": 14, "vol_threshold": 1.5, "min_confidence": 0.5},
        {"ma_fast": 3, "ma_slow": 15, "roc_period": 7, "vol_threshold": 1.0, "min_confidence": 0.7},
    ]
    results = []
    bt = Backtester(commission=0.0005, slippage=0.001, initial_capital=100000)
    
    for params in param_grid:
        eng = StrategyEngine(params)
        feat_df = eng.compute_features(df)
        metrics = bt.run(feat_df, eng.get_signal)
        metrics["params"] = params
        results.append(metrics)
        logging.info(f" 参数: {params} | 收益: {metrics['total_return']} | 夏普: {metrics['sharpe']} | 回撤: {metrics['max_drawdown']}")
    
    # 按夏普比率排序
    results.sort(key=lambda x: x["sharpe"], reverse=True)
    return results[0]

if __name__ == "__main__":
    logging.info("🚀 启动策略优化流水线...")
    df = generate_mock_ohlcv(500)
    best = grid_search(df)
    
    # 保存最优参数
    config_path = os.path.expanduser("~/fed-trading/config/strategy_params.yaml")
    with open(config_path, "w") as f:
        yaml.dump({"best_params": best["params"], "metrics": {k:v for k,v in best.items() if k!="params"}}, f)
    
    logging.info(f"\n🏆 最优参数已保存至: {config_path}")
    logging.info(f"📈 预期表现: 收益 {best['total_return']} | 夏普 {best['sharpe']} | 回撤 {best['max_drawdown']}")
    print("\n✅ 策略优化完成。可运行 python3 scripts/test_dry_run.py 验证实盘信号。")