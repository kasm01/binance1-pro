"""Read-only classification of user windows and FIRST plausible ROI touch.

Historical signals are candidate only. No real sniper/entry/fill/slippage.
Simulated price reference is close of first fully completed 1m candle after
shadow event; future path starts only in NEXT candle. 1m ambiguous TP/SL
ties are conservatively stop-first. 3x and fixed gross ROI 1.25%.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from collections import Counter,defaultdict
import json,requests,bisect
TR=timezone(timedelta(hours=3))
ROOT=Path('research/results')
model=json.loads((ROOT/'LONG1_RECOVERY_ABC_HOLDOUT_NOV11_13_DETAILS_20261115.json').read_text())
# User labels: 13:27-14:54 parsed from typo "13.2714.54".
desired=[
('2026-11-11','12:40','15:00'),('2026-11-11','15:36','17:00'),('2026-11-11','18:25','18:35'),
('2026-11-11','19:06','19:30'),('2026-11-11','22:40','23:00'),
('2026-11-12','02:20','02:55'),('2026-11-12','03:10','03:45'),
('2026-11-12','04:51','05:12'),('2026-11-12','12:15','13:25'),
('2026-11-12','17:22','17:42'),('2026-11-12','18:33','19:10'),('2026-11-12','21:20','22:18')]
avoid=[
('2026-11-12','00:15','02:20'),('2026-11-12','05:18','07:33'),
('2026-11-12','07:54','09:15'),('2026-11-12','10:33','12:18'),
('2026-11-12','13:27','14:54'),('2026-11-12','15:15','16:12'),
('2026-11-12','19:10','20:18')]
def windows(rows):
 return [(date,a,b,datetime.fromisoformat(date+'T'+a).replace(tzinfo=TR),
    datetime.fromisoformat(date+'T'+b).replace(tzinfo=TR)) for date,a,b in rows]
d=windows(desired);a=windows(avoid)
def category(ts):
 hitd=[f'{date} {lo}-{hi}' for date,lo,hi,l,r in d if l<=ts<r]
 hita=[f'{date} {lo}-{hi}' for date,lo,hi,l,r in a if l<=ts<r]
 return dict(wanted=hitd,avoid=hita,
   label='AVOID_WINS' if hita else 'WANTED' if hitd else 'UNLABELED')
# Evaluate all prerecorded observed 3m events under each window. The
# existing comparator saves only candidates, so must gather raw source.
import redis
r=redis.Redis(decode_responses=True,socket_timeout=5)
low=int(datetime(2026,11,11,0,tzinfo=TR).timestamp()*1000)
high=int(datetime(2026,11,13,0,tzinfo=TR).timestamp()*1000)
all_events=[]
for sid,fields in r.xrange('telemetry:long1:context_adaptive_gate:v1',f'{low}-0',f'{high-1}-9999'):
 try:
  v=json.loads(fields['json']);ts=datetime.fromtimestamp(int(sid.split('-')[0])/1000,TR)
  all_events.append(dict(ts=ts,score=v.get('score'),shadow_pass=v.get('pass'),
    flow15=v.get('t15_signed_ratio'),one_min=v.get('live1m_long_direction_support'),
    cid=v.get('close_id'),checks=v.get('checks')))
 except Exception:pass
candidate_lookup={}
for row in model['candidates']:
 key=row['ts_tr'][:19]
 candidate_lookup[key]=row
label_report=[]
for typ,windows_list in [('WANTED',d),('AVOID',a)]:
 for day,lo,hi,left,right in windows_list:
  ev=[x for x in all_events if left<=x['ts']<right]
  c=[z for z in model['candidates'] if left<=datetime.fromisoformat(z['ts_tr'])<right]
  c=[z for z in c if category(datetime.fromisoformat(z['ts_tr']))['label']==typ]
  item=dict(kind=typ,date=day,time_tr=f'{lo}-{hi}',shadow_event_count=len(ev),
    model_score_0495=sum(isinstance(x['score'],(int,float)) and x['score']>=.495 for x in ev),
    shadow_context_pass=sum(x['shadow_pass'] is True for x in ev),
    candidate_A=[z['ts_tr'][11:19] for z in c if 'A' in z['variants']],
    candidate_B=[z['ts_tr'][11:19] for z in c if 'B' in z['variants']],
    candidate_C=[z['ts_tr'][11:19] for z in c if 'C' in z['variants']])
  label_report.append(item)
# 1m price barriers and timestamp in first 60m after first completed
# candle close. This is a fixed retrospective reference, NOT entry fill.
begin=int(datetime(2026,11,12,0,tzinfo=TR).timestamp()*1000)-3600000
end=int(datetime(2026,11,14,12,tzinfo=TR).timestamp()*1000)
candles=[];at=begin
while at<end:
 response=requests.get('https://fapi.binance.com/fapi/v1/klines',
    params={'symbol':'NEARUSDT','interval':'1m','startTime':at,'endTime':end-1,'limit':1000},timeout=12)
 response.raise_for_status();page=response.json()
 if not isinstance(page,list) or not page or not isinstance(page[0],list):raise ValueError('invalid candles')
 candles+=page
 nxt=int(page[-1][0])+60000
 if nxt<=at:raise ValueError('nonincreasing pagination')
 at=nxt
candles=sorted({int(z[6]):dict(close_ms=int(z[6]),close=float(z[4]),high=float(z[2]),low=float(z[3])) for z in candles}.values(),key=lambda z:z['close_ms'])
times=[v['close_ms'] for v in candles]
roi=[]
for c in model['candidates']:
 timestamp=int(datetime.fromisoformat(c['ts_tr']).timestamp()*1000)
 ix=bisect.bisect_left(times,timestamp)
 if ix>=len(candles):continue
 # No trading at ref candle close; use subsequent bars for target test.
 reference=candles[ix]['close']
 t0=candles[ix]['close_ms']
 futur=[b for b in candles[ix+1:] if t0 < b['close_ms']<=t0+60*60000]
 if len(futur)<60:continue
 target=reference*(1+.0125/3)
 # price SL = -2.99% from entry. This is one upper barrier and one
 # indicative lower, NOT a simulation of actual stop or lifecycle.
 stop=reference*(1-.0299)
 first_tp=next((z for z in futur if z['high']>=target),None)
 first_sl=next((z for z in futur if z['low']<=stop),None)
 if first_tp and first_sl:
  status='TP_FIRST' if first_tp['close_ms']<first_sl['close_ms'] else (
      'STOP_FIRST_OR_SAME_MINUTE' if first_tp['close_ms']>=first_sl['close_ms'] else 'UNKNOWN')
 elif first_tp:status='TP_TOUCHED_NO_STOP_60M'
 elif first_sl:status='STOP_TOUCHED_NO_TP_60M'
 else:status='NEITHER_TOUCHED_60M'
 cr=dict(candidate_time_tr=c['ts_tr'],profiles=c['variants'],
  user_label=category(datetime.fromisoformat(c['ts_tr'])), reference_close=reference,
  ref_candle_completed_tr=datetime.fromtimestamp(t0/1000,TR).isoformat(),
  gross_roi_target_pct=1.25,leverage_assumed=3,
  required_price_pct=round(100*.0125/3,5),
  tp_level=round(target,6),price_sl_level=round(stop,6),
  tp_first_touched_tr=datetime.fromtimestamp(first_tp['close_ms']/1000,TR).isoformat() if first_tp else None,
  indicative_price_sl_first_touched_tr=datetime.fromtimestamp(first_sl['close_ms']/1000,TR).isoformat() if first_sl else None,
  first_touch_status=status,executed_trade=False,actual_net_roi_unknown=True)
 roi.append(cr)
print('WANTED_AVOID_WINDOWS')
for row in label_report:print(row['kind'],row['date'],row['time_tr'],'feed',row['shadow_event_count'],
 'score>=.495',row['model_score_0495'],'A',row['candidate_A'],'B',row['candidate_B'],'C',row['candidate_C'])
print('ROI_PRICE_BARRIERS_60M')
for x in roi:print(x['candidate_time_tr'][0:19],x['profiles'],'LABEL',x['user_label']['label'],
 x['first_touch_status'],'tp',x['tp_first_touched_tr'],'sl',x['indicative_price_sl_first_touched_tr'],
 'ref',x['reference_close'],'target',x['tp_level'])
payload=dict(schema='long1_A_B_C_new_user_windows_20261115',date_used_to_decide=False,
 research_only=True,no_order_authority=True,labels_are_subjective=True,
 exact_live_entry_simulated=False,net_roi_unknown=True,
 tp_gross_roi=0.0125,leverage_assumed=3,price_target_change=0.0125/3,
 stop_price_assumed=0.0299,fees_not_modeled=True,
 note='Touch diagnostics from first next fully-closed 1m reference, following 60 completed 1m bars; no entry-confirmation, intra-minute order fill, 2s lifecycle poll, fees or exact stop modeled.',
 selected_windows=label_report,roi_diagnostics=roi)
out=Path('research/results/LONG1_ABC_USER_NOV11_12_WINDOWS_ROI_20261115.json')
out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
print('SAVED',out)
