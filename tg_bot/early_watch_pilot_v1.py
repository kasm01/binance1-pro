"""Explicit-opt-in research EARLY WATCH Telegram sender for 40-coin signal bus.

All 8 assigned direction modules may issue early observations; no READY,
execution, order APIs, or account keys. Closed 1m and taker flow required.
Separate persistence and global anti-spam caps from strong WATCH.
"""
from __future__ import annotations
import json,os,time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from tg_bot.transport_v1 import enabled as telegram_enabled

ALLOWED_FLOW=frozenset({'FLOW_SUPPORTIVE','FLOW_MIXED'})
COOLDOWN_MS=120*60_000
GLOBAL_GAP_MS=3*60_000
HOURLY_CAP=6
HISTORY_MS=COOLDOWN_MS
MAX_STATE_BYTES=50000
IST=ZoneInfo('Europe/Istanbul')

def _base(result):
 return {'delivery':result,'ready':False,'order_authorized':False}

def eligibility(symbol,direction,early,flow,allocations,*,now_ms):
 """Return the assigned bot, or None. Never promote to READY."""
 if not isinstance(symbol,str) or not symbol.endswith('USDT') or direction not in ('LONG','SHORT'):
  return None
 if not isinstance(allocations,dict) or not isinstance(early,dict) or not isinstance(flow,dict):
  return None
 if (early.get('state')!='EARLY_CANDIDATE_SHADOW' or
     early.get('symbol')!=symbol or early.get('direction')!=direction or
     early.get('ready') is not False or early.get('telegram_ready') is not False or
     early.get('order_authorized') is not False or
     type(now_ms) is not int or
     type(early.get('last_completed_1m_close_ms')) is not int or
     not 0<=now_ms-early['last_completed_1m_close_ms']<=30_000):
  return None
 if (flow.get('state') not in ALLOWED_FLOW or
     flow.get('ready') is not False or flow.get('telegram_ready') is not False or
     flow.get('order_authorized') is not False):
  return None
 for i in range(1,5):
  bot=f'{direction}{i}'
  if symbol in allocations.get(bot,()):
   return bot
 return None

def format_early(symbol,direction,bot,early,flow,price,*,now_ms):
 """Advisory-only; always explicitly distinguishes discovery from entry."""
 dt=datetime.fromtimestamp(now_ms/1000,tz=IST).strftime('%d.%m.%Y %H:%M:%S')
 flow_text={'FLOW_SUPPORTIVE':'Taker baskısı hareket yönünde',
            'FLOW_MIXED':'Taker baskısı karışık'}[flow['state']]
 return (f'🟡 BINANCE1 · ERKEN İZLEME · {bot}\n'
   f'Coin: {symbol} · Yön: {direction}\n'
   f'Son kapanış: {price:.8g}\n'
   f'3 dk değişim: {early["ret3_pct"]:+.2f}%\n'
   f'5 dk değişim: {early["ret5_pct"]:+.2f}% · 15 dk: {early["ret15_pct"]:+.2f}%\n'
   f'Hacim (3 dk): {early["volume_ratio3"]:.2f}x\n'
   f'Akış: {flow_text}\n'
   f'Zaman (Türkiye): {dt}\n'
   '⚠️ ERKEN GÖZLEM — YÜKSEK TERS DÖNÜŞ RİSKİ\n'
   'GİRİŞ ONAYI / READY DEĞİL · MANUEL KONTROL\n'
   'Otomatik Binance emri YOK. Komisyon ve stop/target onayı YOK.')

class EarlyWatchDispatcher:
 def __init__(self,path,*,sender):
  self.path=Path(path)
  self.sender=sender
  self.healthy=True
  self.sent=[]
  if self.path.exists():
   try:
    if self.path.stat().st_size>MAX_STATE_BYTES:raise ValueError('state too large')
    obj=json.loads(self.path.read_text(encoding='utf-8'))
    if obj.get('schema')!='early_watch_telegram_v1' or not isinstance(obj.get('sent'),list):
     raise ValueError('invalid state')
    if len(obj['sent'])>400:raise ValueError('too many events')
    for x in obj['sent']:
     if (not isinstance(x,dict) or not isinstance(x.get('symbol'),str)
         or not x['symbol'].endswith('USDT') or
         x.get('direction') not in ('LONG','SHORT') or
         type(x.get('at_ms')) is not int or x['at_ms']<=0):
      raise ValueError('bad event')
    self.sent=obj['sent']
   except (OSError,ValueError,TypeError,KeyError,AttributeError):
    self.healthy=False
 def _persist(self,now_ms):
  try:
   self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
   os.chmod(self.path.parent,0o700)
   payload={'schema':'early_watch_telegram_v1',
            'sent':[x for x in self.sent if 0<=now_ms-x['at_ms']<HISTORY_MS][-400:]}
   temp=self.path.with_suffix('.tmp')
   temp.write_text(json.dumps(payload,separators=(',',':'),sort_keys=True),encoding='utf-8')
   os.chmod(temp,0o600)
   os.replace(temp,self.path)
   return True
  except OSError:return False
 def send_early(self,symbol,direction,early,flow,allocations,price,*,now_ms):
  if os.getenv('TELEGRAM_EARLY_WATCH_ENABLED')!='1' or not telegram_enabled():
   return 'PREVIEW_ONLY'
  if not self.healthy:return 'PERSISTENCE_UNAVAILABLE'
  bot=eligibility(symbol,direction,early,flow,allocations,now_ms=now_ms)
  if bot is None:return 'EARLY_FILTERED'
  try:
   price=float(price)
   import math
   if not math.isfinite(price) or price<=0:return 'INVALID_PRICE'
   now_real=int(time.time()*1000)
   if abs(now_real-now_ms)>120_000:return 'STALE_OR_CLOCK_SKEW'
   if any(x['symbol']==symbol and x['direction']==direction and
          0<=now_ms-x['at_ms']<COOLDOWN_MS for x in self.sent):
    return 'DEDUPED'
   past=[x for x in self.sent if 0<=now_ms-x['at_ms']<60*60_000]
   if len(past)>=HOURLY_CAP:return 'GLOBAL_HOURLY_LIMIT'
   if past and now_ms-max(x['at_ms'] for x in past)<GLOBAL_GAP_MS:
    return 'GLOBAL_3MIN_GAP'
   required=('ret3_pct','ret5_pct','ret15_pct','volume_ratio3')
   if any(not isinstance(early.get(k),(float,int)) for k in required):
    return 'INVALID_METRICS'
   text=format_early(symbol,direction,bot,early,flow,price,now_ms=now_ms)
   if self.sender(text) is not True:return 'SEND_NOT_CONFIRMED'
   self.sent.append({'symbol':symbol,'direction':direction,'at_ms':now_ms})
   if not self._persist(now_ms):
    self.healthy=False
    return 'SENT_PERSIST_FAILED'
   return 'SENT'
  except Exception:
   return 'SEND_FAILED'
