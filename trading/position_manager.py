# trading/position_manager.py
import threading

class PositionManager:
    """
    Pozisyon yönetimi:
    - Açık pozisyonları takip eder
    - Pozisyon büyüklüğünü ve yönünü günceller
    """
    def __init__(self):
        self.positions = {}
        self.lock = threading.Lock()

    def add_position(self, symbol, side, qty, entry_price):
        with self.lock:
            self.positions[symbol] = {
                "side": side,
                "qty": qty,
                "entry_price": entry_price
            }

    def close_position(self, symbol):
        with self.lock:
            if symbol in self.positions:
                del self.positions[symbol]

    def get_position(self, symbol):
        return self.positions.get(symbol, None)

    def update_position(self, symbol, qty=None, entry_price=None):
        with self.lock:
            pos = self.positions.get(symbol)
            if pos:
                if qty is not None:
                    pos["qty"] = qty
                if entry_price is not None:
                    pos["entry_price"] = entry_price
