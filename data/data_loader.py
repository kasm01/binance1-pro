# data/data_loader.py
import pandas as pd
import numpy as np
import logging
from binance.client import Client

class DataLoader:
    def __init__(self, api_key: str, api_secret: str):
        self.client = Client(api_key, api_secret)
        logging.info("✅ DataLoader initialized successfully.")

    def fetch_historical_data(self, symbol: str, interval: str = "1h", limit: int = 1000) -> pd.DataFrame:
        """Binance API'den geçmiş fiyat verilerini alır."""
        klines = self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_buy_base_vol", "taker_buy_quote_vol", "ignore"
        ])
        df = df[["open_time", "open", "high", "low", "close", "volume"]]
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df = df.astype(float, errors="ignore")
        return df.set_index("open_time")

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Min-Max normalizasyonu uygular."""
        result = (df - df.min()) / (df.max() - df.min())
        return result.fillna(0)

    def save_to_csv(self, df: pd.DataFrame, path: str):
        df.to_csv(path)
        logging.info(f"💾 Data saved to {path}")

    def load_from_csv(self, path: str) -> pd.DataFrame:
        return pd.read_csv(path, index_col=0, parse_dates=True)
