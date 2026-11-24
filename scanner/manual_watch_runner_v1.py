"""Standalone opt-in 40-coin market WATCH runner, no Binance trading API.

Pure public REST bootstraps 70 1m bars / coin, then one multiplexed
Binance Futures websocket for up to 40 symbols. Only closed x=true
1m klines accepted. Status JSON local. Telegram intentionally NOT wired;
no execution import; no systemd auto enable.

Usage:
 PYTHONPATH=. python scanner/manual_watch_runner_v1.py --once-public --limit 10
 PYTHONPATH=. python scanner/manual_watch_runner_v1.py --live --max-seconds 30 --limit 10
Only --live with --max-seconds 0 runs indefinitely, foreground only.
"""
from __future__ import annotations
import argparse,asyncio,json,os,time
from pathlib import Path
from scanner.closed_bar_bus_v1 import ClosedBarBus
from scanner.universe_extreme_overlay_v1 import select_movers

BASE='https://fapi.binance.com'
WS='wss://fstream.binance.com/market/stream?streams='
ROOT=Path(__file__).resolve().parents[1]
STATUS=ROOT/'run/signal_center/status.json'
def fetch_public(session,path,params=None):
 res=session.get(BASE+path,params=params,timeout=10)
 res.raise_for_status()
 return res.json()
def make_universe(session,limit):
 now=int(fetch_public(session,'/fapi/v1/time')['serverTime'])
 u=select_movers(fetch_public(session,'/fapi/v1/exchangeInfo'),
                 fetch_public(session,'/fapi/v1/ticker/24hr'))
 chosen=u['unique_symbols'][:limit]
 allocations={bot:[s for s in syms if s in chosen]
              for bot,syms in u['bot_allocations'].items()}
 return now,u,chosen,allocations
def bootstrap(session,bus,chosen,clock_offset_ms):
 for symbol in chosen:
  try:
   k=fetch_public(session,'/fapi/v1/klines',
    {'symbol':symbol,'interval':'1m','limit':80})
   # Re-evaluate observation clock AFTER the HTTP response:
   # fetching 40 symbols can cross one or more minute boundaries.
   # Offset is calibrated to public Binance server clock.
   bus.bootstrap(symbol,k,asof_ms=int(time.time()*1000)+clock_offset_ms)
  except (ValueError,KeyError,TypeError):
   bus.rejections[symbol]='BOOTSTRAP_FAILED'
   bus.data[symbol].clear()
  except Exception:
   bus.rejections[symbol]='BOOTSTRAP_UNAVAILABLE'
   bus.data[symbol].clear()
 return bus.stats()
def watch_rows(bus,allocations,asof_ms):
 rows=[];result=[]
 for symbol in bus.data:
  x=bus.analyze(symbol,asof_ms=asof_ms)
  if x.get('status') not in ('WATCH','STRONG_WATCH','EXTREME_WATCH',
                           'EXTREME_CAUTION_WATCH'):continue
  direction=x['direction']
  bots=[bot for bot,syms in allocations.items()
        if bot.startswith(direction) and symbol in syms]
  if not bots:continue
  result.append({'symbol':symbol,'strategy':bots[0],
   'direction':direction,'status':x['status'],
   'reason':x.get('reason'),'ret15_pct':x.get('ret15_pct'),
   'observed_at_ms':asof_ms})
 return result
def make_status(bus,allocations,now,universe):
 return {'schema':'manual_signal_center_status.v1',
  'manual_only':True,'order_authorized':False,
  'telegram_sent':False,'updated_at_ms':now,
  'selected_symbols':list(bus.data),
  'bot_allocations':allocations,
  'excluded_first15':universe['excluded_top_volume_15'],
  'market_cache':bus.stats(),
  'last_signals':watch_rows(bus,allocations,now)[-10:]}
def atomic_status(payload,path=STATUS):
 path.parent.mkdir(parents=True,exist_ok=True)
 os.chmod(path.parent,0o700)
 temp=path.with_suffix('.tmp')
 with temp.open('w',encoding='utf8') as f:
  json.dump(payload,f,ensure_ascii=False,sort_keys=True)
 os.chmod(temp,0o600)
 os.replace(temp,path)
def run_once(*,limit,persist=False):
 import requests
 with requests.Session() as session:
  now,u,symbols,alloc=make_universe(session,limit)
  bus=ClosedBarBus(symbols)
  clock_offset_ms=now-int(time.time()*1000)
  stats=bootstrap(session,bus,symbols,clock_offset_ms)
  result=make_status(bus,alloc,int(time.time()*1000)+clock_offset_ms,u)
  if persist:atomic_status(result)
  return {'count':len(symbols),'readable':stats['valid_symbols'],
   'watch':result['last_signals'],'raw_watch_count':len(result['last_signals']),
   'public_rest_calls':3+len(symbols),'orders':0,'telegram_sent':False,
   'persisted':persist}
async def live(*,limit,max_seconds):
 import requests,websockets
 from websockets.exceptions import ConnectionClosed
 started=time.monotonic()
 with requests.Session() as session:
  now,u,symbols,alloc=make_universe(session,limit)
  if not symbols:raise RuntimeError('no eligible symbols')
  bus=ClosedBarBus(symbols)
  clock_offset_ms=now-int(time.time()*1000)
  bootstrap(session,bus,symbols,clock_offset_ms)
  atomic_status(make_status(bus,alloc,int(time.time()*1000)+clock_offset_ms,u))
  stream=WS+'/'.join(s.lower()+'@kline_1m' for s in symbols)
  backoff=1
  refresh_deadline=time.monotonic()+1800
  last_healthy_packet=time.monotonic()
  last_status_write=time.monotonic()
  total=0;accepted=0;watch=0;reconnects=0
  # Telegram transport remains inert unless BOTH explicit signal-center
  # flags are on. No READY or trading order can emerge from this runner.
  from tg_bot.signal_center_v1 import SignalDispatcher
  from tg_bot.transport_v1 import send as telegram_send
  dispatcher=SignalDispatcher(sender=telegram_send,bot_allocations=alloc)
  print(json.dumps({'event':'STARTED','symbols':len(symbols),
    'source':'ONE_MULTIPLEXED_WS','orders':0,'telegram':0}),flush=True)
  while max_seconds==0 or time.monotonic()-started<max_seconds:
   try:
    # Disconnect and revisit eligibility hourly, never reuse outdated
    # list with a fresh WATCH after a complete stale interval.
    async with websockets.connect(stream,open_timeout=10,close_timeout=5,
                                  ping_interval=20,ping_timeout=20,max_size=250000) as conn:
     backoff=1
     while max_seconds==0 or time.monotonic()-started<max_seconds:
      if time.monotonic()>=refresh_deadline:
       raise asyncio.TimeoutError('scheduled 30m universe refresh')
      try:message=await asyncio.wait_for(conn.recv(),timeout=3)
      except asyncio.TimeoutError:
       if time.monotonic()-last_healthy_packet>15:
        raise asyncio.TimeoutError('websocket stalled: no public kline events')
       continue
      data=json.loads(message)
      event=data.get('data') if isinstance(data,dict) else None
      if not isinstance(event,dict) or event.get('e')!='kline':continue
      last_healthy_packet=time.monotonic()
      symbol=event.get('s')
      # Observe with source exchange event time, not untrusted bar timestamp.
      ts=event.get('E')
      if type(ts) is not int:continue
      total+=1
      result=bus.update_ws(symbol,event,observed_at_ms=ts)
      if result=='GAP_BLOCKED':
       # REST rebootstrap through isolated thread (bounded).
       await asyncio.to_thread(bootstrap,session,bus,[symbol],clock_offset_ms)
      if result=='CLOSED_ACCEPTED':
       accepted+=1
       x=bus.analyze(symbol,asof_ms=ts)
       if time.monotonic()-last_status_write>=45:
        atomic_status(make_status(bus,alloc,ts,u))
        last_status_write=time.monotonic()
       if x.get('status') not in ('STRONG_WATCH','EXTREME_WATCH','WATCH',
            'EXTREME_CAUTION_WATCH'):
        continue
       watch+=1
       bot=next((bot for bot,syms in alloc.items()
                 if bot.startswith(x.get('direction') or '?') and symbol in syms),None)
       delivery='NO_MATCHING_STRATEGY'
       if bot and x.get('status') in ('STRONG_WATCH','EXTREME_WATCH',
                                     'EXTREME_CAUTION_WATCH'):
        delivery=dispatcher.dispatch({
         'symbol':symbol,'strategy':bot,'state':'WATCH',
         'observed_at_ms':ts,
         'price':bus.data[symbol][-1]['c'],
         'reason':x['reason']+' / '+x['status']
        },now_ms=ts)
       print(json.dumps({'event':'WATCH_PREVIEW','symbol':symbol,
         'direction':x.get('direction'),'status':x['status'],
         'ret15_pct':x.get('ret15_pct'),
         'telegram_delivery':delivery,'orders':0}),flush=True)
      elif result in ('GAP_BLOCKED','FUTURE_OR_STALE_CLOSE','BAD_CANDLE'):
       atomic_status(make_status(bus,alloc,ts,u))
   except (OSError,ConnectionClosed,asyncio.TimeoutError,ValueError) as e:
    reconnects+=1
    if max_seconds and time.monotonic()-started>=max_seconds:break
    # Crucial: an outage invalidates snapshot continuity. Rebootstrap
    # all 40, and select fresh symbols after reconnect.
    try:
     now,u,symbols,alloc=await asyncio.to_thread(make_universe,session,limit)
     bus=ClosedBarBus(symbols)
     clock_offset_ms=now-int(time.time()*1000)
     await asyncio.to_thread(bootstrap,session,bus,symbols,clock_offset_ms)
     stream=WS+'/'.join(s.lower()+'@kline_1m' for s in symbols)
     dispatcher.bot_allocations=alloc
     refresh_deadline=time.monotonic()+1800
     last_healthy_packet=time.monotonic()
     atomic_status(make_status(bus,alloc,int(time.time()*1000)+clock_offset_ms,u))
    except Exception:
     for symbol in bus.data:bus.rejections[symbol]='RECONNECT_SOURCE_UNVERIFIED'
    await asyncio.sleep(min(backoff,8))
    backoff=min(8,backoff*2)
  print(json.dumps({'event':'STOPPED','symbols':len(symbols),
   'messages_received':total,'closed_bars_accepted':accepted,
   'watch_events':watch,'reconnects':reconnects,
   'telegram_sent':0,'orders':0}),flush=True)
def main():
 p=argparse.ArgumentParser()
 mode=p.add_mutually_exclusive_group(required=True)
 mode.add_argument('--once-public',action='store_true')
 mode.add_argument('--live',action='store_true')
 p.add_argument('--limit',type=int,default=10)
 p.add_argument('--max-seconds',type=int,default=30)
 p.add_argument('--write-status',action='store_true')
 a=p.parse_args()
 if not (1<=a.limit<=40):p.error('limit must be 1..40')
 if not (0<=a.max_seconds<=86400):p.error('invalid timeout')
 if a.once_public:
  print(json.dumps(run_once(limit=a.limit,persist=a.write_status)),flush=True)
 else:
  asyncio.run(live(limit=a.limit,max_seconds=a.max_seconds))
if __name__=='__main__':main()
