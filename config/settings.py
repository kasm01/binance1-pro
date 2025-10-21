# config/settings.py
import os
from dotenv import load_dotenv

# Ortam değişkenlerini yükle (.env dosyasından)
load_dotenv()

class Settings:
    """
    Ana yapılandırma sınıfı.
    Binance, Redis, Telegram ve Google Cloud yapılandırmalarını içerir.
    """
    # === Uygulama Ayarları ===
    APP_NAME = "Binance1-Pro Bot"
    VERSION = "2.1.0"
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # === Binance API Ayarları ===
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
    BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")
    BINANCE_FUTURES_URL = "https://fapi.binance.com"
    BINANCE_WS_URL = "wss://fstream.binance.com/ws"

    # === Telegram ===
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # === Redis ===
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

    # === Model & Cache Ayarları ===
    MODEL_CACHE_TTL = 1800  # saniye (30 dakika)
    PREDICTION_LOG_PATH = os.path.join(BASE_DIR, "logs", "predictions.log")

    # === Risk Yönetimi ===
    MAX_RISK_PER_TRADE = 0.02  # %2 risk
    MAX_OPEN_POSITIONS = 3
    CAPITAL_ALLOCATION = 0.95  # Toplam sermayenin %95'i kullanılabilir

    # === Google Cloud Ayarları ===
    GCLOUD_PROJECT_ID = os.getenv("GCLOUD_PROJECT_ID", "")
    GCLOUD_REGION = os.getenv("GCLOUD_REGION", "europe-west1")
    GCLOUD_REDIS_INSTANCE = os.getenv("GCLOUD_REDIS_INSTANCE", "")
    GCLOUD_LOGGING = True

    # === Supervisor ===
    SUPERVISOR_CONFIG_PATH = os.path.join(BASE_DIR, "config", "supervisor.conf")

    # === Diğer ===
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def summary(cls):
        """Ayarların kısa bir özetini yazdırır."""
        print(f"📦 {cls.APP_NAME} v{cls.VERSION}")
        print(f"🌐 Environment: {cls.ENVIRONMENT}")
        print(f"🔑 Binance API: {cls.BINANCE_API_KEY[:8]}...")
        print(f"🤖 Telegram Chat ID: {cls.TELEGRAM_CHAT_ID}")
        print(f"🧠 Redis: {cls.REDIS_HOST}:{cls.REDIS_PORT}")
        print(f"💰 Max Positions: {cls.MAX_OPEN_POSITIONS}")
        print(f"☁️ Google Cloud Project: {cls.GCLOUD_PROJECT_ID}")
