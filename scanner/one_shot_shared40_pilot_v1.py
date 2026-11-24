"""One-shot public Binance REST pilot, strictly opt-in and bounded.

Default: no HTTP, no Telegram, no writes. --fetch-public connects only
to Binance public USD-M market-data endpoints, 2 metadata + up to 10
unique 1m kline requests, then prints small summary.
Never launches background scanner or trading services.
"""
from __future__ import annotations
import argparse,json,time
from scanner.universe_extreme_overlay_v1 import select_movers
from scanner.shared_market_snapshot_v1 import evaluate
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--fetch-public',action='store_true')
 ap.add_argument('--limit',type=int,default=10)
 a=ap.parse_args()
 if not a.fetch_public:
  print('DISABLED: --fetch-public required; no HTTP, no Telegram')
  return 0
 if not 1<=a.limit<=10:ap.error('pilot --limit must be 1..10')
 import requests
 base='https://fapi.binance.com'
 sess=requests.Session()
 try:
  def get(path,params=None):
   resp=sess.get(base+path,params=params,timeout=8)
   resp.raise_for_status()
   return resp.json()
  # Exchange server clock, not local VM clock as source proof.
  observed=int(get('/fapi/v1/time')['serverTime'])
  e=get('/fapi/v1/exchangeInfo')
  tick=get('/fapi/v1/ticker/24hr')
  universe=select_movers(e,tick)
  selected=universe['unique_symbols'][:a.limit]
  # Reduced pilot assignments, no undocumented phantom symbols
  allocation={k:[s for s in v if s in selected]
              for k,v in universe['bot_allocations'].items()}
  raw={}
  for symbol in selected:
   raw[symbol]=get('/fapi/v1/klines',
    {'symbol':symbol,'interval':'1m','limit':70})
  # Bound asof by server time used before data collection: may reject bars
  # completed after that time, an intentionally conservative choice.
  snapshot=evaluate(selected_symbols=selected,bot_allocations=allocation,
   klines_by_symbol=raw,observed_at_ms=observed,
   universe_time_ms=observed)
  sample={k:{'status':v['status'],'direction':v.get('direction'),
      'reason':v.get('reason'),'ret15_pct':v.get('ret15_pct')}
      for k,v in snapshot['per_symbol'].items()}
  print(json.dumps({'schema':snapshot['schema'],'real_public_market_data':True,
   'strictly_single_run':True,'selected_symbols':selected,
   'excluded_first_15':universe['excluded_top_volume_15'],
   'sample':sample,
   'watch_candidates_by_direction':snapshot['watch_candidates_by_direction'],
   'api_calls':3+len(selected),'telegram_messages_sent':0,
   'binance_orders_sent':0},sort_keys=True))
 except (requests.RequestException,ValueError,TypeError,KeyError) as err:
  print('PUBLIC_PILOT_UNAVAILABLE: '+type(err).__name__)
  return 2
 finally:sess.close()
 return 0
if __name__=='__main__':raise SystemExit(main())
