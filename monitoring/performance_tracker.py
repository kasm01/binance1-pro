# monitoring/performance_tracker.py
import time

class PerformanceTracker:
    """
    Botun performansını ölçmek ve raporlamak için kullanılır
    """
    def __init__(self):
        self.start_time = time.time()
        self.trades_executed = 0
        self.profit_loss = 0.0

    def log_trade(self, pnl):
        self.trades_executed += 1
        self.profit_loss += pnl

    def get_summary(self):
        elapsed = time.time() - self.start_time
        return {
            "runtime_sec": elapsed,
            "trades_executed": self.trades_executed,
            "profit_loss": self.profit_loss
        }
