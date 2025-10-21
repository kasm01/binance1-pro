# core/cache_manager.py
"""
🧠 CacheManager — Redis destekli akıllı önbellek yöneticisi.
"""
import json
import time
from config.redis_config import RedisManager
from core.logger import logger

class CacheManager:
    """
    Model tahminleri, fiyat verileri ve API yanıtlarını Redis’te saklar.
    """
    def __init__(self):
        self.redis = RedisManager()
        self.redis.connect()

    def set_cache(self, key: str, data, ttl: int = 60 * 10):
        try:
            self.redis.set(key, json.dumps(data), ttl)
            logger.debug(f"🔒 Cache set: {key} (TTL={ttl}s)")
        except Exception as e:
            logger.error(f"Cache set hatası: {e}")

    def get_cache(self, key: str):
        try:
            data = self.redis.get(key)
            if data:
                logger.debug(f"🧩 Cache hit: {key}")
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Cache get hatası: {e}")
            return None

    def clear_cache(self, key: str):
        try:
            self.redis.delete(key)
            logger.debug(f"🗑️ Cache silindi: {key}")
        except Exception as e:
            logger.error(f"Cache clear hatası: {e}")
