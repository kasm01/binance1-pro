# core/utils.py
"""
🎛️ Yardımcı Fonksiyonlar Modülü
Zaman, dosya işlemleri ve güvenli dönüşümler için kullanılır.
"""
import asyncio
import aiohttp
import json
import os
from datetime import datetime
from functools import wraps

def time_now(fmt="%Y-%m-%d %H:%M:%S"):
    return datetime.utcnow().strftime(fmt)

def safe_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def async_retry(retries=3, delay=2, allowed_exceptions=(Exception,)):
    """
    ⚙️ Asenkron tekrar deneme dekoratörü
    Hatalı API veya ağ işlemlerinde fallback sağlar.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(1, retries + 1):
                try:
                    return await func(*args, **kwargs)
                except allowed_exceptions as e:
                    if attempt == retries:
                        raise
                    print(f"[{attempt}/{retries}] Hata: {e}, tekrar denenecek...")
                    await asyncio.sleep(delay)
        return wrapper
    return decorator
