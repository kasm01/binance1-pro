"""True following-day LONG-only holdout, frozen strict research entry params.

Events: exact November 16 live MODEL-SCORE lines, including score/threshold.
Price: official Binance UTC Nov 15+16 complete daily 1m ZIPs.
Entry decisions only use CLOSED bars; hypothetical fill at next 1m OPEN.
Does NOT recreate actual production entry and does not trade.
"""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
from io import TextIOWrapper
from zipfile import ZipFile
from bisect import bisect_right
import csv,json,re
R=Path(__file__).resolve().parents[2]
cfg=json.loads((R/'research/staging/long1_research_only_settings_v2.json').read_text())
assert cfg['candidate']=='strict_recovery' and not cfg['safety']['order_authority']
P=cfg['entry_revalidation'];risk=cfg['risk_and_exit_replay']
logs=[]
for file in (R/'logs/main.log.1',R/'logs/main.log'):
 for line in file.open(errors='replace'):
  if not line.startswith('2026-11-16') or '[MODEL-SCORE]' not in line or 'symbol=NEARUSDT' not in line:continue
  m=re.search(r'close_id=(\d+) p_used=([0-9.]+) long_thr=([0-9.]+) side=(\w+)',line)
  if not m:continue
  cid,score,thr,side=m.groups()
  dt=datetime.strptime(line[:23],'%Y-%m-%d %H:%M:%S,%f').replace(tzinfo=timezone.utc)
  logs.append({'t_ms':int(dt.timestamp()*1000),'tr':dt.isoformat(),
    'legacy_close_id':cid,'score':float(score),'threshold':float(thr),'side':side})
assert len(logs)==419 and len(set(x['legacy_close_id'] for x in logs))==419
signals=sorted([x for x in logs if x['side']=='long'],key=lambda x:x['t_ms'])
assert len(signals)==24 and all(x['score']>=x['threshold'] for x in signals)
source=R/'research/local_market_data/near_usdm_20261110_15'
hold=R/'research/local_market_data/near_usdm_20261110_16_holdout'
bars=[]
for path in (source/'NEARUSDT-1m-2026-11-15.zip',hold/'NEARUSDT-1m-2026-11-16.zip'):
 with ZipFile(path) as z:
  with z.open(z.namelist()[0]) as f:
   for row in csv.DictReader(TextIOWrapper(f,encoding='utf8')):
    bars.append({'open_t':int(row['open_time']),'o':float(row['open']),
      'h':float(row['high']),'l':float(row['low']),
      'c':float(row['close']),'q':float(row['quote_volume']),
      'buy':float(row['taker_buy_quote_volume'])})
assert len(bars)==2880
close_t=[x['open_t']+60000 for x in bars]
assert all(close_t[i]-close_t[i-1]==60000 for i in range(1,len(close_t)))
def flow(seq):
 q=sum(bars[i]['q'] for i in seq)
 return 2*sum(bars[i]['buy'] for i in seq)/q-1 if q else -1
def metrics(i):
 b=bars[i];rng=b['h']-b['l']
 return {'body':max(b['c']-b['o'],0)/rng if rng>0 else 0,
  'retrace':(b['h']-b['c'])/rng if rng>0 else 1,
  'flow1':flow(range(i,i+1)),
  'flow3':flow(range(i-2,i+1)),
  'r3':100*(b['c']/bars[i-3]['c']-1)}
def issues(m,origin):
 err=[]
 if m['body']<P['bull_body_to_range_min']:err.append('body')
 if m['retrace']>P['upper_retrace_to_range_max']:err.append('retrace')
 if m['flow1']<P['one_minute_taker_signed_flow_min']:err.append('flow1')
 if m['flow3']<origin['flow3']+P['flow_3m_improvement_over_origin_min']:err.append('flow_recovery')
 if m['r3']<origin['r3']+P['price_3m_return_improvement_percentage_points_min']:err.append('price_recovery')
 if P['require_3m_return_positive'] and m['r3']<=0:err.append('price3_negative')
 if P['require_3m_taker_flow_positive'] and m['flow3']<=0:err.append('flow3_negative')
 return err
assert risk['simulated_tp_gross_3x_roi_percent']==1.25
assert risk['simulated_stop_price_pct']==2.99
assert risk['simulated_max_hold_minutes']==60
def exit_path(i):
 price=bars[i]['o'];tp=price*(1+1.25/300);sl=price*(1-2.99/100)
 for j in range(i,i+60):
  x=bars[j]
  slhit=x['l']<=sl;tphit=x['h']>=tp
  if slhit or tphit:
   return j,'SL_FIRST' if slhit else 'TP_FIRST',(-8.97 if slhit else 1.25)-.24
 return i+59,'TIMEOUT',(bars[i+59]['c']/price-1)*300-.24
records=[]
for sig in signals:
 i=bisect_right(close_t,sig['t_ms'])-1
 assert i>=60
 before=metrics(i)
 start_rechecks=i+1;rejected=Counter()
 qualified=None
 for j in range(start_rechecks,start_rechecks+P['max_completed_1m_rechecks']):
  err=issues(metrics(j),before)
  if not err:qualified=j;break
  rejected.update(err)
 item={'time_utc':sig['tr'],'score':sig['score'],
   'rolling_threshold':sig['threshold'],'legacy_close_id':sig['legacy_close_id'],
   'model_gate_passed':True,'rejected_recheck_features':dict(rejected),
   'production_open_intent_proven':False}
 if qualified is None:
  item.update(decision='PENDING_EXPIRED',simulated_open=False)
 else:
  entryidx=qualified+1
  assert bars[entryidx]['open_t']==close_t[qualified]
  j,status,net=exit_path(entryidx)
  item.update(decision='SHADOW_READY',entry_time_utc=datetime.fromtimestamp(bars[entryidx]['open_t']/1000,timezone.utc).isoformat(),
   entry_idx=entryidx,exit_idx=j,exit_status=status,net_roi_pp=round(net,4),simulated_open=False)
 records.append(item)
book=[];occupied=-1
for e in records:
 if e['decision']!='SHADOW_READY':continue
 if e['entry_idx']<=occupied:
  e['portfolio_reason']='ONE_POSITION_BUSY';continue
 e['simulated_open']=True
 book.append(e)
 occupied=e['exit_idx']
assert len(records)==24
res={'schema':'long1_nov16_frozen_strict_after_development_holdout_v1',
 'date_utc':'2026-11-16','model_evaluations':419,'long_signals':24,
 'training_development_date_range':'2026-11-11_to_2026-11-15',
 'frozen_settings_source':'research/staging/long1_research_only_settings_v2.json',
 'param_changed_after_holdout':False,'broker_order_execution_not_reproduced':True,
 'production_whale_sniper_entry_not_reproduced':True,
 'heldout_one_day_only':True,'holdout_price_bars':1440,
 'signal_candle_identity':'wallclock legacy bucket, not closed exchange candle',
 'signal_research_time_source':'UTC production MODEL-SCORE log',
 'signals_ready':sum(x['decision']=='SHADOW_READY' for x in records),
 'single_position_opens':len(book),
 'exit_counts':dict(Counter(x['exit_status'] for x in book)),
 'net_roi_pp_sum':round(sum(x['net_roi_pp'] for x in book),4),
 'net_roi_pp_not_account_growth':True,
 'no_orders':True,'production_redis_writes':0,
 'records':records}
dest=R/'research/results/LONG1_NOV16_FROZEN_STRICT_HOLDOUT_20261119.json'
dest.write_text(json.dumps(res,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in res.items() if k!='records'},sort_keys=True))
