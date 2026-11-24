"""Explicit opt-in verified Telegram HTTP delivery for MANUAL signal center.

No network until both signal-center env flags are on. Response checked.
No logging or returning bot token, no hidden retries and no orders.
"""
from __future__ import annotations
import os
import requests
from tg_bot.read_only_commands_v1 import allowed_ids
def enabled():
 return (os.getenv('TELEGRAM_SIGNAL_CENTER_ENABLED','0')=='1' and
         os.getenv('TELEGRAM_SIGNAL_CENTER_SEND_ENABLED','0')=='1')
def send(text,*,post=None)->bool:
 if not enabled():return False
 token=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
 chat=(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
 try:chat_id=int(chat)
 except ValueError:return False
 allowed=allowed_ids(os.getenv('TELEGRAM_ALLOWED_CHAT_IDS') or chat)
 if not token or chat_id not in allowed or not text or len(text)>3800:return False
 post=post or requests.post
 try:
  resp=post('https://api.telegram.org/bot'+token+'/sendMessage',
   data={'chat_id':str(chat_id),'text':text,'disable_web_page_preview':'true'},
   timeout=6)
  if resp.status_code!=200:return False
  data=resp.json()
  return data.get('ok') is True and isinstance(data.get('result'),dict)
 except (requests.RequestException,ValueError,TypeError,AttributeError):
  return False
