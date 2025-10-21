# monitoring/trade_logger.py
import csv
import os
from datetime import datetime

class TradeLogger:
    """
    Tüm alım-satım işlemlerini CSV dosyasına kaydeder
    """
    def __init__(self, log_file="trade_log.csv"):
        self.log_file = log_file
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "symbol", "side", "qty", "price", "pnl"])

    def log_trade(self, symbol, side, qty, price, pnl):
        with open(self.log_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([datetime.utcnow(), symbol, side, qty, price, pnl])
