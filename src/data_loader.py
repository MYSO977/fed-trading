"""
data_loader.py v2.0
罗素2000动态成交量池 + 实时量价特征
"""
import logging
import numpy as np
import pandas as pd
import yfinance as yf
import requests
from datasets import Dataset

log = logging.getLogger(__name__)

# ── 罗素2000股票池 ────────────────────────────────────────
RUSSELL2000_URL = "https://en.wikipedia.org/wiki/List_of_Russell_2000_companies"
FALLBACK_TICKERS_PATH = "/home/heng/tickers_executor.txt"

def get_russell2000_tickers() -> list:
    """从Wikipedia拉罗素2000，失败则用本地文件"""
    try:
        tables = pd.read_html(RUSSELL2000_URL)
        for t in tables:
            cols = [c.lower() for c in t.columns]
            if any("tick" in c or "symbol" in c for c in cols):
                col = [c for c in t.columns if "tick" in c.lower() or "symbol" in c.lower()][0]
                tickers = t[col].dropna().tolist()
                tickers = [str(s).replace(".", "-").strip() for s in tickers if str(s).strip()]
                log.info(f"罗素2000加载: {len(tickers)}只")
                return tickers
    except Exception as e:
        log.warning(f"Wikipedia拉取失败: {e}")

    # fallback本地文件
    try:
        with open(FALLBACK_TICKERS_PATH) as f:
            tickers = [l.strip() for l in f if l.strip()]
        log.info(f"本地股票池加载: {len(tickers)}只")
        return tickers
    except Exception as e:
        log.error(f"本地文件也失败: {e}")
        return ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN"]

# ── 动态成交量筛选 ─────────────────────────────────────────
def filter_by_volume(tickers: list, top_n: int = 100, min_price: float = 5.0) -> list:
    """
    量价初选：
    1. 过滤价格<5美元的垃圾股
    2. 按20日平均成交额排序
    3. 取前top_n只
    """
    log.info(f"开始量价筛选: {len(tickers)}只 → 目标{top_n}只")
    batch_size = 50
    results = []

    for i in range(0, min(len(tickers), 500), batch_size):
        batch = tickers[i:i+batch_size]
        try:
            data = yf.download(
                batch, period="25d", interval="1d",
                group_by="ticker", auto_adjust=True,
                progress=False, threads=True
            )
            for sym in batch:
                try:
                    if len(batch) == 1:
                        df = data
                    else:
                        df = data[sym] if sym in data.columns.get_level_values(0) else None
                    if df is None or len(df) < 5:
                        continue
                    df = df.dropna()
                    last_price = float(df["Close"].iloc[-1])
                    if last_price < min_price:
                        continue
                    avg_dollar_vol = float((df["Close"] * df["Volume"]).mean())
                    results.append({
                        "ticker": sym,
                        "price": last_price,
                        "avg_dollar_vol": avg_dollar_vol,
                        "vol_ratio": float(df["Volume"].iloc[-1] / df["Volume"].mean())
                    })
                except Exception:
                    continue
        except Exception as e:
            log.warning(f"批次{i}失败: {e}")
            continue

    if not results:
        log.warning("量价筛选无结果，返回fallback")
        return tickers[:top_n]

    df_rank = pd.DataFrame(results).sort_values("avg_dollar_vol", ascending=False)
    selected = df_rank.head(top_n)["ticker"].tolist()
    log.info(f"量价筛选完成: {len(selected)}只入选")
    log.info(f"Top5: {selected[:5]}")
    return selected

# ── 实时OHLCV拉取 ─────────────────────────────────────────
def fetch_ohlcv(ticker: str, period: str = "60d") -> pd.DataFrame:
    """拉单只股票OHLCV，列名统一小写"""
    try:
        df = yf.download(ticker, period=period, interval="1d",
                        auto_adjust=True, progress=False)
        df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
        df = df.dropna()
        if len(df) < 30:
            return pd.DataFrame()
        return df
    except Exception as e:
        log.warning(f"{ticker} OHLCV拉取失败: {e}")
        return pd.DataFrame()

# ── 实时prompt生成（兼容inference.py）────────────────────
def fetch_realtime_prompt(sym: str, **kw) -> str:
    """生成实时推理prompt"""
    df = fetch_ohlcv(sym, period="30d")
    if df.empty or len(df) < 21:
        return None
    try:
        close = df["close"]
        volume = df["volume"]
        ma5  = float(close.rolling(5).mean().iloc[-1])
        ma20 = float(close.rolling(20).mean().iloc[-1])
        vr   = float(volume.iloc[-1] / volume.rolling(20).mean().iloc[-1])
        rsi_delta = close.diff()
        gain = rsi_delta.clip(lower=0).rolling(14).mean().iloc[-1]
        loss = (-rsi_delta.clip(upper=0)).rolling(14).mean().iloc[-1]
        rsi  = round(100 - 100 / (1 + gain / (loss + 1e-9)), 1)
        price = float(close.iloc[-1])
        return (f"Asset:{sym}|Price:{price:.2f}|MA5/20:{ma5:.2f}/{ma20:.2f}"
                f"|VolRatio:{vr:.2f}x|RSI:{rsi}|Node:rt|Action:")
    except Exception as e:
        log.warning(f"{sym} prompt生成失败: {e}")
        return None

# ── 训练数据集生成 ────────────────────────────────────────
def load_real_market_data(node_id: str = "lenovo", samples_count: int = 100,
                          use_dynamic_pool: bool = False, **kw) -> Dataset:
    """
    生成训练数据集
    node_id: lenovo=tech数据, brain_18=risk数据, exec_11=execution数据
    """
    if use_dynamic_pool:
        tickers = get_russell2000_tickers()
        tickers = filter_by_volume(tickers, top_n=50)
    else:
        # 快速模式：用本地文件前50只
        try:
            with open(FALLBACK_TICKERS_PATH) as f:
                tickers = [l.strip() for l in f if l.strip()][:50]
        except Exception:
            tickers = ["TSLA","NVDA","AAPL","MSFT","AMZN","GOOGL","META","AMD"]

    out = []
    per_ticker = max(1, samples_count // len(tickers))

    for sym in tickers[:samples_count]:
        prompt = fetch_realtime_prompt(sym)
        if prompt:
            # 简单规则标注（后续LoRA微调覆盖）
            parts = dict(p.split(":") for p in prompt.split("|") if ":" in p)
            price = float(parts.get("Price", 0))
            ma20  = float(parts.get("MA5/20", "0/0").split("/")[1])
            vr    = float(parts.get("VolRatio", "1.0").replace("x",""))
            action = "BUY" if price > ma20 and vr > 1.2 else \
                     "SELL" if price < ma20 and vr > 1.2 else "HOLD"
            out.append({"text": prompt + action, "node": node_id})
        if len(out) >= samples_count:
            break

    if not out:
        log.warning("无真实数据，使用模拟数据")
        out = [{"text": f"Asset:TSLA|Price:250|MA5/20:245/240|VolRatio:1.5x|RSI:55|Node:rt|Action:BUY",
                "node": node_id}]

    log.info(f"数据集生成完成: {len(out)}条 (node={node_id})")
    return Dataset.from_list(out)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== 测试实时prompt ===")
    p = fetch_realtime_prompt("TSLA")
    print(f"TSLA: {p}")

    print("\n=== 测试量价筛选 ===")
    tickers = get_russell2000_tickers()
    top = filter_by_volume(tickers[:100], top_n=10)
    print(f"Top10: {top}")
