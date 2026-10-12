#!/usr/bin/env python3
from __future__ import annotations
import csv, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig

STREAM='shadow:telemetry:market_context'
OUT=ROOT/'research/results/NEAR_SHADOW_MARKET_CONTEXT.csv'

def flatten(mid, obj):
    oi=obj.get('okx_oi') or {}; st=obj.get('binance_structure') or {}; d=obj.get('derived') or {}
    return {
      'stream_id':mid,'observed_at_ms':obj.get('observed_at_ms'),'symbol':obj.get('symbol'),'status':obj.get('status'),
      'oi_status':oi.get('status'),'oi_direction':oi.get('oi_direction'),'oi_ret_period':oi.get('oi_ret_period'),
      'oi_cache_age_sec':oi.get('cache_age_sec'),'oi_source_age_sec':oi.get('source_age_sec'),
      'oi_source_phase_age_sec':oi.get('source_phase_age_sec'),'oi_period_sec':oi.get('period_sec'),
      'structure_status':st.get('status'),'m1_ret1':st.get('m1_ret1'),'m3_ret1':st.get('m3_ret1'),
      'research_m3_ret1':st.get('research_m3_ret1'),'research_m3_ret2':st.get('research_m3_ret2'),'research_m3_ret3':st.get('research_m3_ret3'),
      'research_m3_up_frac3':st.get('research_m3_up_frac3'),'research_m3_ret1_mean3':st.get('research_m3_ret1_mean3'),
      'research_m3_ret1_accel':st.get('research_m3_ret1_accel'),'research_m3_buy_ratio':st.get('research_m3_buy_ratio'),
      'research_m3_imbalance':st.get('research_m3_imbalance'),'research_m3_imb_mean3':st.get('research_m3_imb_mean3'),
      'research_m3_body':st.get('research_m3_body'),'research_m3_range':st.get('research_m3_range'),'research_m3_close_loc':st.get('research_m3_close_loc'),
      'deep_pullback':st.get('deep_pullback'),'low_recovery':st.get('low_recovery'),'price_down_3m':st.get('price_down_3m'),
      'recovery_from_low':st.get('recovery_from_low'),'structure_oi_support':d.get('structure_oi_support'),
      'm3_persistence_long':d.get('m3_persistence_long'),'m3_persistence_short':d.get('m3_persistence_short'),
      'm3_accel_long':d.get('m3_accel_long'),'m3_accel_short':d.get('m3_accel_short'),
      'm3_flow_long':d.get('m3_flow_long'),'m3_flow_short':d.get('m3_flow_short')
    }

def main():
    r=RedisConfig().client
    rows=[]
    for mid,fields in r.xrange(STREAM):
        try:
            obj=json.loads(fields.get('json') or '{}'); rows.append(flatten(mid,obj))
        except Exception: pass
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if rows:
        with OUT.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f'rows={len(rows)} out={OUT}')
if __name__=='__main__': main()
