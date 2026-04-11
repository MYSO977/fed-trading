#!/usr/bin/env python3
# data_loader.py - 真实市场数据加载器（动量策略专用）
import pandas as pd
import yfinance as yf
import numpy as np
from datasets import Dataset
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

# ============ 配置：你关注的低流通盘动量股池 ============
# 可根据实盘需求动态扩展（建议单节点每次训练 3~5 只，避免显存溢出）
SYMBOLS = [
    "TSLA", "NVDA", "AMD", "MARA", "RIOT",  # 高波动科技/矿业股
    "SOUN", "BBAI", "IONQ", "RKLB", "PLTR"  # 低流通盘动量标的
]

def calculate_momentum_label(df, lookback=5, threshold=0.02):
    """
    动量策略标签生成：
    - 未来 lookback 天收益率 > threshold → BUY
    - 未来 lookback 天收益率 < -threshold → SELL  
    - 否则 → HOLD
    """
    future_ret = df["Close"].pct_change(lookback).shift(-lookback)
    labels = []
    for ret in future_ret:
        if pd.isna(ret):
            labels.append("HOLD")
        elif ret > threshold:
            labels.append("BUY")
        elif ret < -threshold:
            labels.append("SELL")
        else:
            labels.append("HOLD")
    return labels

def load_real_market_data(node_id="global", days=30, lookback=5, threshold=0.02):
    """
    拉取真实行情，构造指令微调样本
    输出格式与训练脚本完全对齐: {"text": "Feature... Action: LABEL"}
    """
    rows = []
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    for sym in SYMBOLS:
        try:
            # 下载日线数据（可改为 period="5d" interval="1h" 获取小时线）
            df = yf.download(sym, start=start_date, end=end_date, progress=False)
            if len(df) < 20:  # 数据不足跳过
                continue
                
            # 计算技术指标
            df["MA5"] = df["Close"].rolling(5).mean()
            df["MA20"] = df["Close"].rolling(20).mean()
            df["VolRatio"] = df["Volume"] / df["Volume"].rolling(20).mean()
            df["Ret5"] = df["Close"].pct_change(5)
            
            # 生成动量标签
            df["Label"] = calculate_momentum_label(df, lookback, threshold)
            
            # 构造训练样本（对齐原始格式）
            for i in range(20, len(df) - lookback):  # 留出指标计算窗口
                row = df.iloc[i]
                if pd.isna(row["Label"]) or row["Label"] == "HOLD":
                    continue  # 只训练明确信号，提升样本质量
                    
                # 构造 prompt（保持与合成数据一致的句式）
                prompt = (
                    f"Asset: {sym} | "
                    f"Price: {row['Close']:.2f} | "
                    f"MA5/20: {row['MA5']:.2f}/{row['MA20']:.2f} | "
                    f"VolRatio: {row['VolRatio']:.1f}x | "
                    f"Ret5: {row['Ret5']*100:+.1f}% | "
                    f"Node: {node_id} | Action:"
                )
                rows.append({"text": f"{prompt} {row['Label']}"})
                
        except Exception as e:
            print(f"⚠️ 跳过 {sym}: {e}")
            continue
    
    print(f"✅ 节点 [{node_id}] 加载 {len(rows)} 条真实行情样本")
    return Dataset.from_list(rows)

# ============ 本地测试 ============
if __name__ == "__main__":
    ds = load_real_market_data(node_id="test", days=15)
    print("\n📊 样本预览:")
    for i in range(min(3, len(ds))):
        print(ds[i]["text"])
