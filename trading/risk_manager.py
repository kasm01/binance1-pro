# trading/risk_manager.py
class RiskManager:
    """
    Risk yönetimi:
    - Maksimum kayıp oranı
    - Stop-loss ve take-profit hesaplamaları
    - Pozisyon başına risk optimizasyonu
    """
    def __init__(self, max_risk_per_trade=0.02):
        self.max_risk_per_trade = max_risk_per_trade

    def calculate_qty(self, capital, entry_price, stop_loss):
        risk_amount = capital * self.max_risk_per_trade
        qty = risk_amount / abs(entry_price - stop_loss)
        return qty
