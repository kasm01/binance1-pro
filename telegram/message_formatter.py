# telegram/message_formatter.py

class MessageFormatter:
    """
    Bot mesajlarını biçimlendirir
    """
    @staticmethod
    def format_trade(trade):
        """
        trade: dict -> {symbol, side, qty, price, pnl}
        """
        return (
            f"💹 Trade Bilgisi:\n"
            f"Symbol: {trade['symbol']}\n"
            f"Side: {trade['side']}\n"
            f"Miktar: {trade['qty']}\n"
            f"Fiyat: {trade['price']}\n"
            f"PnL: {trade['pnl']}\n"
        )

    @staticmethod
    def format_alert(message, level="INFO"):
        """
        Kritik uyarıları veya genel mesajları biçimlendirir
        """
        prefix = "⚠️" if level == "ALERT" else "ℹ️"
        return f"{prefix} {message}"
