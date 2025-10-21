# config/credentials.py
"""
Binance, Telegram ve diğer API anahtarlarını yönetir.
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class BinanceKeys:
    api_key: str
    secret_key: str

    def is_valid(self) -> bool:
        return bool(self.api_key and self.secret_key)

@dataclass
class TelegramKeys:
    token: str
    chat_id: str

    def is_valid(self) -> bool:
        return bool(self.token and self.chat_id)
