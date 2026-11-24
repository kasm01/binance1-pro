"""Manual WATCH forward excursion observability, never a trade/backtest fill.

Records signal at LAST CLOSED candle's close; forward paths include only
subsequently closed, exact-sequence 1m OHLC. MFE/MAE use highs/lows
as path extrema, NOT executable exits or ROI. No future peeking.
Persistence is bounded, atomic, private and fail-closed on corruption.
"""
from __future__ import annotations
import json,os
from pathlib import Path
from scanner.extreme_momentum_v1 import MS,number
HORIZONS=(5,15,30,60)
MAX_EVENTS=1000
MAX_PENDING=200
MAX_BYTES=1_000_000

def evaluate_path(event,bars,*,horizon):
 if horizon not in HORIZONS:raise ValueError('unsupported horizon')
 start=event['reference_close_ms']
 end=start+horizon*MS
 selected=[b for b in bars if start<=b['t']<end]
 if len(selected)!=horizon:
  return None
 if any(b['t']!=start+i*MS for i,b in enumerate(selected)):
  return None
 ref=event['reference_price']
 if not isinstance(ref,(int,float)) or ref<=0:return None
 highs=[number(b.get('h')) for b in selected]
 lows=[number(b.get('l')) for b in selected]
 closes=[number(b.get('c')) for b in selected]
 if None in highs+lows+closes or min(lows)<=0 or any(l>h for l,h in zip(lows,highs)):
  return None
 sign=1 if event['direction']=='LONG' else -1
 favorable=(max(highs)/ref-1)*100 if sign==1 else (1-min(lows)/ref)*100
 adverse=(min(lows)/ref-1)*100 if sign==1 else (1-max(highs)/ref)*100
 terminal=sign*(closes[-1]/ref-1)*100
 # Values are price path high/low best-case not simultaneous or fill-realizable.
 return {'horizon_min':horizon,'mfe_pct':round(favorable,4),
         'mae_pct':round(adverse,4),'terminal_directional_pct':round(terminal,4),
         'path_source':'closed_1m_high_low',
         'not_fill_or_ROI':True}

class OutcomeLedger:
 def __init__(self,path,*,episode_cooldown_ms=60*MS):
  self.path=Path(path)
  self.episode_cooldown_ms=episode_cooldown_ms
  self.events=[]
  self.healthy=True
  if self.path.exists():
   try:
    if self.path.stat().st_size>MAX_BYTES:raise ValueError('oversized state')
    obj=json.loads(self.path.read_text(encoding='utf8'))
    if obj.get('schema')!='manual_watch_outcomes_v1' or not isinstance(obj.get('events'),list):
     raise ValueError('corrupt schema')
    if len(obj['events'])>MAX_EVENTS:raise ValueError('too many events')
    for event in obj['events']:
     self._validate(event)
    self.events=obj['events']
   except (ValueError,OSError,TypeError,AttributeError,KeyError):
    self.healthy=False
 def _validate(self,event):
  if not isinstance(event,dict):raise ValueError('bad event')
  if not isinstance(event.get('symbol'),str) or not event['symbol'].endswith('USDT'):
   raise ValueError('bad symbol')
  if event.get('direction') not in ('LONG','SHORT'):raise ValueError('bad direction')
  if type(event.get('reference_close_ms')) is not int or event['reference_close_ms']<=0:
   raise ValueError('bad ref timestamp')
  if event['reference_close_ms']%MS:raise ValueError('unaligned ref timestamp')
  ref=number(event.get('reference_price'))
  if ref is None or ref<=0:raise ValueError('bad reference price')
  if not isinstance(event.get('outcomes'),dict):raise ValueError('invalid outcome map')
 def _persist(self):
  if not self.healthy:return False
  try:
   self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
   os.chmod(self.path.parent,0o700)
   new={'schema':'manual_watch_outcomes_v1','events':self.events[-MAX_EVENTS:]}
   blob=json.dumps(new,separators=(',',':'),sort_keys=True,ensure_ascii=False)
   if len(blob.encode())>MAX_BYTES:raise ValueError('state too large')
   temp=self.path.with_suffix('.tmp')
   with temp.open('w',encoding='utf8') as f:f.write(blob)
   os.chmod(temp,0o600)
   os.replace(temp,self.path)
   return True
  except (OSError,ValueError):
   self.healthy=False
   return False
 def observe(self,symbol,direction,scanner,context,*,reference_close_ms,reference_price):
  if not self.healthy:return 'LEDGER_UNAVAILABLE'
  if len(self.events)>=MAX_EVENTS:
   return 'CAPACITY_REACHED'
  if sum(not e.get('final') for e in self.events)>=MAX_PENDING:
   return 'PENDING_CAP_REACHED'
  if direction not in ('LONG','SHORT') or scanner.get('status') not in ('STRONG_WATCH','EXTREME_WATCH'):
   return 'NOT_STRONG_WATCH'
  if (scanner.get('direction')!=direction or scanner.get('last_completed_1m_close_ms')!=reference_close_ms
      or scanner.get('telegram_ready') is not False or scanner.get('order_authorized') is not False):
   return 'SOURCE_UNVERIFIED'
  if type(reference_close_ms) is not int or reference_close_ms%MS:return 'SOURCE_UNVERIFIED'
  price=number(reference_price)
  if price is None or price<=0:return 'SOURCE_UNVERIFIED'
  if any(e['symbol']==symbol and e['direction']==direction and
         0<=reference_close_ms-e['reference_close_ms']<self.episode_cooldown_ms
         for e in self.events):
   return 'EPISODE_DEDUPED'
  self.events.append({'symbol':symbol,'direction':direction,
   'reference_close_ms':reference_close_ms,
   'reference_price':price,'watch_status':scanner['status'],
   'context_state':context.get('state','UNKNOWN'),
   'context_reason':context.get('reason','UNKNOWN'),
   'outcomes':{},'final':False,'invalid_reason':None,
   'manual_only':True,'trade_executed':False})
  if not self._persist():return 'LEDGER_WRITE_FAILED'
  return 'OBSERVED'
 def observe_early(self,symbol,direction,early,*,
                   reference_close_ms,reference_price,flow=None):
  """Separate SHADOW-only 3m early discovery, no Telegram and no orders."""
  if not self.healthy:return 'LEDGER_UNAVAILABLE'
  if len(self.events)>=MAX_EVENTS:
   return 'CAPACITY_REACHED'
  if sum(not e.get('final') for e in self.events)>=MAX_PENDING:
   return 'PENDING_CAP_REACHED'
  if not isinstance(early,dict) or early.get('state')!='EARLY_CANDIDATE_SHADOW':
   return 'NOT_EARLY_CANDIDATE'
  if (not isinstance(symbol,str) or not symbol.endswith('USDT') or
      direction not in ('LONG','SHORT') or early.get('direction')!=direction or
      early.get('symbol')!=symbol or
      early.get('last_completed_1m_close_ms')!=reference_close_ms or
      early.get('ready') is not False or
      early.get('telegram_ready') is not False or
      early.get('order_authorized') is not False or
      type(reference_close_ms) is not int or reference_close_ms%MS):
   return 'SOURCE_UNVERIFIED'
  price=number(reference_price)
  if price is None or price<=0:return 'SOURCE_UNVERIFIED'
  if flow is not None and (not isinstance(flow,dict) or
       flow.get('ready') is not False or flow.get('order_authorized') is not False):
   return 'FLOW_UNVERIFIED'
  if any(e['symbol']==symbol and e['direction']==direction and
         0<=reference_close_ms-e['reference_close_ms']<self.episode_cooldown_ms
         for e in self.events):
   return 'EPISODE_DEDUPED'
  self.events.append({'symbol':symbol,'direction':direction,
   'reference_close_ms':reference_close_ms,'reference_price':price,
   'watch_status':'EARLY_CANDIDATE_SHADOW',
   'context_state':'EARLY_UNCONFIRMED','context_reason':early.get('reason'),
   'outcomes':{},'final':False,'invalid_reason':None,'manual_only':True,
   'trade_executed':False,'telegram_sent':False,'early_shadow_only':True,
   'flow_shadow_state':flow.get('state','FLOW_NOT_CHECKED') if flow else 'FLOW_NOT_CHECKED',
   'flow_shadow_reason':flow.get('reason','not_checked') if flow else 'not_checked',
   'directional_taker_imbalance_3m':
      flow.get('directional_taker_imbalance_3m') if flow else None})
  if not self._persist():return 'LEDGER_WRITE_FAILED'
  return 'OBSERVED'

 def advance(self,symbol,bars,*,last_close_ms):
  """Only exact future closed bars, never bootstrap prefix classified as future
  without actual continuity. A gap invalidates pending episodes."""
  if not self.healthy:return 0
  if not bars:return 0
  changed=0
  for e in self.events:
   if e['symbol']!=symbol or e.get('final'):continue
   origin=e['reference_close_ms']
   if last_close_ms<=origin:continue
   for horizon in HORIZONS:
    key=str(horizon)
    if key in e['outcomes']:continue
    if last_close_ms<origin+horizon*MS:continue
    outcome=evaluate_path(e,bars,horizon=horizon)
    if outcome is None:
     e['invalid_reason']='missing_or_discontinuous_future_bars'
     e['final']=True
     changed+=1
     break
    e['outcomes'][key]=outcome
    changed+=1
   if len(e['outcomes'])==len(HORIZONS):
    e['final']=True
  if changed and not self._persist():return -1
  return changed
 def revalidate_early(self,symbol,bars,*,last_close_ms):
  # Separate checkpoint history; do not replace or modify existing
  # outcome MFE/MAE logic, and never send Telegram/READY.
  from scanner.early_revalidation_shadow_v1 import CHECKPOINTS,revalidate
  if not self.healthy or not isinstance(bars,list):return 0
  changed=0
  for e in self.events:
   if (e['symbol']!=symbol or e.get('watch_status')!='EARLY_CANDIDATE_SHADOW'
       or e.get('invalid_reason')):continue
   checks=e.setdefault('revalidation_checkpoints',{})
   for point in CHECKPOINTS:
    key=str(point)
    if key in checks or last_close_ms<e['reference_close_ms']+point*MS:continue
    result=revalidate(e,bars,checkpoint=point)
    # Do not write invented checkpoint results if history is absent;
    # explicitly record invalid provenance so absence can be audited.
    checks[key]=result
    changed+=1
  if changed and not self._persist():return -1
  return changed

 def invalidate_symbol(self,symbol,reason):
  if not self.healthy:return False
  changes=0
  for e in self.events:
   if e['symbol']==symbol and not e.get('final'):
    e['final']=True
    e['invalid_reason']=reason
    changes+=1
  return not changes or self._persist()
 def invalidate_missing(self,symbols,reason):
  if not self.healthy:return False
  allowed=set(symbols)
  changed=0
  for e in self.events:
   if e['symbol'] not in allowed and not e.get('final'):
    e['final']=True;e['invalid_reason']=reason;changed+=1
  return not changed or self._persist()
 def summary(self):
  recent=self.events[-MAX_EVENTS:]
  return {'outcome_events_recorded':len(recent),
   'outcome_events_complete':sum(bool(e.get('final')) and not e.get('invalid_reason') for e in recent),
   'outcome_events_pending':sum(not e.get('final') for e in recent),
   'outcome_events_invalid':sum(bool(e.get('invalid_reason')) for e in recent),
   'outcome_ledger_healthy':self.healthy,
   'evaluation_horizons_min':list(HORIZONS),
   'real_trades':0,'ready_signals':0}
