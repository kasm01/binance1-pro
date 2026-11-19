"""Research replay invariants, must not authorize real execution."""
import json
from pathlib import Path
from collections import Counter
R=Path(__file__).resolve().parents[2]
a=json.loads((R/'research/results/LONG1_NEW_BINANCE_103_ASOF_3PROFILE_REPLAY_20261119.json').read_text())
b=json.loads((R/'research/results/LONG1_NEW_BINANCE_103_STOP_SENSITIVITY_20261119.json').read_text())
c=json.loads((R/'research/staging/long1_research_only_settings_v2.json').read_text())
assert a['model_events']==103 and a['backfilled_archive_kline_minutes']==8640
assert a['all_hypothetical_orders_only'] and not a['production_config_modified']
assert not a['real_entry_sniper_whale_and_pending_reproduced']
assert not a['lookahead_data_used_in_entry_decision']
assert a['simulated_price_entry_only_next_bar_open']
assert a['user_label_only_used_for_retrospective_conflict_veto_and_reporting']
assert a['production_redis_writes']==a['real_exchange_orders']==0
assert b['real_executed_orders']==b['production_redis_writes']==0
assert c['status']=='NO_GO_SHADOW_ONLY' and c['candidate']=='strict_recovery'
assert not c['safety']['order_authority'] and not c['safety']['production_env_edited']
assert c['safety']['actual_joint_risk_live_guard']=='UNCONDITIONALLY_VETO'
expected={'strict_recovery':(32,20,12,1,7,-21.954,6,4),
          'balanced_pending':(59,36,23,2,11,-31.533,9,4),
          'cautious_relaxation':(81,43,30,4,9,-44.475,9,2)}
for key,(ready,opened,tp,sl,timeout,roi,targ_ready,targ_open) in expected.items():
 s=a['comparisons'][key]
 assert s['models']==103 and len(s['events'])==103
 assert s['all_ready']==ready and s['single_position_shadow_opens']==opened
 assert s['single_position_book_outcomes']=={'TP_FIRST':tp,'SL_FIRST':sl,'TIMEOUT':timeout}
 assert abs(s['single_position_net_roi_pp_sum']-roi)<1e-8
 assert s['by_label']['LONG_TARGET']['ready']==targ_ready
 assert s['by_label']['LONG_TARGET']['portfolio_open']==targ_open
 assert s['by_label']['CONFLICT_NO_TRADE']['conflict_rejected']==1
 assert s['by_label']['CONFLICT_NO_TRADE']['portfolio_open']==0
 assert s['decisions']['MODEL_GATE_REJECT']==1
 assert s['decisions']['REJECT_CONFLICT_ORIGIN']==1
 assert sum(z['simulated_order'] for z in s['events'])==opened
 assert not any(z['simulated_order'] for z in s['events'] if z['reference_label']=='CONFLICT_NO_TRADE')
 assert all(z['source_preclosed_1m_only'] and
     not z['model_to_entry_trace_observed'] and
     not z['exact_partial_m1_entry_reproduced'] for z in s['events'])
 for stop,v in b['profiles'][key].items():
  q=v['simulation_only_book']
  assert q['n']>=opened if float(stop)<2.99 else q['n']==opened
  assert q['roi_pp_sum']<0
  assert v['with_historic_broker_occupancy_veto']['roi_pp_sum']<0
assert sum(x['model_events'] for x in [a])==103
print(json.dumps({'status':'PASS','models':103,'profiles':3,'replay_books':3,
 'stop_profiles':12,'real_order_authorized':False,
 'production_configuration_changed':False,'conflict_opened':0},sort_keys=True))
