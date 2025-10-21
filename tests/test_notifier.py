# tests/test_notifier.py
import unittest
from telegram.telegram_bot import TelegramBot

class TestNotifier(unittest.TestCase):

    def test_message_formatting(self):
        from telegram.message_formatter import MessageFormatter
        msg = MessageFormatter.format_alert("Test Alert", level="ALERT")
        self.assertIn("⚠️", msg)

if __name__ == "__main__":
    unittest.main()
