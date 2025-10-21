# core/notifier.py
import requests
import logging
from config.settings import Settings

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """
    Telegram üzerinden sistem ve trade bildirimleri gönderir.
    """
    def __init__(self):
        self.token = Settings.TELEGRAM_BOT_TOKEN
        self.chat_id = Settings.TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send(self, message: str):
        if not self.token or not self.chat_id:
            logger.warning("Telegram token veya chat_id bulunamadı.")
            return

        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
        try:
            response = requests.post(self.api_url, data=payload, timeout=5)
            if response.status_code != 200:
                logger.error(f"Telegram gönderim hatası: {response.text}")
        except Exception as e:
            logger.error(f"Telegram bağlantı hatası: {e}")

# Global notifier
notifier = TelegramNotifier()
