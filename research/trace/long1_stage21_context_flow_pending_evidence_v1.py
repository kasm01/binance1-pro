"""Stage21: as-of 3m/5m/15m flow-price + strict fresh pending proof (shadow).

Only archived fully CLOSED Binance 1m kline proxy; never claim native
live market or intent transport proof. No lookahead, no calls, no orders.
"""
from __future__ import annotations
from pathlib import Path
from collections import Counter
from datetime import datetime
import csv,gzip,json,math
from orchestration.trace.long1_fresh_reentry_validator_v1 import verify_fresh_reentry
from research.trace.long1_stage20_closed_candle_pending_shadow_v1 import (
 ROOT,SOURCE,completed_asof,load_archive)
SRC=ROOT/'research/results/LONG1_STAGE20_ASOF_3M5M_CANDLE_PENDING_EVIDENCE_20261124.json'
DEST=ROOT/'research/results/LONG1_STAGE21_FLOW_CONTEXT_PENDING_PROOF_20261124.json'
def load_flow(path=SOURCE):
 out={}
 with gzip.open(path,'rt') as f:
  for z in csv.DictReader(f):
   t=int(z['open_time_ms'])
   if t in out or z['fully_closed_1m_required']!='1':
    raise ValueError('invalid_flow_source')
   buy=float(z['agg_buy_taker_quote'])
   sell=float(z['agg_sell_taker_quote'])
   total=buy+sell
   if not all(math.isfinite(v) and v>=0 for v in (buy,sell,total)):
    raise ValueError('bad_flow')
   out[t]={'t':t,'buy':buy,'sell':sell}
 return out
def window_at(flow,*,decision_ms,minutes):
 if type(decision_ms)!=int or minutes not in (3,5,15,60):
  return {'valid':False,'reason':'invalid_request'}
 # last 1m open whose CLOSE <= decision_ms
 close_exclusive=((decision_ms+1)//60000)*60000
 first=close_exclusive-minutes*60000
 ts=range(first,close_exclusive,60000)
 if first<0 or any(t not in flow for t in ts):
  return {'valid':False,'reason':'missing_completed_1m'}
 buy=sum(flow[t]['buy'] for t in ts)
 sell=sum(flow[t]['sell'] for t in ts)
 if buy+sell<=0:
  return {'valid':False,'reason':'zero_volume'}
 return {'valid':True,'start_ms':first,'close_ms':close_exclusive-1,
  'window_minutes':minutes,'signed_ratio':round((buy-sell)/(buy+sell),8),
  'source':'ARCHIVE_CLOSED_1M_TAKER_VOLUME_PROXY',
  'live_collector_and_market_context_independently_verified':False}
def context_diagnostic(*,c3,c5,f3,f5,f15,f60,decision_ms):
 if not all(x.get('valid') for x in (c3,c5,f3,f5,f15,f60)):
  return 'MISSING_SOURCE_FAIL_CLOSED'
 if any(x['close_ms']>decision_ms for x in (c3,c5,f3,f5,f15,f60)):
  return 'FUTURE_DATA_FAIL_CLOSED'
 if c3['c']<=c3['o'] or c5['c']<=c5['o']:
  return 'PRICE_REVERSAL_NOT_SUPPORTED'
 if f3['signed_ratio']<0 or f5['signed_ratio']<0:
  return '3M_5M_BUYER_FLOW_WEAK'
 if f15['signed_ratio']<0 or f60['signed_ratio']<0:
  return '15M_60M_CONTEXT_NEGATIVE'
 return 'ARCHIVE_RESEARCH_SUPPORT_ONLY'
def status_fresh(*,orig,new,observed,close3,close5):
 """Explicit dummy IDs cannot pass exact source/new 1m/risk proof."""
 origin={'symbol':'NEARUSDT','side':'long','intent_id':'pending-origin-demo',
  'model_evaluation_id':'model-origin-demo','pending_attempt_id':'pending-test-1'}
 recheck={'symbol':'NEARUSDT','side':'long','intent_id':'fresh-demo',
  'model_evaluation_id':'model-fresh-demo','pending_attempt_id':'pending-test-1',
  'pending_origin_intent_id':'pending-origin-demo',
  'pending_recheck_intent_id':'fresh-demo'}
 evidence={'origin_closed_3m_ms':orig,'new_closed_3m_ms':close3,
  'new_closed_5m_ms':close5,'observed_at_ms':observed,
  # No arbitrary YES attestations: source chain/real native proof unavailable
  'exact_model_signal_candidate_intent_chain':False,
  'fresh_model_evaluation_attested':False,
  'closed_3m_source_verified':False,'closed_5m_source_verified':False,
  'contra_recovery_3m5m_confirmed':False,
  'new_1m_sniper_pass':False,'new_1m_entry_confirmation_pass':False,
  'original_pending_expired':False,'no_conflicting_window':False,
  'broker_position_flat_verified':False,'shared_risk_permission':False}
 return verify_fresh_reentry(origin=origin,recheck=recheck,evidence=evidence)
def run():
 base=json.loads(SRC.read_text());bars=load_archive();flows=load_flow()
 assert len(bars)==len(flows)==8640
 output=[];counts=Counter();proof_errors=Counter()
 for e in base['research_event_rows']:
  if not e['proxy_evaluable']:
   output.append({'model_time_tr':e['model_time_tr'],
    'stage13_decision':e['stage13_decision'],
    'investigated':False,'real_order_authority':False});continue
  d=e['research_1m_entry_decision_ms']
  c3=e['archive_3m_closed'];c5=e['archive_5m_closed']
  f3=window_at(flows,decision_ms=d,minutes=3)
  f5=window_at(flows,decision_ms=d,minutes=5)
  f15=window_at(flows,decision_ms=d,minutes=15)
  f60=window_at(flows,decision_ms=d,minutes=60)
  reason=context_diagnostic(c3=c3,c5=c5,f3=f3,f5=f5,
    f15=f15,f60=f60,decision_ms=d)
  origin=int(datetime.fromisoformat(e['model_time_tr']).timestamp()*1000)
  p=status_fresh(orig=origin,new=d,observed=d,
    close3=c3.get('close_ms'),close5=c5.get('close_ms'))
  assert not p['live_order_authorized'] and not p['provenance_complete']
  counts[reason]+=1;proof_errors.update(p['missing_or_invalid'])
  output.append({'model_time_tr':e['model_time_tr'],
    'stage13_decision':e['stage13_decision'],'investigated':True,
    'research_decision_asof_ms':d,'archive_flow3':f3,'archive_flow5':f5,
    'archive_flow15':f15,'archive_flow60':f60,
    'archive_close3':c3,'archive_close5':c5,
    'research_market_context_result':reason,
    'pending_provenance_status':p['status'],
    'missing_real_proof':list(p['missing_or_invalid']),
    'source_chain_and_real_new_intent_proven':False,
    'real_order_authority':False})
 assert len(output)==103 and sum(counts.values())==32
 return {'schema':'long1_stage21_context_flow_pending_evidence_v1',
  'model_events':103,'stage13_ready_proxies':32,
  'archive_flow_diagnostics':dict(counts),
  'missing_real_proof_frequency':dict(proof_errors),
  'native_live_3m5m_market_context_proven':False,
  'native_pending_origin_and_new_intent_proven':False,
  'live_whale_sniper_entry_confirm_risk_proven':False,
  'independent_new_model_identity_proven':False,
  'archive_time_asof_closed_only':True,
  'human_outcome_labels_used_for_gating':False,
  'archive_proxy_not_real_trade_entry':True,
  'real_order_authority_count':0,'production_redis_writes':0,
  'binance_api_calls':0,'additional_services':0,
  'details':output}
def main():
 x=run()
 DEST.write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
 print(json.dumps({k:v for k,v in x.items() if k!='details'},sort_keys=True))
if __name__=='__main__':main()
