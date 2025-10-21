# trading/capital_manager.py
class CapitalManager:
    """
    Sermaye yönetimi:
    - Toplam bakiye
    - Maksimum risk
    - Pozisyon başına sermaye
    """
    def __init__(self, total_capital):
        self.total_capital = total_capital
        self.available_capital = total_capital

    def allocate(self, amount):
        if amount <= self.available_capital:
            self.available_capital -= amount
            return True
        return False

    def release(self, amount):
        self.available_capital += amount
        if self.available_capital > self.total_capital:
            self.available_capital = self.total_capital
