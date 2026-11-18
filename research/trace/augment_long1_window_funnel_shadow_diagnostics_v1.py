"""Offline metadata enrichment of 11-15 Nov audit; no broker queries/orders.

Uses retained Redis and redacted hashed intent markers in output.
Historical user labels and in-sample R1 candidate are RESEARCH ONLY.
Do not use these windows as a clock-based live filter.
"""
from __future__ import annotations
import hashlib,json,re
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import redis

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/'research/results/LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json'
S=ROOT/'research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json'
TZ=ZoneInfo('Europe/Istanbul')
def load():return json.loads(PATH.read_text())
def from_mid(mid):return datetime.fromtimestamp(int(mid.split('-')[0])/1000,TZ)
def label(dt,intervals):
    names={name for lo,hi,name in intervals if lo<=dt<hi}
    if len(names)>1:return 'CONFLICT_NO_TRADE'
    if 'LONG_WANTED' in names:return 'LONG_TARGET'
    if 'LONG_AVOID' in names:return 'LONG_AVOID'
    return 'UNLABELLED'
a=load()
w=json.loads(S.read_text())
intervals=[(datetime.fromisoformat(q['start_tr']),datetime.fromisoformat(q['end_tr']),q['user_label']) for q in w['user_intervals']]
r=redis.Redis(host='127.0.0.1',port=6379,decode_responses=True,socket_connect_timeout=2,socket_timeout=6)
streams=('signals_stream_long1','candidates_stream_long1','top5_stream_long1','trade_intents_stream_long1')
stage={}
stage_daily={}
for name in streams:
    labels=Counter()
    days=defaultdict(Counter)
    for mid,v in r.xrange(name):
        dt=from_mid(mid)
        if not ('2026-11-11'<=dt.date().isoformat()<='2026-11-15'):continue
        if name=='signals_stream_long1':
            data=json.loads(v.get('json') or '{}')
            assert data.get('producer_id')=='heavy_engine' and data.get('side_candidate')=='long' and data.get('symbol')=='NEARUSDT'
        cat=label(dt,intervals)
        labels[cat]+=1;days[dt.date().isoformat()][cat]+=1
    stage[name]={'total':sum(labels.values()),'by_reference':dict(labels)}
    stage_daily[name]={k:dict(v) for k,v in sorted(days.items())}
assert [stage[n]['total'] for n in streams]==[874,317,310,112]
assert stage['trade_intents_stream_long1']['by_reference']==a['trade_intent_reference_counts']
a['stage_redis_stream_event_counts']=stage
a['stage_redis_stream_daily_counts']=stage_daily
a['redis_signal_event_vs_model_bar_note']=(
    '874 SignalEvent Redis writes are repeated emissions, NOT 874 independent '
    'three-minute MODEL LONG score events (103); neither event count equals 112 '
    'distinct TradeIntent items.'
)
assert stage['signals_stream_long1']['by_reference'].get('CONFLICT_NO_TRADE')==6
assert stage['candidates_stream_long1']['by_reference'].get('CONFLICT_NO_TRADE')==2
assert stage['top5_stream_long1']['by_reference'].get('CONFLICT_NO_TRADE')==1
assert stage['trade_intents_stream_long1']['by_reference'].get('CONFLICT_NO_TRADE',0)==0

intents={}
for _,v in r.xrange('trade_intents_stream_long1'):
    row=json.loads(v['json'])
    for item in row.get('items') or []:
        if item.get('symbol')!='NEARUSDT':continue
        t=datetime.fromisoformat(str(item.get('ts_utc') or row.get('ts_utc')).replace('Z','+00:00')).astimezone(TZ)
        if not ('2026-11-11'<=t.date().isoformat()<='2026-11-15'):continue
        key=item.get('intent_id');assert key and key not in intents
        intents[key]=t

from pathlib import Path as P
current=None
logs={}
for f in [ROOT/'logs'/('main.log'+x) for x in ('.5','.4','.3','.2','.1','')]:
    if not f.exists():continue
    with f.open(errors='replace') as fh:
        for ln in fh:
            if ln[:10] not in {f'2026-11-{i:02d}' for i in range(11,16)}:continue
            msg=ln.split(' | ',3)[-1]
            m=re.search(r'\[EXEC-EVENTS\] recv intent=([0-9a-f-]+) side=long symbol=NEARUSDT',msg)
            if m:
                current=m.group(1)
                logs[current]={'entry':None,'recheck':None,'risk':None,'contra':None,'done':False}
                continue
            if not current:continue
            rec=logs[current]
            if '[EXEC][ENTRY-DECISION]' in msg:
                mm=re.search(r'action=(\w+) reason=([\w-]+)',msg)
                if mm:rec['entry']=mm.groups()
            elif '[EXEC][PENDING-RECHECK]' in msg:
                mm=re.search(r'status=(\w+)',msg)
                if mm:rec['recheck']=mm.group(1)
            elif '[EXEC][NOTIONAL][REJECT]' in msg:
                mm=re.search(r'reason=([\w-]+)',msg)
                rec['risk']=mm.group(1) if mm else 'risk_reject'
            elif '[EXEC][CONTRA-GUARD]' in msg:
                mm=re.search(r'action=(\w+)',msg)
                rec['contra']=mm.group(1) if mm else 'unknown'
            if '[EXEC-EVENTS] decision dispatched' in msg and f'intent={current}' in msg:
                rec['done']=True;current=None
assert set(logs)==set(intents) and all(z['done'] for z in logs.values())
# Open shadow intent IDs are independently paired to signed Binance open
# orders in the primary audit; validate 10 matches using its timestamps.
opened={}
for _,v in r.xrange('shadow:telemetry:position_open'):
    x=json.loads(v.get('json') or '{}')
    if x.get('symbol')!='NEARUSDT' or not x.get('position_open_at_ms'):continue
    dt=datetime.fromtimestamp(int(x['position_open_at_ms'])/1000,TZ)
    if not ('2026-11-11'<=dt.date().isoformat()<='2026-11-15'):continue
    assert x.get('intent_id') in intents
    opened[x['intent_id']]=x
assert len(opened)==10
rows=[]
for iid,dt in sorted(intents.items(),key=lambda kv:kv[1]):
    data=logs[iid]
    cat=label(dt,intervals)
    if iid in opened:
        reason='EXACT_BINANCE_FILLED_OPEN'
    elif data['entry']:
        action,original=data['entry']
        if action=='open' and data['risk']=='no_available_balance':
            reason='execution_risk_no_available_balance'
        elif action=='open' and data['contra']=='PENDING':
            reason='contra_trend_pending_after_entry_ready'
        elif action=='open':
            raise AssertionError('unexplained READY without fill')
        else:reason=original
    elif data['recheck']=='wait':
        reason='pending_recheck_wait_no_fresh_entry_decision'
    else:raise AssertionError('unexplained no-entry')
    rows.append({'intent_marker_sha256_12':hashlib.sha256(iid.encode()).hexdigest()[:12],
      'intent_time_tr':dt.isoformat(timespec='seconds'),
      'user_reference':cat,
      'decision_class':'OPENED' if iid in opened else 'NOT_OPENED',
      'evidence_reason':reason,
      'actual_binance_fill_order_verified':iid in opened,
      'source_model_to_intent_exact_trace_available':False})
assert len(rows)==112
assert Counter(x['evidence_reason'] for x in rows if x['decision_class']=='NOT_OPENED')==a['not_opened_reasons']
a['all_112_intent_decisions_anonymized']=rows

# Candidate shadow guard analysis based on observed pre-entry data, not
# a proposal to modify current Contra-Trend or TIME windows.
shadow_by_time={}
for iid,x in opened.items():
    dt=datetime.fromtimestamp(int(x['position_open_at_ms'])/1000,TZ)
    shadow_by_time[dt.strftime('%Y-%m-%dT%H:%M')]=x
r1_marked=[]
for trade in a['trades']:
    dt=datetime.fromisoformat(trade['open_tr'])
    assert trade['index'] and trade['exact_redis_open_order_and_intent_match']
    match=shadow_by_time[dt.strftime('%Y-%m-%dT%H:%M')]
    def f(k):return float(match[k]) if match.get(k) is not None else None
    flow15=f('research_m3_flow15_completed')
    flow60=f('research_m3_flow60_completed')
    upfrac=f('research_m3_up_frac3')
    mean3=f('research_m3_ret1_mean3')
    # Retrospective hypothesis only. Existing production rule may differ!
    risk_flag=all(x is not None for x in (flow15,flow60,upfrac,mean3)) and (
        flow15<0 and flow60<0 and upfrac<=1/3+1e-6 and mean3<0)
    trade['entry_context_telemetry']={
      'model_score':round(f('signal_score'),6),
      'm3_up_frac3':round(upfrac,6),
      'm3_return_mean3':round(mean3,7),
      'completed_flow15':round(flow15,6),
      'completed_flow60':round(flow60,6),
      'shadow_contra_conjunction_risk_only':risk_flag,
      'live_guard_decision_independently_attested':False,
    }
    if risk_flag:r1_marked.append(trade['index'])
assert r1_marked==[7,8],r1_marked
a['candidate_shadow_r1_negative_mtf_flow_hypothesis']={
  'flags_on_10_real_trades':len(r1_marked),
  'flagged_winning_trades':0,
  'flagged_losing_trades':2,
  'in_sample_only':True,'production_rule_unmodified':True,
  'not_a_validated_trading_filter':True,
  'no_future_out_of_sample_profit_improvement_claimed':True
}

path=PATH
path.write_text(json.dumps(a,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print(json.dumps({
 'status':'PASS','signal_stream_events':stage[streams[0]]['total'],
 'candidate_events':stage[streams[1]]['total'],
 'top5_batches':stage[streams[2]]['total'],
 'intent_items':len(rows),'opened':len(opened),
 'not_opened':112-len(opened),
 'conflict_signals':stage[streams[0]]['by_reference']['CONFLICT_NO_TRADE'],
 'conflict_candidates':stage[streams[1]]['by_reference']['CONFLICT_NO_TRADE'],
 'conflict_top5':stage[streams[2]]['by_reference']['CONFLICT_NO_TRADE'],
 'conflict_intents':stage[streams[3]]['by_reference'].get('CONFLICT_NO_TRADE',0),
 'in_sample_r1_flags':r1_marked,
 'real_binance_orders_sent':0,'redis_writes':0},sort_keys=True))
