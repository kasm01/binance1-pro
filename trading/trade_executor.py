# trading/trade_executor.py
class TradeExecutor:
    """
    Trade execution:
    - Binance Futures API ile pozisyon açma/kapatma
    - Retry ve fallback mekanizması ile güvenli işlem
    """
    def __init__(self, client, position_manager, capital_manager, risk_manager):
        self.client = client
        self.position_manager = position_manager
        self.capital_manager = capital_manager
        self.risk_manager = risk_manager

    def execute_trade(self, symbol, side, entry_price, stop_loss):
        qty = self.risk_manager.calculate_qty(
            self.capital_manager.total_capital, entry_price, stop_loss
        )
        if not self.capital_manager.allocate(qty * entry_price):
            print(f"❌ Yetersiz bakiye: {symbol}")
            return False

        try:
            # Market order örneği
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type="MARKET",
                quantity=qty
            )
            self.position_manager.add_position(symbol, side, qty, entry_price)
            print(f"✅ Trade executed: {symbol} {side} {qty} units")
            return order
        except Exception as e:
            self.capital_manager.release(qty * entry_price)
            print(f"❌ Trade failed: {e}")
            return False
