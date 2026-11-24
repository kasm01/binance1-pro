"""Fail-closed MANUAL signal formatter and optional sender; no trading imports.

Default mode PREVIEW ONLY. Callers provide prevalidated signal decisions.
Even READY is advisory, never an exchange order, never proof of model edge.
"""
from __future__ import annotations
import math,os,re,time
from collections.abc import Mapping
from threading import Lock
SYMBOL=re.compile(r'^[A-Z0-9]{2,20}USDT$')
STRATEGY=re.compile(r'^(LONG|SHORT)[1-4]$')
STATES=frozenset({'WATCH','READY','INVALIDATED','TARGET_OBSERVED','STOP_OBSERVED'})
READY_REQUIRED=('signal_asof_verified','market_context_verified',
                'entry_confirmation_verified','cost_check_pass')
def _true(name):return str(os.getenv(name,'0')).lower() in ('1','true','yes','on')
def normalize(signal):
 if not isinstance(signal,Mapping):raise ValueError('signal mapping required')
 symbol=str(signal.get('symbol') or '').upper()
 strategy=str(signal.get('strategy') or '').upper()
 state=str(signal.get('state') or '').upper()
 if not SYMBOL.fullmatch(symbol) or not STRATEGY.fullmatch(strategy):
  raise ValueError('invalid symbol or strategy')
 if state not in STATES:raise ValueError('invalid signal state')
 if state=='READY' and any(signal.get(k) is not True for k in READY_REQUIRED):
  raise ValueError('READY requires verified closed-source and cost/entry evidence')
 observed=signal.get('observed_at_ms')
 if type(observed) is not int or observed<=0:raise ValueError('invalid timestamp')
 price=signal.get('price')
 if price is not None:
  try: price=float(price)
  except (ValueError,TypeError):raise ValueError('invalid price')
  if not math.isfinite(price) or price<=0:raise ValueError('invalid price')
 reason=str(signal.get('reason') or '').strip()
 if not reason or len(reason)>160 or any(c in reason for c in ('\n','\r')):
  raise ValueError('invalid reason')
 direction='LONG' if strategy.startswith('LONG') else 'SHORT'
 return {'symbol':symbol,'strategy':strategy,'direction':direction,
  'state':state,'observed_at_ms':observed,'price':price,'reason':reason,
  'advisory_only':True,'manual_only':True,'order_authorized':False}
def format_message(sig:Mapping)->str:
 x=normalize(sig)
 fmt_price='—' if x['price'] is None else f"{x['price']:.8g}"
 title={'READY':'🟢','WATCH':'🔎','INVALIDATED':'⛔',
        'TARGET_OBSERVED':'🎯','STOP_OBSERVED':'🛑'}[x['state']]
 return (f"{title} BINANCE1 · {x['strategy']} · {x['state']}\n"
  f"Coin: {x['symbol']} · Yön: {x['direction']}\n"
  f"Fiyat gözlemi: {fmt_price}\n"
  f"Gerekçe: {x['reason']}\n"
  f"Zaman (Unix ms): {x['observed_at_ms']}\n"
  "MANUEL İNCELEME · OTOMATİK EMİR YOK\n"
  "Bu bir işlem gerçekleşmesi veya kesin getiri bildirimi değildir.")
class SignalDispatcher:
 def __init__(self, sender=None, *,cooldown_s=900,bot_allocations=None):
  if cooldown_s<0:raise ValueError('negative cooldown')
  self.sender=sender;self.cooldown_s=cooldown_s
  self.bot_allocations=bot_allocations or {}
  self.seen={};self.lock=Lock()
 def dispatch(self,signal,*,now_ms=None):
  x=normalize(signal)
  now=int(time.time()*1000) if now_ms is None else now_ms
  if type(now) is not int or now<=0 or x['observed_at_ms']>now+1000:
   return 'INVALID_TIMESTAMP'
  # Do not send weeks-old signals because a VM restarted.
  if now-x['observed_at_ms']>120000:return 'STALE'
  text=format_message(signal)
  if not(_true('TELEGRAM_SIGNAL_CENTER_ENABLED') and
         _true('TELEGRAM_SIGNAL_CENTER_SEND_ENABLED')):
   return 'PREVIEW_ONLY'
  if x['symbol'] not in self.bot_allocations.get(x['strategy'],()):
   return 'SYMBOL_NOT_ALLOCATED_TO_STRATEGY'
  if not self.sender:return 'NO_SENDER'
  key=(x['strategy'],x['symbol'])
  with self.lock:
   previous=self.seen.get(key)
   if previous and previous[0]==x['state'] and now-previous[1]<self.cooldown_s*1000:
    return 'DEDUPED'
   # Mark only after a successful send response.
   try:
    sent=self.sender(text)
   except Exception:
    return 'SEND_FAILED'
   if sent is not True:return 'SEND_NOT_CONFIRMED'
   self.seen[key]=(x['state'],now)
   return 'SENT'
