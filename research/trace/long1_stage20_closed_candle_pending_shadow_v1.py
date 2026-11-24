"""Stage20 strictly-as-of 3m/5m candle identity from independent archived 1m.

Archive-derived 3m/5m candles are RESEARCH proxy; independent live source
attestation still not established. No future candle, no stale intent
reuse, no Risk Master or order permission.
"""
from __future__ import annotations
import csv,gzip,json
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2]
TR=ZoneInfo('Europe/Istanbul')
MS=60000
SOURCE=ROOT/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz'
EVENTS=ROOT/'research/results/LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json'
DEST=ROOT/'research/results/LONG1_STAGE20_ASOF_3M5M_CANDLE_PENDING_EVIDENCE_20261124.json'
def load_archive(path=SOURCE):
 with gzip.open(path,'rt') as f:
  rows=list(csv.DictReader(f))
 out={}
 for r in rows:
  t=int(r['open_time_ms'])
  if t%MS or r['fully_closed_1m_required']!='1' or t in out:
   raise ValueError('invalid_or_duplicate_source_1m')
  out[t]={'t':t,'o':float(r['open']),'h':float(r['high']),
    'l':float(r['low']),'c':float(r['close']),'source_verified_1m':True}
 return out
def completed_asof(bars,*,asof_ms,minutes):
 """Latest FULL 3/5m UTC-aligned candle; close-ms no later than asof_ms."""
 if type(asof_ms)!=int or type(minutes)!=int or minutes not in (3,5):
  return {'valid':False,'reason':'bad_request'}
 width=minutes*MS
 # Fully closed candle end epoch inclusive.
 start=((asof_ms+1)//width)*width-width
 if start<0 or start+width-1>asof_ms:return {'valid':False,'reason':'bar_not_closed_asof'}
 stamps=[start+j*MS for j in range(minutes)]
 if any(t not in bars or bars[t].get('source_verified_1m') is not True for t in stamps):
  return {'valid':False,'reason':'missing_closed_source_1m','start_ms':start}
 seq=[bars[t] for t in stamps]
 if any(seq[j]['t']!=seq[j-1]['t']+MS for j in range(1,len(seq))):
  return {'valid':False,'reason':'nonconsecutive_source_1m'}
 return {'valid':True,'source':'ARCHIVE_1M_AGGREGATE_RESEARCH_PROXY',
  'independently_live_exchange_verified':False,'minutes':minutes,
  'start_ms':start,'close_ms':start+width-1,
  'o':seq[0]['o'],'h':max(z['h'] for z in seq),'l':min(z['l'] for z in seq),
  'c':seq[-1]['c'],'source_1m_count':minutes}
def pending_revalidation(*,origin_ms,decision_ms,origin_intent_id,
                        recheck_intent_id,closed3,closed5):
 """Candle-only subset of pending provenance, never a full-ready grant."""
 if not all(type(t)==int and t>0 for t in (origin_ms,decision_ms)):
  return {'status':'NO_GO','reason':'invalid_times','order_authority':False}
 if not (isinstance(origin_intent_id,str) and origin_intent_id and
         isinstance(recheck_intent_id,str) and recheck_intent_id):
  return {'status':'NO_GO','reason':'missing_intent_identity','order_authority':False}
 if origin_intent_id==recheck_intent_id:
  return {'status':'NO_GO','reason':'original_intent_reused','order_authority':False}
 if not(closed3.get('valid') and closed5.get('valid')):
  return {'status':'NO_GO','reason':'missing_closed_candle','order_authority':False}
 if not(closed3['close_ms']<=decision_ms and closed5['close_ms']<=decision_ms):
  return {'status':'NO_GO','reason':'future_candle','order_authority':False}
 if not(closed3['close_ms']>origin_ms and closed5['close_ms']>origin_ms):
  return {'status':'NO_GO','reason':'not_new_closed_3m5m','order_authority':False}
 if closed3['c']<=closed3['o'] or closed5['c']<=closed5['o']:
  return {'status':'NO_GO','reason':'proxy_candle_not_up','order_authority':False}
 return {'status':'RESEARCH_CANDLE_PROXY_READY_NOT_LIVE',
  'reason':'closed_3m5m_after_origin_on_proxy','order_authority':False,
  'real_intent_parent_verified':False,
  'native_market_context_verified':False,
  'native_entry_confirmation_verified':False,
  'risk_master_verified':False}
def compute():
 bars=load_archive()
 raw=json.loads(EVENTS.read_text())
 events=raw['events'];assert len(events)==103
 out=[];decisions=Counter();reasons=Counter()
 for i,z in enumerate(events):
  model_ms=int(datetime.fromisoformat(z['model_time_tr']).timestamp()*1000)
  # Stage13 emits research_entry_ms at closed 1m as-of boundary.
  decision_ms=z.get('closed_1m_decision_ms')
  if z['decision']!='RESEARCH_READY_NO_REAL_INTENT':
   out.append({'model_time_tr':z['model_time_tr'],
    'stage13_decision':z['decision'],'proxy_evaluable':False,
    'reason':'no_frozen_research_entry','order_authority':False})
   continue
  if type(decision_ms)!=int:
   out.append({'model_time_tr':z['model_time_tr'],
    'stage13_decision':z['decision'],'proxy_evaluable':False,
    'reason':'entry_asof_missing','order_authority':False});continue
  # query exactly observed decision moment, no + minute lookahead
  a=completed_asof(bars,asof_ms=decision_ms,minutes=3)
  b=completed_asof(bars,asof_ms=decision_ms,minutes=5)
  # Synthetic *different* intent ID purely exercises the old→fresh condition,
  # does not attest that a genuine later MODEL/Intent exists.
  v=pending_revalidation(origin_ms=model_ms,decision_ms=decision_ms,
    origin_intent_id='research-origin-'+str(i),
    recheck_intent_id='research-not-real-'+str(i),closed3=a,closed5=b)
  reasons[v['reason']]+=1
  out.append({'model_time_tr':z['model_time_tr'],
    'stage13_decision':z['decision'],
    'proxy_evaluable':True,'research_1m_entry_decision_ms':decision_ms,
    'archive_3m_closed':a,'archive_5m_closed':b,
    'research_synthetic_intent_only':True,
    'research_proxy_revalidation':v,
    'order_authority':False})
 assert len(out)==103
 assert all(not z['order_authority'] for z in out)
 return {'schema':'long1_stage20_closed_3m5m_103model_asof_replay_v1',
  'source_1m_bars':len(bars),'model_events':103,
  'stage13_research_ready_count':sum(z['proxy_evaluable'] for z in out),
  'research_3m5m_proxy_reason_counts':dict(reasons),
  'nonready_stage13_decision_counts':dict(Counter(z['stage13_decision'] for z in out if not z['proxy_evaluable'])),
  'research_ready_not_actual_model_intent':True,
  'time_aligned_closed_candles_only':True,
  'source_live_market_context_not_independently_verified':True,
  'recheck_intents_not_actual_real_model_events':True,
  'history_user_labels_not_used_for_rules':True,
  'fresh_intent_verified_count':0,
  'native_entry_verified_count':0,
  'shared_risk_authorized_count':0,
  'live_order_authorized_count':0,
  'prod_redis_writes':0,'real_orders':0,
  'research_event_rows':out}
def main():
 x=compute()
 DEST.write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
 print(json.dumps({k:v for k,v in x.items() if k!='research_event_rows'},sort_keys=True))
if __name__=='__main__':main()
