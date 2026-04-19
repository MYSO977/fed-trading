import numpy as np
import pandas as pd

class StrategyEngine:
    """
    多因子信号引擎 v2.0
    量价形态 + 技术指标 + 经典策略融合
    """
    def __init__(self, params=None):
        defaults = {
            # 均线
            "ma_fast": 5,
            "ma_slow": 20,
            "ma_200": 200,
            "ema_9": 9,
            "ema_21": 21,
            # 动量
            "roc_period": 10,
            "rsi_period": 14,
            "rsi_ob": 70,
            "rsi_os": 30,
            # MACD
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            # 布林带
            "bb_period": 20,
            "bb_std": 2.0,
            # 量价
            "vol_threshold": 1.5,
            "vol_ma": 20,
            "vwap_period": 20,
            # ATR风控
            "atr_period": 14,
            "atr_mult_sl": 2.0,
            "atr_mult_tp": 3.0,
            # 信号阈值
            "min_confidence": 0.55,
        }
        self.p = {**defaults, **(params or {})}
        for k in ["ma_fast","ma_slow","ma_200","ema_9","ema_21",
                  "roc_period","rsi_period","macd_fast","macd_slow",
                  "macd_signal","bb_period","vol_ma","vwap_period","atr_period"]:
            if k in self.p:
                self.p[k] = int(self.p[k])

    # ── 指标计算 ──────────────────────────────────────────
    def _ema(self, series, period):
        return series.ewm(span=period, adjust=False).mean()

    def _rsi(self, series, period):
        delta = series.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / (loss + 1e-9)
        return 100 - (100 / (1 + rs))

    def _macd(self, series):
        fast = self._ema(series, self.p["macd_fast"])
        slow = self._ema(series, self.p["macd_slow"])
        macd = fast - slow
        signal = self._ema(macd, self.p["macd_signal"])
        hist = macd - signal
        return macd, signal, hist

    def _bollinger(self, series):
        mid = series.rolling(self.p["bb_period"]).mean()
        std = series.rolling(self.p["bb_period"]).std()
        upper = mid + self.p["bb_std"] * std
        lower = mid - self.p["bb_std"] * std
        return upper, mid, lower

    def _vwap(self, df):
        tp = (df["high"] + df["low"] + df["close"]) / 3
        vwap = (tp * df["volume"]).rolling(self.p["vwap_period"]).sum() / \
               df["volume"].rolling(self.p["vwap_period"]).sum()
        return vwap

    def _atr(self, df):
        hl = df["high"] - df["low"]
        hc = (df["high"] - df["close"].shift()).abs()
        lc = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return tr.rolling(self.p["atr_period"]).mean()

    # ── 量价形态检测 ──────────────────────────────────────
    def _detect_patterns(self, df):
        c = df["close"]
        o = df["open"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]
        body = (c - o).abs()
        candle = h - l

        patterns = pd.DataFrame(index=df.index)

        # 锤子线（看涨反转）
        lower_shadow = o.where(c > o, c) - l
        patterns["hammer"] = (
            (lower_shadow > 2 * body) &
            (body > 0) &
            (c > o)
        ).astype(int)

        # 吞没形态（看涨）
        patterns["bullish_engulf"] = (
            (c > o) &
            (c.shift() < o.shift()) &
            (c > o.shift()) &
            (o < c.shift())
        ).astype(int)

        # 十字星（反转信号）
        patterns["doji"] = (body < candle * 0.1).astype(int)

        # 放量突破（价涨量增）
        patterns["vol_breakout"] = (
            (c > c.shift()) &
            (v > v.rolling(self.p["vol_ma"]).mean() * self.p["vol_threshold"])
        ).astype(int)

        # 缩量回调（健康回调）
        patterns["vol_pullback"] = (
            (c < c.shift()) &
            (v < v.rolling(self.p["vol_ma"]).mean() * 0.8)
        ).astype(int)

        # 价格突破20日高点
        patterns["breakout_20d"] = (c > h.shift().rolling(20).max()).astype(int)

        return patterns

    # ── 经典策略信号 ──────────────────────────────────────
    def _classic_strategies(self, df):
        signals = pd.DataFrame(index=df.index)

        # 1. 双均线金叉/死叉
        signals["ma_cross"] = np.where(
            (df["MA_Fast"] > df["MA_Slow"]) & (df["MA_Fast"].shift() <= df["MA_Slow"].shift()), 1,
            np.where(
                (df["MA_Fast"] < df["MA_Slow"]) & (df["MA_Fast"].shift() >= df["MA_Slow"].shift()), -1, 0
            )
        )

        # 2. MACD金叉/死叉
        signals["macd_cross"] = np.where(
            (df["MACD"] > df["MACD_Signal"]) & (df["MACD"].shift() <= df["MACD_Signal"].shift()), 1,
            np.where(
                (df["MACD"] < df["MACD_Signal"]) & (df["MACD"].shift() >= df["MACD_Signal"].shift()), -1, 0
            )
        )

        # 3. RSI超买超卖
        signals["rsi_signal"] = np.where(
            df["RSI"] < self.p["rsi_os"], 1,
            np.where(df["RSI"] > self.p["rsi_ob"], -1, 0)
        )

        # 4. 布林带突破
        signals["bb_signal"] = np.where(
            df["close"] < df["BB_Lower"], 1,
            np.where(df["close"] > df["BB_Upper"], -1, 0)
        )

        # 5. VWAP多空
        signals["vwap_signal"] = np.where(df["close"] > df["VWAP"], 1, -1)

        # 6. 200日均线趋势过滤
        signals["trend_filter"] = np.where(df["close"] > df["MA_200"], 1, -1)

        return signals

    # ── 主特征计算（回测用）─────────────────────────────
    def compute_features(self, df):
        df = df.copy()
        # 均线
        df["MA_Fast"]  = df["close"].rolling(self.p["ma_fast"]).mean()
        df["MA_Slow"]  = df["close"].rolling(self.p["ma_slow"]).mean()
        df["MA_200"]   = df["close"].rolling(self.p["ma_200"]).mean()
        df["EMA_9"]    = self._ema(df["close"], self.p["ema_9"])
        df["EMA_21"]   = self._ema(df["close"], self.p["ema_21"])
        # 动量
        df["ROC"]      = df["close"].pct_change(self.p["roc_period"])
        df["RSI"]      = self._rsi(df["close"], self.p["rsi_period"])
        # MACD
        df["MACD"], df["MACD_Signal"], df["MACD_Hist"] = self._macd(df["close"])
        # 布林带
        df["BB_Upper"], df["BB_Mid"], df["BB_Lower"] = self._bollinger(df["close"])
        df["BB_Width"] = (df["BB_Upper"] - df["BB_Lower"]) / df["BB_Mid"]
        # 量价
        df["VolRatio"] = df["volume"] / df["volume"].rolling(self.p["vol_ma"]).mean()
        df["VWAP"]     = self._vwap(df)
        # ATR
        df["ATR"]      = self._atr(df)
        df["ATR_Pct"]  = df["ATR"] / df["close"]
        # 形态
        patterns = self._detect_patterns(df)
        df = pd.concat([df, patterns], axis=1)
        # 经典策略
        signals = self._classic_strategies(df)
        df = pd.concat([df, signals], axis=1)
        return df.dropna()

    # ── 实时推理接口 ──────────────────────────────────────
    def get_signal(self, row):
        score = 0.0
        reasons = []

        # 趋势层（权重0.3）
        if row.get("MA_Fast", 0) > row.get("MA_Slow", 0):
            score += 0.15; reasons.append("均线多头")
        if row.get("close", 0) > row.get("VWAP", 0):
            score += 0.10; reasons.append("价格>VWAP")
        if row.get("close", 0) > row.get("MA_200", 0):
            score += 0.05; reasons.append("200日线上方")

        # 动量层（权重0.3）
        rsi = row.get("RSI", 50)
        if 40 < rsi < self.p["rsi_ob"]:
            score += 0.15; reasons.append(f"RSI健康({rsi:.0f})")
        elif rsi < self.p["rsi_os"]:
            score += 0.20; reasons.append(f"RSI超卖({rsi:.0f})")
        if row.get("MACD", 0) > row.get("MACD_Signal", 0):
            score += 0.10; reasons.append("MACD多头")
        if row.get("ROC", 0) > 0:
            score += 0.05; reasons.append("动量为正")

        # 量价层（权重0.25）
        if row.get("vol_breakout", 0):
            score += 0.15; reasons.append("放量突破")
        elif row.get("VolRatio", 0) > self.p["vol_threshold"]:
            score += 0.10; reasons.append("量能放大")
        if row.get("vol_pullback", 0):
            score += 0.05; reasons.append("缩量回调")

        # 形态层（权重0.15）
        if row.get("hammer", 0):
            score += 0.08; reasons.append("锤子线")
        if row.get("bullish_engulf", 0):
            score += 0.10; reasons.append("看涨吞没")
        if row.get("breakout_20d", 0):
            score += 0.07; reasons.append("突破20日高点")

        # 空头扣分
        if row.get("close", 0) < row.get("BB_Lower", 0):
            score += 0.05; reasons.append("布林下轨支撑")
        if row.get("close", 0) > row.get("BB_Upper", 0):
            score -= 0.10; reasons.append("布林上轨超买")
        if rsi > self.p["rsi_ob"]:
            score -= 0.15; reasons.append(f"RSI超买({rsi:.0f})")

        score = max(0.0, min(score, 1.0))

        if score >= self.p["min_confidence"]:
            action = "BUY"
        elif score <= 0.25:
            action = "SELL"
        else:
            action = "HOLD"

        atr = row.get("ATR", row.get("close", 100) * 0.02)
        price = row.get("close", 0)
        sl = price - self.p["atr_mult_sl"] * atr if action == "BUY" else price + self.p["atr_mult_sl"] * atr
        tp = price + self.p["atr_mult_tp"] * atr if action == "BUY" else price - self.p["atr_mult_tp"] * atr

        return {
            "action": action,
            "confidence": round(score, 3),
            "stop_loss": round(sl, 2),
            "take_profit": round(tp, 2),
            "rsi": round(rsi, 1),
            "macd_hist": round(row.get("MACD_Hist", 0), 4),
            "vol_ratio": round(row.get("VolRatio", 0), 2),
            "bb_width": round(row.get("BB_Width", 0), 4),
            "reason": " | ".join(reasons) if reasons else "无明确信号"
        }
