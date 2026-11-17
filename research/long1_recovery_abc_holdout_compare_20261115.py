"""Comparative A/B/C holdout from prerecorded context and completed public bars.

A/B are exploratory (first training-day profiles), C frozen. No execution.
Only causal bars for setup. Subsequent 60m path purely diagnostic, NOT
simulation of actual Sniper / stops / TP / net ROI.
"""
from __future__ import annotations
from datetime import datetime,timezone,timedelta,date,time as dt_time
import bisect,collections,json,requests,redis,hashlib
from pathlib import Path
from research.long1_recovery_regime_frozen_v1 import assess,FROZEN_PROFILE
tz=timezone(timedelta(hours=3));outroot=Path('research/results')
start=int(datetime(2026,11,10,18,tzinfo=timezone.utc).timestamp()*1000)
end=int(datetime(2026,11,14,1,tzinfo=timezone.utc).timestamp()*1000)
def getbars(tf,ms):
 rows=[];at=start
 while at<end:
  resp=requests.get('https://fapi.binance.com/fapi/v1/klines',
     params=dict(symbol='NEARUSDT',interval=tf,startTime=at,endTime=end-1,limit=1000),timeout=12)
  resp.raise_for_status(); arr=resp.json()
  if not isinstance(arr,list) or not arr or not isinstance(arr[0],list):
   raise ValueError('bad response')
  rows.extend(arr)
  newat=int(arr[-1][0])+ms
  if newat<=at:raise ValueError('non-increasing cursor')
  at=newat
 unique={int(x[6]):dict(t=int(x[6]),o=float(x[1]),h=float(x[2]),l=float(x[3]),c=float(x[4])) for x in rows}
 return sorted(unique.values(),key=lambda v:v['t'])
bars={tf:getbars(tf,step) for tf,step in (('1m',60000),('3m',180000),('5m',300000),('15m',900000))}
times={tf:[z['t'] for z in bs] for tf,bs in bars.items()}
def previous(tf,now,count):
 ix=bisect.bisect_left(times[tf],now)
 return bars[tf][max(0,ix-count):ix]
def ctx(now):
 a=previous('3m',now,4);b=previous('5m',now,3);c=previous('15m',now,3)
 if len(a)<4 or len(b)<3 or len(c)<3:return None
 if now-a[-1]['t']>183000 or now-b[-1]['t']>303000:return None
 return dict(return_3m=a[-1]['c']/a[-2]['c']-1,
 return_5m=b[-1]['c']/b[-2]['c']-1,
 return_9m=a[-1]['c']/a[-4]['c']-1,
 return_15m=c[-1]['c']/c[-2]['c']-1,
 three_m_higher_low=a[-1]['l']>a[-2]['l'],
 five_m_higher_low=b[-1]['l']>b[-2]['l'])
def abc(x):
 # Candidate A/B are exploratory and include no order authority.
 f=x['price_features']
 if f is None or x['flow15'] is None or x['score'] is None or not isinstance(x.get('all_shadow_checks'),dict):return []
 if x['score']<.493 or x['flow15']<.20 or x['one_min_support'] is not True or x['all_shadow_checks'].get('whale_ok') is not True:return []
 if f['return_3m']<=0 or f['return_5m']<=0:return []
 result=['A']
 if f['return_9m']>0:result.append('B')
 if assess(x)['status']=='SHADOW_READY_CANDIDATE':result.append('C')
 return result
def subsequent_mfe_mae(now):
 # First subsequent fully CLOSED minute for analytic reference price.
 i=bisect.bisect_left(times['1m'],now)
 future=bars['1m'][i:i+60]
 if len(future)<60 or future[-1]['t']-future[0]['t']!=59*60000:return None
 ref=future[0]['c'];max_up=max(z['h'] for z in future)/ref-1;max_down=min(z['l'] for z in future)/ref-1
 return dict(ref_close_first_post_event=round(ref,6),
   max_favorable_price_60m_pct=round(max_up*100,4),
   max_adverse_price_60m_pct=round(max_down*100,4),
   ending_price_change_60m_pct=round((future[-1]['c']/ref-1)*100,4))
r=redis.Redis(decode_responses=True,socket_timeout=6)
scan=r.xrange('telemetry:long1:context_adaptive_gate:v1',f'{start}-0',f'{end-1}-9999')
events={}
for sid,ff in scan:
 try:
  z=json.loads(ff['json']);cid=int(z['close_id']);ms=int(sid.split('-')[0])
  t=datetime.fromtimestamp(ms/1000,tz)
  if not(date(2026,11,11)<=t.date()<=date(2026,11,13)):continue
  obj=dict(score=z['score'],flow15=z['t15_signed_ratio'],
    one_min_support=z['live1m_long_direction_support'],
    shadow_record_present=True,all_shadow_checks=z['checks'],
    price_features=ctx(ms))
  wins=abc(obj);cycle=subsequent_mfe_mae(ms) if wins else None
  events[(cid,t.isoformat())]=dict(ts_tr=t.isoformat(),date=t.date().isoformat(),
      hourblock=f'{t.hour//6*6:02d}:00-{t.hour//6*6+6:02d}:00',
      score=round(obj['score'],6),flow15=round(obj['flow15'],4),
      oi_direction=z.get('oi_direction'),one_min_support=obj['one_min_support'],
      variants=wins,price_path_60m=cycle,actual_order_authorized=False)
 except Exception as exc:
  print('SKIP_ERR',type(exc).__name__,str(exc)[:100])
rows=sorted(events.values(),key=lambda z:z['ts_tr'])
byblock=collections.defaultdict(lambda:{'A':[],'B':[],'C':[],'source_events':0})
for z in rows:
 key=(z['date'],z['hourblock']);q=byblock[key];q['source_events']+=1
 for v in z['variants']:q[v].append(z['ts_tr'][11:19])
summaries=[]
for day in (11,12,13):
 for hr in (0,6,12,18):
  k=(f'2026-11-{day}',f'{hr:02d}:00-{hr+6:02d}:00')
  v=byblock[k]
  summaries.append(dict(date_tr=k[0],time_tr=k[1],source_events=v['source_events'],
    coverage='NO_RECORDED_CONTEXT' if v['source_events']==0 else 'PARTIAL' if v['source_events']<90 else 'AVAILABLE',
    A=v['A'],B=v['B'],C=v['C']))
payload=dict(schema='long1_ABC_holdout_compare_v1',research_only=True,
 no_live_orders=True,no_actual_trade_backtest=True,score_to_order_not_authorized=True,
 training_date='2026-11-15',profile_C_hash=hashlib.sha256(Path('research/long1_recovery_regime_frozen_v1.py').read_bytes()).hexdigest(),
 fee_and_slippage_not_modeled=True,partial_first_window=True,
 price_path_note='MFE/MAE from FIRST closed 1m candle after shadow timestamp to next 60 closed 1m; no executable entry price, intrabar ordering, stop or funding. No claims of net ROI.',
 kline_count={tf:len(arr) for tf,arr in bars.items()},
 hour_blocks=summaries,
 candidates=[z for z in rows if z['variants']])
out=outroot/'LONG1_RECOVERY_ABC_HOLDOUT_NOV11_13_DETAILS_20261115.json'
out.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n')
for item in summaries:
 print(item['date_tr'],item['time_tr'],'context',item['source_events'],
 'A',','.join(item['A']) or '-', 'B',','.join(item['B']) or '-','C',','.join(item['C']) or '-')
print('COUNTS',len(payload['candidates']),{v:sum(v in z['variants'] for z in payload['candidates']) for v in ('A','B','C')},'OUTPUT',out)
