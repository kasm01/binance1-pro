"""One-shot public Binance USD-M 40-coin selection, explicit opt-in.

No Binance API key, no orders, no services, no persistent sensitive data.
No API requests without --fetch-public.
"""
from __future__ import annotations
import argparse,json,sys
from scanner.universe_40_v1 import select
def main():
 p=argparse.ArgumentParser()
 p.add_argument('--fetch-public',action='store_true')
 p.add_argument('--min-volume-usdt',type=float,default=5_000_000)
 a=p.parse_args()
 if not a.fetch_public:
  print('DISABLED: requires explicit --fetch-public; no HTTP by default')
  return 0
 if not 0<=a.min_volume_usdt<=1e12:p.error('invalid min volume')
 import requests
 try:
  base='https://fapi.binance.com'
  e=requests.get(base+'/fapi/v1/exchangeInfo',timeout=7)
  e.raise_for_status()
  t=requests.get(base+'/fapi/v1/ticker/24hr',timeout=7)
  t.raise_for_status()
  obj=select(e.json(),t.json(),min_quote_volume_usdt=a.min_volume_usdt)
  print(json.dumps(obj,ensure_ascii=False,sort_keys=True))
 except (requests.RequestException,ValueError,TypeError) as err:
  print('PUBLIC_MARKET_DATA_UNAVAILABLE: '+type(err).__name__)
  return 2
 return 0
if __name__=='__main__':raise SystemExit(main())
