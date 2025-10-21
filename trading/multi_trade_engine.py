# trading/multi_trade_engine.py
from threading import Thread

class MultiTradeEngine:
    """
    Aynı anda birden fazla pozisyon açmak için paralel trade engine
    """
    def __init__(self, trade_executor):
        self.trade_executor = trade_executor

    def execute_trades_parallel(self, trade_list):
        """
        trade_list = [
            {"symbol": "BTCUSDT", "side": "BUY", "entry_price": 30000, "stop_loss": 29500},
            {"symbol": "ETHUSDT", "side": "SELL", "entry_price": 2000, "stop_loss": 2050},
            ...
        ]
        """
        threads = []
        for trade in trade_list:
            t = Thread(target=self.trade_executor.execute_trade, kwargs=trade)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()
