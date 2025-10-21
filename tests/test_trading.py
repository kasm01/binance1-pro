# tests/test_trading.py
import unittest
from trading.trade_executor import TradeExecutor
from trading.risk_manager import RiskManager

class TestTrading(unittest.TestCase):

    def test_trade_execution(self):
        executor = TradeExecutor()
        result = executor.place_order(symbol="BTCUSDT", side="BUY", qty=0.001)
        self.assertTrue("order_id" in result)

    def test_risk_manager_limits(self):
        risk = RiskManager()
        self.assertTrue(risk.check_risk(0.5))
        self.assertFalse(risk.check_risk(5.0))

if __name__ == "__main__":
    unittest.main()
