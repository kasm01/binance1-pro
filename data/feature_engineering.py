# data/feature_engineering.py
import pandas as pd
import ta

class FeatureEngineer:
    def __init__(self):
        pass

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Teknik indikatörleri ekler."""
        df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
        df["ema_20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
        df["ema_50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
        df["macd"] = ta.trend.MACD(df["close"]).macd()
        df["atr"] = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"]).average_true_range()
        df["roc"] = ta.momentum.ROCIndicator(df["close"]).roc()
        df["returns"] = df["close"].pct_change()
        df = df.dropna()
        return df

    def generate_target(self, df: pd.DataFrame, threshold: float = 0.002) -> pd.DataFrame:
        """Yukarı / Aşağı yönlü hareketleri hedef olarak etiketler."""
        df["target"] = (df["returns"].shift(-1) > threshold).astype(int)
        return df.dropna()
