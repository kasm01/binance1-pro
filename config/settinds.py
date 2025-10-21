import os
from dataclasses import dataclass, field
from typing import List

@dataclass
class TradingConfig:
    SYMBOLS: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "BNBUSDT"])
    INTERVAL: str = "1m"
    MAX_DAILY_LOSS: float = 500.0
    MAX_PARALLEL_TRADES: int = 3

@dataclass
class MLConfig:
    MIN_CONFIDENCE: float = 0.6
    RETRAIN_HOURS: int = 6

@dataclass
class Config:
    trading: TradingConfig = field(default_factory=TradingConfig)
    ml: MLConfig = field(default_factory=MLConfig)
    api_keys: dict = field(default_factory=lambda: {
        "BINANCE_API_KEY": os.getenv("BINANCE_API_KEY"),
        "BINANCE_SECRET_KEY": os.getenv("BINANCE_SECRET_KEY"),
        "REDIS_URL": os.getenv("REDIS_URL", "redis://localhost:6379/0")
    })

    def validate(self):
        if not self.api_keys["BINANCE_API_KEY"] or not self.api_keys["BINANCE_SECRET_KEY"]:
            raise ValueError("Binance API key and secret must be set.")
