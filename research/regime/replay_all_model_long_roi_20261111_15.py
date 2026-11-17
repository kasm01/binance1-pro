"""Read-only exploratory first-hit barrier replay for ALL logged LONG model events.

No actual trade/entry authorization. Reference entry is close of first fully closed
1m candle AFTER logged MODEL-SCORE event; path begins NEXT candle. No hindsight
in entry reference. Time windows ONLY evaluate user labels, never generate trades.
Price TP 1.25% gross leveraged ROI at 3x -> +0.416667% price. Price SL -2.99%.
Dynamic 30s confirmation and exchange fill semantics not modeled.
"""
from __future__ import annotations
from bisect import bisect_left
from collections import Counter,defaultdict
from pathlib import Path
from datetime import datetime,timezone,timedelta
import csv,json,requests,hashlib
ROOT=Path('/home/kasm920/binance1-pro')
src=ROOT/'research/results/LONG1_TRUE_MODEL_LONG_REGIME_SHADOW_V1_20261111_15.json'
events=json.loads(src.read_text())['full_results']
assert len(events)==103
TZ=timezone(timedelta(hours=3))
# Public Binance closed 1m history: only GET, capped requests; stop at current minute.
start=int(datetime(2026,11,11,8,0,tzinfo=timezone.utc).timestamp()*1000)
end=int(datetime(2026,11,16,0,0,tzinfo=timezone.utc).timestamp()*1000)
candles=[];cursor=start;page_count=0
while cursor<end:
    res=requests.get('https://fapi.binance.com/fapi/v1/klines',
      params=dict(symbol='NEARUSDT',interval='1m',startTime=cursor,endTime=end-1,limit=1000),
      timeout=12)
    res.raise_for_status()
    page=res.json()
    if not isinstance(page,list):raise ValueError(f'HTTP succeeded with error: {str(page)[:180]}')
    if not page:break
    if not isinstance(page[0],list):raise ValueError('unexpected candle shape')
    candles+=page
    next_cursor=int(page[-1][0])+60000
    if next_cursor<=cursor:raise ValueError('nonmonotonic cursor')
    cursor=next_cursor
    page_count+=1
    if page_count>9:raise ValueError('unexpected request count')
v=sorted({int(z[6]):dict(t=int(z[6]),o=float(z[1]),h=float(z[2]),l=float(z[3]),c=float(z[4]))
 for z in candles}.values(),key=lambda z:z['t'])
times=[x['t'] for x in v]
assert len(v)>=5000
HORIZONS=(30,60,120,240)
TARGET_ROI=0.0125;LEVERAGE=3;PRICE_SL=0.0299;EST_ROUND_TRIP_FEE_NOTIONAL=0.0008
def run_one(e):
    ms=int(e['ts_ms'])
    idx=bisect_left(times,ms)
    if idx>=len(v):return None
    first=v[idx]
    # First completed 1m candle after the observed event; no use of its high/low.
    if first['t']<=ms or first['t']-ms>60000:return None
    ref=first['c']
    tp=ref*(1+TARGET_ROI/LEVERAGE)
    sl=ref*(1-PRICE_SL)
    found_tp=None;found_sl=None
    info={}
    for h in HORIZONS:
        # strictly later than reference, contiguous, no forward data beyond current.
        window=v[idx+1:idx+1+h]
        complete=len(window)==h and window[-1]['t']-window[0]['t']==(h-1)*60000
        if not complete:
            info[str(h)]={'status':'CENSORED_INCOMPLETE_FORWARD_WINDOW'}
            continue
        first_tp=next((x for x in window if x['h']>=tp),None)
        first_sl=next((x for x in window if x['l']<=sl),None)
        if first_tp and first_sl:
            state='TP_FIRST' if first_tp['t']<first_sl['t'] else (
             'SL_FIRST' if first_sl['t']<first_tp['t'] else 'SAME_MINUTE_AMBIGUOUS_SL_FIRST')
        elif first_tp:state='TP_FIRST'
        elif first_sl:state='SL_FIRST'
        else:state='NEITHER'
        # "net" fee only illustration if TP fill exact; no actual order.
        info[str(h)]=dict(status=state,
           tp_price_touched=bool(first_tp),sl_price_touched=bool(first_sl),
           tp_touched_tr=datetime.fromtimestamp(first_tp['t']/1000,TZ).strftime('%Y-%m-%d %H:%M:%S') if first_tp else None,
           sl_touched_tr=datetime.fromtimestamp(first_sl['t']/1000,TZ).strftime('%Y-%m-%d %H:%M:%S') if first_sl else None,
           max_favorable_price_pct=round((max(z['h'] for z in window)/ref-1)*100,4),
           max_adverse_price_pct=round((min(z['l'] for z in window)/ref-1)*100,4),
           horizon_end_change_price_pct=round((window[-1]['c']/ref-1)*100,4))
    return dict(model_ts_tr=e['ts_tr'],close_id=e['cid'],
      model_score=e['score'],actual_rolling_threshold=e['rolling'],
      research_label=e['reference_label'],market_regime=e['decision']['regime'],
      flow_source=e['flow_source'],
      reference_close=ref,
      reference_candle_closed_tr=datetime.fromtimestamp(first['t']/1000,TZ).strftime('%Y-%m-%d %H:%M:%S'),
      gross_roi_target_pct=1.25,price_target_pct=round(TARGET_ROI/LEVERAGE*100,6),
      tp_price=round(tp,7),sl_price=round(sl,7),
      assumed_leverage=3,indicative_tp_net_roi_after_0p08pct_round_trip_fees_pct=round((TARGET_ROI-EST_ROUND_TRIP_FEE_NOTIONAL*LEVERAGE)*100,3),
      actual_entry_simulated=False, actual_order_sent=False,
      horizons=info)
rows=[run_one(e) for e in events]
missing=sum(x is None for x in rows)
rows=[x for x in rows if x is not None]
def table_for_horizon(h):
 groups=defaultdict(list)
 for a in rows:groups[(a['model_ts_tr'][:10],a['research_label'])].append(a)
 table=[]
 for day in ('2026-11-11','2026-11-12','2026-11-13','2026-11-14','2026-11-15'):
  for lab in ('LONG_TARGET','LONG_AVOID','CONFLICT_NO_TRADE','UNLABELLED'):
   subset=groups[(day,lab)]
   eligible=[z for z in subset if z['horizons'][str(h)]['status']!='CENSORED_INCOMPLETE_FORWARD_WINDOW']
   counts=Counter(z['horizons'][str(h)]['status'] for z in eligible)
   table.append(dict(date_tr=day,label=lab,total=len(subset),
       eligible=len(eligible),censored=len(subset)-len(eligible),
       price_tp_touched=sum(z['horizons'][str(h)].get('tp_price_touched') is True for z in eligible),
       price_sl_touched=sum(z['horizons'][str(h)].get('sl_price_touched') is True for z in eligible),
       tp_first=counts['TP_FIRST'],sl_first=counts['SL_FIRST'],
       both_same_minute=counts['SAME_MINUTE_AMBIGUOUS_SL_FIRST'],neither=counts['NEITHER']))
 return table
table={str(h):table_for_horizon(h) for h in HORIZONS}
payload=dict(schema='long1_all_model_long_roi_first_hit_v1',
 retrospective_reference=True,actual_entry_simulated=False,
 no_order_authorization=True,historical_labels_not_in_signal_decision=True,
 notes='Gross leveraged ROI touch and 2.99% price SL first hit from first post-event closed 1m close; signal-only hypothetical entries, not Sniper/Entry/Contra approval; dynamic stop 30s, native triggers, exact fees, funding, BNB and intraminute fill absent.',
 first_candle_not_included_in_barrier_checks=True,ref_candle_close_after_event=True,
 fee_illustration_assumed_round_trip_notional_pct=EST_ROUND_TRIP_FEE_NOTIONAL*100,
 number_of_candles=len(v),fetch_requests=page_count,
 model_long_count=103,model_event_no_reference=missing,
 horizons_minutes=HORIZONS,summaries=table,events=rows)
out=ROOT/'research/results/LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json'
out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
csv_path=ROOT/'research/results/LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.csv'
with csv_path.open('w',newline='') as f:
 w=csv.writer(f)
 w.writerow(['date_tr','model_time_tr','reference_label','model_score','regime','flow_source','reference_close','TP_60m','SL_60m','first_hit_60m','TP_time_60m','SL_time_60m','first_hit_120m','first_hit_240m'])
 for z in rows:
  v60=z['horizons']['60'];v120=z['horizons']['120'];v240=z['horizons']['240']
  w.writerow([z['model_ts_tr'][:10],z['model_ts_tr'],z['research_label'],z['model_score'],z['market_regime'],z['flow_source'],
    z['reference_close'],v60.get('tp_price_touched'),v60.get('sl_price_touched'),v60['status'],
    v60.get('tp_touched_tr'),v60.get('sl_touched_tr'),v120['status'],v240['status']])
for horizon in HORIZONS:
 print('\n=== HORIZON',horizon,'MIN ===')
 for lab in ('LONG_TARGET','LONG_AVOID','CONFLICT_NO_TRADE','UNLABELLED'):
  subset=[x for x in table[str(horizon)] if x['label']==lab]
  keys=('total','eligible','censored','price_tp_touched','price_sl_touched','tp_first','sl_first','both_same_minute','neither')
  print(lab,dict(zip(keys,[sum(x[k] for x in subset) for k in keys])))
for row in table['60']:
 if row['label']=='UNLABELLED':continue
 print('DAY_60',row)
print('SAMPLE_AVOID_TP_FIRST_60M')
for z in rows:
 if z['research_label']=='LONG_AVOID' and z['horizons']['60']['status']=='TP_FIRST':
  print(z['model_ts_tr'], 'score',z['model_score'],'regime',z['market_regime'],'tp',z['horizons']['60']['tp_touched_tr'])
print('SAMPLE_AVOID_SL_FIRST_60M')
for z in rows:
 if z['research_label']=='LONG_AVOID' and z['horizons']['60']['status']=='SL_FIRST':
  print(z['model_ts_tr'],'score',z['model_score'],'regime',z['market_regime'],'sl',z['horizons']['60']['sl_touched_tr'])
print('FILES',out,csv_path,'n',len(rows),'missing_ref',missing,'klines',len(v),'pages',page_count)
