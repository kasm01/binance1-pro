"""Read-only public replay for previously API-confirmed Telegram early messages."""
from __future__ import annotations
import json,requests
from pathlib import Path
from scanner.shared_market_snapshot_v1 import parse_closed_klines
from scanner.early_revalidation_shadow_v1 import revalidate,CHECKPOINTS
from scanner.extreme_momentum_v1 import MS

def main():
 src=json.loads(Path('research/results/BINANCE1_CONFIRMED_TELEGRAM_FORWARD_AUDIT_20261124.json').read_text())
 events=[x for x in src['events'] if x['kind']=='EARLY']
 ses=requests.Session()
 now=int(ses.get('https://fapi.binance.com/fapi/v1/time',timeout=8).json()['serverTime'])
 report=[]
 for event in events:
  sym=event['symbol'];t=event['reference_close_ms']
  resp=ses.get('https://fapi.binance.com/fapi/v1/klines',params={
   'symbol':sym,'interval':'1m','startTime':t-160*MS,
   'endTime':min(now,t+7*MS),'limit':180},timeout=8)
  resp.raise_for_status()
  rows=parse_closed_klines(resp.json(),asof_ms=now)
  origin={'symbol':sym,'direction':event['direction'],
   'reference_close_ms':t,'reference_price':event['reference_price']}
  checkpoints={str(i):revalidate(origin,rows,checkpoint=i) for i in CHECKPOINTS}
  report.append({'symbol':sym,'direction':event['direction'],
   'signal_time_tr':event['signal_time_tr'],'reference_price':event['reference_price'],
   'checkpoints':checkpoints})
 result={'schema':'confirmed_early_revalidation_replay_v1',
  'candidate_count':len(report),'rest_requests':1+len(report),
  'note':'Retrospective closed 1m snapshots at each checkpoint; no Telegram action, fills, fees or auto orders',
  'events':report,'real_trades':0,'ready_count':0}
 target=Path('research/results/BINANCE1_CONFIRMED_EARLY_1_3_5_REVALIDATION_20261124.json')
 target.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+'\n')
 for e in report:
  print(e['signal_time_tr'],e['symbol'],e['direction'],
   [(k,v['state'],v['reason'],v.get('directional_terminal_pct'),v.get('adverse_excursion_pct'),v.get('flow_state'))
    for k,v in e['checkpoints'].items()])
 print('TOTAL',len(report),'REST_REQUESTS',1+len(report))
if __name__=='__main__':main()
