"""Illustrative $2,000 sizing, frozen Stage13 fee+stop assumptions.

No prospective trade profitability claim. Fixed margin per hypothetical
trade, not compounding; slippage/funding not modeled. Retrospective user
labels are diagnostic only and never authorize time-based trading.
"""
import json,statistics
from pathlib import Path
R=Path(__file__).resolve().parents[2]
P=json.loads((R/'research/results/LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json').read_text())
M=json.loads((R/'research/results/LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json').read_text())['events']
H=json.loads((R/'research/results/LONG1_70_USER_WINDOWS_ASOF_SIMULATION_20261120.json').read_text())
out={'schema':'long1_2000_usdt_risk_and_model_gate_research_v1',
 'account_balance_usdt':2000,'leverage':3,
 'position_fraction_is_ASSUMED_INITIAL_MARGIN_fraction_of_balance':True,
 'roundtrip_taker_notional_fee_pct_assumed':0.08,
 'gross_tp_roi_pct':1.25,'stop_price_pct':2.99,
 'fee_roi_points':.24,'stop_gross_roi_points':-8.97,
 'stop_net_roi_points':-9.21,
 'historical_user_labels_not_live_order_rules':True,
 'real_orders':0,'real_orders_authorized':False,
 'source_no_model_wanted_windows':H['by_label']['LONG_WANTED']['without_model_long'],
 'model_score_by_label':{},'scenarios':[]}
for label in ('LONG_TARGET','LONG_AVOID','UNLABELLED'):
 z=[a for a in M if a['research_label']==label]
 assert z
 out['model_score_by_label'][label]={'models':len(z),
  'already_passed_actual_rolling_model_gate':sum(a['model_score']>=a['actual_rolling_threshold'] for a in z),
  'median_model_score':round(statistics.median(a['model_score'] for a in z),6),
  'median_margin_above_actual_gate':round(statistics.median(a['model_score']-a['actual_rolling_threshold'] for a in z),6)}
for frac in (.05,.10,.20,.48):
 margin=2000*frac;notional=3*margin
 row={'initial_margin_fraction_of_account':frac,
 'margin_usdt':round(margin,4),'notional_usdt':round(notional,4),
 'roundtrip_fee_usdt':round(notional*.0008,4),
 'take_profit_net_usdt':round(margin*(1.25-.24)/100,4),
 'stop_loss_net_usdt':round(margin*(-8.97-.24)/100,4),
 'loss_if_stop_pct_of_account':round(frac*9.21,4),
 'research_historical_hypothetical_total_net_usdt_if_constant_margin_not_compounded':{},
 'no_slippage_funding_liquidation_model':True}
 for kind in ('fixed','hybrid'):
  s=P['exit_comparison'][kind]
  row['research_historical_hypothetical_total_net_usdt_if_constant_margin_not_compounded'][kind]={
   'synthetic_single_position':round(margin*s['pure_synthetic_single_position']['net_roi_points_total']/100,4),
   'broker_position_occupancy_sensitivity':round(margin*s['real_broker_occupancy_sensitivity']['net_roi_points_total']/100,4)}
 out['scenarios'].append(row)
assert out['source_no_model_wanted_windows']==34
assert out['model_score_by_label']['LONG_TARGET']['already_passed_actual_rolling_model_gate']==11
assert out['model_score_by_label']['LONG_AVOID']['already_passed_actual_rolling_model_gate']==69
assert out['scenarios'][-1]['stop_loss_net_usdt']==-88.416
assert out['scenarios'][-1]['take_profit_net_usdt']==9.696
path=R/'research/results/LONG1_2000USDT_RISK_SIZE_AND_GATE_DIAGNOSTIC_20261120.json'
path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','scenarios':out['scenarios'],
 'model_score_by_label':out['model_score_by_label']},sort_keys=True))
