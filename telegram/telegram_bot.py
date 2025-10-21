# telegram/telegram_bot.py
from telegram import Bot
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram.ext import MessageHandler, Filters
from .commands import CommandHandler as BotCommandHandler

class TelegramBot:
    """
    Telegram bot başlatma ve yönetimi
    """
    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self.updater = Updater(token=token, use_context=True)
        self.dispatcher = self.updater.dispatcher
        self.command_handler = BotCommandHandler(self.bot, self.dispatcher)

    def start(self):
        # Komutları ekle
        self.command_handler.register_commands()
        # Botu başlat
        self.updater.start_polling()
        self.updater.idle()
