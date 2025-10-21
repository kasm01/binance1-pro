# core/exceptions.py
"""
📛 Hata Yönetimi Modülü
Bot içerisindeki özel hata türlerini tanımlar.
"""

class BotError(Exception):
    """Genel bot hatası"""
    pass

class NetworkError(BotError):
    """Ağ bağlantı hatası"""
    pass

class TradeExecutionError(BotError):
    """Emir gönderme / yürütme hatası"""
    pass

class ModelError(BotError):
    """Makine öğrenimi model hatası"""
    pass

class CacheError(BotError):
    """Önbellek hatası"""
    pass
