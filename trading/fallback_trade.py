# trading/fallback_trade.py
class FallbackTrade:
    """
    Ana trade executor başarısız olursa devreye girer
    - Küçük miktar ile basit logic trades uygular
    """
    def __init__(self, trade_executor):
        self.trade_executor = trade_executor

    def execute(self, symbol, side, entry_price, stop_loss):
        print(f"⚠️ Fallback trade activated: {symbol}")
        qty = 0.1  # küçük miktar
        self.trade_executor.client.futures_create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=qty
        )
