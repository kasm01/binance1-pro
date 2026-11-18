"""Strict offline regression of real-window research and broker reconciliation.

No network, Redis, Binance, order placement, production state or new filters.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime,timedelta
from decimal import Decimal
from collections import Counter
ROOT=Path(__file__).resolve().parents[2]
data=json.loads((ROOT/'research/results/LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json').read_text())
shared=json.loads((ROOT/'research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json').read_text())
intervals=[(datetime.fromisoformat(q['start_tr']),datetime.fromisoformat(q['end_tr']),q['user_label']) for q in shared['user_intervals']]
def labels(t):
 active={z for a,b,z in intervals if a<=t<b}
 if len(active)>1:return 'CONFLICT_NO_TRADE'
 if 'LONG_WANTED' in active:return 'LONG_TARGET'
 if 'LONG_AVOID' in active:return 'LONG_AVOID'
 return 'UNLABELLED'
def offline_research_gate(t):
 return 'REJECT_CONFLICT_NO_TRADE' if labels(t)=='CONFLICT_NO_TRADE' else 'NOT_AUTHORIZED_BY_USER_LABEL'
assert len(intervals)==70
assert Counter(x[2] for x in intervals)=={'LONG_WANTED':44,'LONG_AVOID':26}
assert data['model_long_scores']==103
assert data['trade_intents']==112 and data['opened_positions']==10 and data['not_opened_intents']==102
assert data['stage_redis_stream_event_counts']['signals_stream_long1']['total']==874
assert data['stage_redis_stream_event_counts']['candidates_stream_long1']['total']==317
assert data['stage_redis_stream_event_counts']['top5_stream_long1']['total']==310
assert data['stage_redis_stream_event_counts']['trade_intents_stream_long1']['total']==112
assert data['trade_intent_reference_counts']=={'LONG_TARGET':9,'LONG_AVOID':72,'UNLABELLED':31}
assert data['open_by_reference']=={'LONG_AVOID':4,'UNLABELLED':6}
assert data['model_long_reference_counts']=={'LONG_TARGET':11,'LONG_AVOID':70,
                                               'UNLABELLED':21,'CONFLICT_NO_TRADE':1}
assert sum(data['not_opened_reasons'].values())==102
assert all(x['decision_class']=='OPENED' or x['evidence_reason'] in data['not_opened_reasons']
           for x in data['all_112_intent_decisions_anonymized'])
assert len(data['all_112_intent_decisions_anonymized'])==112
assert len(set(x['intent_marker_sha256_12'] for x in data['all_112_intent_decisions_anonymized']))==112
assert len(data['window_coverage'])==70
assert len(data['conflict_coverage'])==7
for conflict in data['conflict_coverage']:
 lo=datetime.fromisoformat(conflict['start_tr']);hi=datetime.fromisoformat(conflict['end_tr'])
 assert lo<hi
 assert offline_research_gate(lo)=='REJECT_CONFLICT_NO_TRADE'
 assert offline_research_gate(lo+(hi-lo)/2)=='REJECT_CONFLICT_NO_TRADE'
 assert offline_research_gate(hi-timedelta(microseconds=1))=='REJECT_CONFLICT_NO_TRADE'
 assert conflict['real_open_count']==0 and conflict['intent_count']==0
assert all(offline_research_gate(datetime.fromisoformat(t['open_tr']))!='REJECT_CONFLICT_NO_TRADE'
           for t in data['trades'])
for trade in data['trades']:
 t=datetime.fromisoformat(trade['open_tr'])
 assert labels(t)==trade['reference_label']
 assert trade['exchange_fill_verified'] and trade['exact_redis_open_order_and_intent_match']
 assert trade['commission_usdt_indicative_hourly_bnb']>=0
 if trade['intratrade_public_1m']['fully_enclosed_bars']:
  assert trade['intratrade_public_1m']['entry_and_exit_minute_excluded'] is True
assert sum(x['realized_price_pnl_usdt']>0 for x in data['trades'])==8
assert sum(x['realized_price_pnl_usdt']<0 for x in data['trades'])==2
assert sum((Decimal(str(x['realized_price_pnl_usdt'])) for x in data['trades']),Decimal(0))==Decimal('-0.052')
assert data['shadow_outcome_missing']==1
assert len([x for x in data['trades'] if not x['shadow_outcome_present']])==1
assert data['exchange_filled_round_trips']==10 and data['exchange_market_orders']==20
assert data['exchange_usertrade_fills']==27
assert data['actual_exchange_orders_sent']==0
assert data['new_production_redis_writes']==0
# Rounded costs are approximate, check ≤2 ten-thousandths USDT.
estimate=Decimal(str(data['realized_pnl_usdt_exact']))+Decimal(str(data['total_funding_usdt_exact']))-Decimal(str(data['commission_usdt_hourly_estimate']))
assert abs(estimate-Decimal(str(data['indicative_total_after_funding_and_commissions_usdt'])))<Decimal('0.000002')
losses=[x for x in data['trades'] if x['realized_price_pnl_usdt']<0]
assert all(x['reference_label']=='LONG_AVOID' for x in losses)
assert all(.6 in x['intratrade_public_1m']['arm_levels_touched'] for x in losses)
assert sum(x['entry_context_telemetry']['shadow_contra_conjunction_risk_only'] for x in data['trades'])==2
print(json.dumps({'status':'PASS','wanted_windows':44,'avoid_windows':26,
 'conflicts_hard_offline_rejected':7,'conflict_real_opens':0,
 'model_long':103,'signal_messages':874,'candidate':317,'top5':310,
 'intents':112,'opened':10,'not_opened':102,
 'exact_broker_order_pairs':10,'two_losses_arm_0p6_touched':True,
 'actual_new_orders':0,'production_redis_writes':0},sort_keys=True))
