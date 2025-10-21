# telegram/commands.py
from telegram import Update
from telegram.ext import CallbackContext

class CommandHandler:
    """
    Telegram bot komutlarını yönetir
    """
    def __init__(self, bot, dispatcher):
        self.bot = bot
        self.dispatcher = dispatcher

    def register_commands(self):
        self.dispatcher.add_handler(CallbackContext.dispatcher.add_handler(
            telegram.ext.CommandHandler("start", self.start_command)))
        self.dispatcher.add_handler(CallbackContext.dispatcher.add_handler(
            telegram.ext.CommandHandler("status", self.status_command)))

    def start_command(self, update: Update, context: CallbackContext):
        update.message.reply_text("Binance1-Pro botuna hoş geldiniz!")

    def status_command(self, update: Update, context: CallbackContext):
        # Burada performans ve sistem durumu bilgisi gönderilebilir
        update.message.reply_text("Bot çalışıyor. Performans raporu hazır!")
