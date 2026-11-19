"""As-of historical 1m closed-candle and taker-flow context for 103 MODEL LONG.

Uses LOCAL official Binance daily 1m kline archives only. Does not
reconstruct private whale, historic depth imbalance, historic live 1m
partial candle, exact model->signal identity, or Binance order state.
No forward prices used for market context. Backward-only UTC windows.
"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from bisect import bisect_right
from collections import Counter
import gzip,csv,json
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'research/local_market_data/near_usdm_20261110_15/near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz'
MODEL=json.loads((ROOT/'research/results/LONG1_MARKET_CONTEXT_V2_103_ASOF_20261111_15.json').read_text())['full_results']
assert len(MODEL)==103
with gzip.open(DATA,'rt',encoding='utf-8') as f:raw=list(csv.DictReader(f))
assert len(raw)==8640
t=[int(z['open_time_ms'])+60000 for z in raw] # CLOSED minute timestamp
assert t==sorted(set(t))
rets=[];stats=Counter()
for m in MODEL:
 event=datetime.fromisoformat(m['ts_tr'])
 # As-of last close_ts <= observed MODEL timestamp, no future minute.
 ts=int(event.timestamp()*1000)
 j=bisect_right(t,ts)-1
 assert j>=60 and j<len(raw)
 past=raw[j-59:j+1]
 assert len(past)==60 and all(int(v['fully_closed_1m_required'])==1 for v in past)
 assert all(t[j-i]-t[j-i-1]==60000 for i in range(59))
 assert t[j]<=ts<t[j]+60000
 def flow(n):
  sample=past[-n:]
  buy=sum(float(q['taker_buy_quote_volume']) for q in sample)
  quote=sum(float(q['quote_volume']) for q in sample)
  return round((2*buy-quote)/quote,6) if quote>0 else None
 def change(n):
  # approx ret of last n fully closed 1m bars
  before=float(raw[j-n]['close'])
  return round(100*(float(raw[j]['close'])/before-1),6)
 rec={'model_event_tr':m['ts_tr'],'user_reference':m['reference_label'],
 'model_close_id':m['close_id'],
 'asof_last_closed_1m_tr':datetime.fromtimestamp(t[j]/1000,ZoneInfo('Europe/Istanbul')).isoformat(timespec='seconds'),
 'fully_closed_1m_count':60,
 'market_taker_signed_flow_3m':flow(3),
 'market_taker_signed_flow_5m':flow(5),
 'market_taker_signed_flow_15m':flow(15),
 'market_taker_signed_flow_60m':flow(60),
 'price_return_3m_pct':change(3),
 'price_return_5m_pct':change(5),
 'price_return_15m_pct':change(15),
 'source':'Binance USD-M 1m complete kline quote+taker_buy_quote volume',
 'entry_confirmation_partial_1m_recovered':False,
 'realtime_orderbook_whale_depth_recovered':False,
 'raw_model_parent_trace_recovered':False,
 'all_features_available_no_lookahead':True}
 rets.append(rec)
 stats[(m['reference_label'],'negative_flow15') if rec['market_taker_signed_flow_15m']<0 else (m['reference_label'],'positive_flow15')]+=1
assert len(rets)==103
labels=Counter(z['user_reference'] for z in rets)
assert labels=={'LONG_TARGET':11,'LONG_AVOID':70,'UNLABELLED':21,'CONFLICT_NO_TRADE':1},labels
out={'schema':'long1_reconstructed_asof_binance_market_flow_20261111_15_v1',
 'source_manifest':'research/local_market_data/near_usdm_20261110_15/manifest.json',
 'source_verified_official_sha256_files':12,
 'exact_103_model_reference_events_matched_by_existing_times':True,
 'source_kline_1m_minutes':8640,
 'model_longs':len(rets),
 'user_labels':dict(labels),
 'taker_flow15_sign_by_reference':{str(k):v for k,v in stats.items()},
 'historical_flow_missing_after_rebuild':sum(z['market_taker_signed_flow_60m'] is None for z in rets),
 'prior_shadow_source_flow_availability_is_not_same_as_rebuilt_binance_taker_flow':True,
 'partial_minute_entry_features_not_recovered':True,
 'whale_depth_and_bot_context_not_recovered':True,
 'one_minute_data_only_closed_bars':True,'no_live_entry_authority':True,
 'binance_order_calls':0,'prod_redis_writes':0,
 'events':rets}
path=ROOT/'research/results/LONG1_BINANCE_ARCHIVE_ASOF_FLOW_103_MODEL_EVENTS_20261119.json'
path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'result':'PASS','model_events':len(rets),
 'historical_flow_missing':out['historical_flow_missing_after_rebuild'],
 'by_user_reference':dict(labels),
 'target_15m_signed_flow':[x['market_taker_signed_flow_15m'] for x in rets if x['user_reference']=='LONG_TARGET'],
 'whale_depth_reconstructed':False,
 'closed_bar_only':True,'no_exchange_orders':True},sort_keys=True))
