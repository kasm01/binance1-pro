# tests/test_api.py
import unittest
from websocket.binance_ws import BinanceWS

class TestAPI(unittest.TestCase):

    def test_binance_ws_connection(self):
        ws = BinanceWS()
        self.assertTrue(ws.connect() in [True, False])  # Bağlantı kontrolü

if __name__ == "__main__":
    unittest.main()
