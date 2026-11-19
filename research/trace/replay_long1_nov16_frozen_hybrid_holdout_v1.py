"""16 Nov frozen candidate only. Do not change entries or stage settings."""
from pathlib import Path
from zipfile import ZipFile
from io import TextIOWrapper
from datetime import datetime
from collections import Counter
import csv,json
from research.regime.long1_six_tier_lock_shadow_v1 import LockState,update
R=Path(__file__).resolve().parents[2]
hold=json.loads((R/'research/results/LONG1_NOV16_FROZEN_STRICT_HOLDOUT_20261119.json').read_text())
source=R/'research/local_market_data/near_usdm_20261110_16_holdout/NEARUSDT-1m-2026-11-16.zip'
with ZipFile(source) as z:
 with z.open(z.namelist()[0]) as f:
  bars=[{'t':int(x['open_time']),'o':float(x['open']),
   'h':float(x['high']),'l':float(x['low']),'c':float(x['close'])}
   for x in csv.DictReader(TextIOWrapper(f,encoding='utf-8'))]
assert len(bars)==1440
from datetime import timezone
first=int(datetime(2026,11,16,tzinfo=timezone.utc).timestamp()*1000)
assert bars[0]['t']==first
def run(e,cap=True):
 # indices include previous Nov15 1440 bars
 i=e['entry_idx']-1440
 assert i>=0
 entry=bars[i]['o'];state=LockState();tp=entry*(1+1.25/300);sl=entry*(1-2.99/100)
 for j in range(i,i+60):
  b=bars[j]
  if b['o']<=sl:return j,'STOP_GAP',300*(b['o']/entry-1)-.24
  if cap and b['o']>=tp:return j,'TP_GAP',300*(b['o']/entry-1)-.24
  if b['l']<=sl:return j,'SL_FIRST',-8.97-.24
  if cap and b['h']>=tp:return j,'TP_FIRST',1.25-.24
  decision=update(state,300*(b['c']/entry-1),b['t']+60000)
  if decision['state']=='SHADOW_TRAIL_TRIGGER':
   return j+1,'TRAIL_NEXT_OPEN',300*(bars[j+1]['o']/entry-1)-.24
 return i+59,'TIMEOUT',300*(bars[i+59]['c']/entry-1)-.24
profiles={}
ready=sorted((r for r in hold['records'] if r['decision']=='SHADOW_READY'),key=lambda x:x['entry_idx'])
assert len(ready)==5
for name,cap in [('hybrid_cap125',True),('runner_uncapped',False)]:
 book=[];occupied=-1
 for r in ready:
  j,status,net=run(r,cap)
  if r['entry_idx']<=occupied:continue
  book.append({'source_model_time':r['time_utc'],'exit_reason':status,
   'net_roi_pp':round(net,4),'exit_local_index':j})
  occupied=j+1440
 profiles[name]={'opened':len(book),
  'outcomes':dict(Counter(x['exit_reason'] for x in book)),
  'net_roi_pp_sum':round(sum(x['net_roi_pp'] for x in book),4),
  'positions':book}
report={'schema':'long1_nov16_frozen_entry_hybrid_holdout_v1',
 'baseline_fixed_open':hold['single_position_opens'],
 'baseline_fixed_net_roi_pp_sum':hold['net_roi_pp_sum'],
 'original_24_model_signals_count':hold['long_signals'],
 'frozen_before_holdout':True,
 'candidate_gate_unchanged':True,
 'historical_user_label_input':False,
 'trailing_uses_close_then_next_open':True,
 'fee_roundtrip_roi_points_estimate':.24,
 'real_slippage_liquidation_funding_and_native_stop_not_reproduced':True,
 'real_exchange_orders':0,'prod_redis_writes':0,
 'profiles':profiles}
path=R/'research/results/LONG1_NOV16_FROZEN_HYBRID_HOLDOUT_20261119.json'
path.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='profiles'}|
 {'profiles':{k:{z:v[z] for z in ('opened','outcomes','net_roi_pp_sum')} for k,v in profiles.items()}},sort_keys=True))
