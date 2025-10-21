# config/redis_config.py
import redis
import logging
from typing import Optional
from config.settings import Settings

logger = logging.getLogger(__name__)

class RedisManager:
    """
    Redis bağlantı yöneticisi (önbellek ve anlık veri için)
    """
    def __init__(self):
        self.client: Optional[redis.Redis] = None

    def connect(self):
        try:
            self.client = redis.StrictRedis(
                host=Settings.REDIS_HOST,
                port=Settings.REDIS_PORT,
                db=Settings.REDIS_DB,
                password=Settings.REDIS_PASSWORD,
                decode_responses=True
            )
            self.client.ping()
            logger.info("✅ Redis bağlantısı kuruldu.")
        except Exception as e:
            logger.error(f"❌ Redis bağlantı hatası: {e}")
            self.client = None

    def get(self, key: str):
        if not self.client:
            self.connect()
        try:
            return self.client.get(key)
        except Exception as e:
            logger.error(f"Redis GET hatası: {e}")
            return None

    def set(self, key: str, value, ttl: int = Settings.MODEL_CACHE_TTL):
        if not self.client:
            self.connect()
        try:
            self.client.set(key, value, ex=ttl)
        except Exception as e:
            logger.error(f"Redis SET hatası: {e}")

    def delete(self, key: str):
        if self.client:
            try:
                self.client.delete(key)
            except Exception as e:
                logger.error(f"Redis DELETE hatası: {e}")
