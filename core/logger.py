# core/logger.py
import logging
import os
from logging.handlers import RotatingFileHandler
from config.settings import Settings

def setup_logger(name: str = "Binance1Pro", level: str = Settings.LOG_LEVEL):
    """
    Uygulama genelinde kullanılacak logger nesnesi oluşturur.
    """
    log_dir = os.path.join(Settings.BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"{name.lower()}.log")

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=5)
    handler.setFormatter(formatter)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.addHandler(console)

    return logger

# Global logger
logger = setup_logger()
