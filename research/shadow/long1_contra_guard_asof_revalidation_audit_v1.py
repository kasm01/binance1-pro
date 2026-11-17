#!/usr/bin/env python3
"""Read-only: verify as-of CLOSED 3m/5m candles, model gate and native Entry Confirmation."""
import importlib.util, json, math, re
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('fsm',ROOT/'research/shadow/long1_contra_guard_shadow_fsm_v1.py')
fsm=importlib.util.module_from_spec(spec);spec.loader.exec_module(fsm)
BARS=ROOT/'research/data/NEARUSDT_1m_20261111_1030_1450_SHADOW_REPLAY.csv'
TRACE=ROOT/'research/results/LONG1_DECISION_TRACE_SHADOW.jsonl'
OUT=ROOT/'research/results/LONG1_CONTRA_GUARD_ASOF_3M5M_NATIVE_20261111.csv'
raw=pd.read_csv(BARS).sort_values('open_time')
assert raw.open_time.diff().dropna().eq(60000).all(),'Missing candles'
barends={}
for n in (3,5):
 tmp=raw.copy()
 tmp['b']=tmp.open_time//(n*60000)
 group=tmp.groupby('b').agg(first=('open_time','first'),last=('close_time','last'),close=('close','last'),count=('close','size'))
 group=group[(group['count']==n)&(group['last']==((group.index+1)*n*60000-1))]
 barends[n]=group
def asof(n,when):
 b=barends[n]
 # strict rule: last completed bar close < signal timestamp
 z=b[b['last']<when]
 if len(z)<2:return None
 a,c=z.iloc[-2],z.iloc[-1]
 return dict(last_close_ms=int(c['last']),last_close=float(c['close']),previous_close=float(a['close']),
             up=bool(c['close']>a['close']),age_sec=round((when-int(c['last']))/1000,2))
def last15flow(when):
 a=raw[raw.close_time<when].tail(15)
 if len(a)<15:return None
 if int(a.close_time.iloc[-1])+1>when:return None
 q=a.quote_asset_volume.sum()
 return round(float((2*a.taker_buy_quote_volume.sum()-q)/q),6) if q else None
events=fsm.events(TRACE)
native=fsm.native_decisions(ROOT/'logs/main.log')
shadow=[e for e in events if e.get('stream')=='signals_stream_long1' and e.get('model',{}).get('side')=='LONG']
pend=[e for e in shadow if (e.get('specialists',{}).get('market_direction') or {}).get('direction')=='SHORT' and (e.get('specialists',{}).get('money_flow') or {}).get('direction')=='SHORT' and e.get('advisory_action')=='PENDING']
assert len(pend)>0
items=[e for e in events if e.get('stream')=='exec_events_stream_long1']
rows=[]
for p in pend:
 t0=int(p.get('observed_at_ms') or fsm.dt.datetime.fromisoformat(p['observed_at_utc']).timestamp()*1000)
 origin=p.get('candidate_id')
 following=[e for e in items if t0<int(e.get('observed_at_ms') or 0)<=t0+1800000]
 any_real=False
 for ev in following:
  when=int(ev['observed_at_ms'])
  m3=asof(3,when);m5=asof(5,when);flow=last15flow(when)
  for it in ev.get('items') or []:
   if it.get('symbol')!='NEARUSDT':continue
   id=it.get('intent_id');decision=native.get(id) or {}
   native_ready=(decision.get('action')=='open' and decision.get('reason')=='entry_confirmation_ready')
   score=it.get('model_score');gate=p.get('model',{}).get('rolling_gate')
   # Historical rolling gate at event can differ; cached gate is not as-of proof.
   same_fresh_model=bool(score is not None and gate is not None and math.isfinite(float(score)))
   both=bool(m3 and m5 and m3['up'] and m5['up'])
   record=dict(origin_id=origin,origin_ts_ms=t0,intent_id=id,decision_ts_ms=decision.get('ts_ms'),
               event_ts_ms=when,minutes_after_origin=round((when-t0)/60000,2),
               actual_native_action=decision.get('action'),actual_native_reason=decision.get('reason'),
               native_ready=native_ready,observed_model_score=score,
               original_rolling_threshold=gate,
               fresh_gate_recomputed_proven=False,
               m3_last_closed_ms=m3['last_close_ms'] if m3 else None,
               m5_last_closed_ms=m5['last_close_ms'] if m5 else None,
               m3_up=m3['up'] if m3 else None,m5_up=m5['up'] if m5 else None,
               m3_5m_confirm=both,flow15_completed=flow,
               all_proven_ready=False,
               rationale='no_fresh_native_model_gate_sniper_revalidation_event')
   rows.append(record)
   any_real=any_real or native_ready
print('PENDING_EVENTS',len(pend),'UNIQUE_ORIGINS',len(set(e.get('candidate_id') for e in pend)),'INTENT_ROWS',len(rows))
if rows:
 out=pd.DataFrame(rows);out.to_csv(OUT,index=False)
 print('FOLLOW_NATIVE_READY',int(out.native_ready.sum()),'BOTH_3M5M',int(out.m3_5m_confirm.sum()),'BOTH_AND_READY',int((out.native_ready & out.m3_5m_confirm).sum()),'PROVEN_FULL_READY',int(out.all_proven_ready.sum()))
 print(out[['origin_id','intent_id','minutes_after_origin','actual_native_action','actual_native_reason','native_ready','m3_up','m5_up','m3_5m_confirm','flow15_completed']].to_string(index=False))
else:
 pd.DataFrame(columns=['origin_id','intent_id','native_ready','m3_5m_confirm','all_proven_ready']).to_csv(OUT,index=False)
print('OUTPUT',OUT)
# Separate candle-only counterfactual from real native READY.
# Trigger only after both completed 3m and 5m intervals, using no future prices.
origin=min(int(x.get('observed_at_ms') or fsm.dt.datetime.fromisoformat(x['observed_at_utc']).timestamp()*1000) for x in pend)
window=range(origin,origin+30*60000+1,60_000)
tests=[]
for t in window:
 three=asof(3,t);five=asof(5,t);fl=last15flow(t)
 if three and five:
  tests.append(dict(ts_ms=t,minutes_from_first_pending=round((t-origin)/60000,2),
    three_close_ms=three['last_close_ms'],five_close_ms=five['last_close_ms'],
    three_up=three['up'],five_up=five['up'],flow15=fl,
    candle_only_ready=bool(three['up'] and five['up']),
    candle_plus_flow=bool(three['up'] and five['up'] and fl is not None and fl>=0),
    native_ready=False,actual_order_authority=False))
frame=pd.DataFrame(tests)
mp=ROOT/'research/results/LONG1_CONTRA_GUARD_ASOF_CANDLE_WINDOW_20261111.csv'
frame.to_csv(mp,index=False)
print('PENDING_CANDLE_WINDOW',len(frame),'3m5m_up_minutes',int(frame.candle_only_ready.sum()),
      '3m5m_up_plus_flow_minutes',int(frame.candle_plus_flow.sum()),
      'first_3m5m_up_minute',float(frame.loc[frame.candle_only_ready,'minutes_from_first_pending'].iloc[0]) if frame.candle_only_ready.any() else None,
      'native_intents_after_pending',len(rows), 'OUTPUT',mp)
