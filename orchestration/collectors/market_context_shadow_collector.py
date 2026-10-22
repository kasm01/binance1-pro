#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path
from typing import Any, Dict
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig
from monitoring.okx_oi_shadow_context import read_okx_oi_shadow, read_binance_structure_shadow

def _read_micro(r: Any, symbol: str) -> Dict[str,Any]:
    try:
        raw=r.get(f'shadow:market_context:microstructure:{symbol}')
        if not raw: return {'symbol':symbol,'status':'MISSING'}
        obj=json.loads(raw) if isinstance(raw,str) else raw
        if not isinstance(obj,dict): return {'symbol':symbol,'status':'INVALID'}
        now_ms=int(time.time()*1000); obs=int(obj.get('observed_at_ms') or 0)
        obj['cache_age_sec']=max(0.0,(now_ms-obs)/1000.0) if obs else None
        if obj['cache_age_sec'] is None or obj['cache_age_sec']>10.0: obj['status']='STALE'
        return obj
    except Exception as e:
        return {'symbol':symbol,'status':'ERROR','error':type(e).__name__}

def build_context(r: Any, symbol: str) -> Dict[str,Any]:
    now_ms=int(time.time()*1000)
    oi=read_okx_oi_shadow(r,symbol)
    st=read_binance_structure_shadow(r,symbol)
    micro=_read_micro(r,symbol)
    oi_ok=str(oi.get('status') or '').upper()=='OK'
    st_ok=str(st.get('status') or '').upper()=='OK'
    micro_ok=str(micro.get('status') or '').upper()=='OK'
    support=bool(oi_ok and st_ok and str(oi.get('oi_direction') or '').upper()=='UP' and st.get('deep_pullback') is True and st.get('low_recovery') is True and st.get('price_down_3m') is True)
    upf=st.get('research_m3_up_frac3'); mean3=st.get('research_m3_ret1_mean3'); accel=st.get('research_m3_ret1_accel'); imb3=st.get('research_m3_imb_mean3')
    persist_long=bool(st_ok and upf is not None and mean3 is not None and float(upf)>=2.0/3.0 and float(mean3)>0.0)
    persist_short=bool(st_ok and upf is not None and mean3 is not None and float(upf)<=1.0/3.0 and float(mean3)<0.0)
    accel_long=bool(st_ok and accel is not None and float(accel)>0.0)
    accel_short=bool(st_ok and accel is not None and float(accel)<0.0)
    flow_long=bool(st_ok and imb3 is not None and float(imb3)>0.0)
    flow_short=bool(st_ok and imb3 is not None and float(imb3)<0.0)
    flow15=st.get('research_m3_flow15_completed'); flow60=st.get('research_m3_flow60_completed')
    long_exhaustion_threshold=float(os.getenv('LONG_MONEY_FLOW_EXHAUSTION_60M','0.15') or .15)
    long_exhaustion=bool(st_ok and flow60 is not None and float(flow60)>=long_exhaustion_threshold)
    return {
      'schema_version':3,'shadow_only':True,'observed_at_ms':now_ms,'symbol':symbol,
      'status':'OK' if (oi_ok and st_ok) else 'DEGRADED',
      'okx_oi':oi,'binance_structure':st,'binance_microstructure':micro,
      'derived':{'structure_oi_support':support,
                 'm3_persistence_long':persist_long,'m3_persistence_short':persist_short,
                 'm3_accel_long':accel_long,'m3_accel_short':accel_short,
                 'm3_flow_long':flow_long,'m3_flow_short':flow_short,
                 'taker_flow15_completed':flow15,'taker_flow60_completed':flow60,
                 'long_money_flow_exhaustion':long_exhaustion,
                 'long_money_flow_exhaustion_threshold':long_exhaustion_threshold,
                 'long_money_flow_policy':'SHADOW_ONLY_NEW_ENTRY_VETO_CANDIDATE',
                 'oi_context_available':oi_ok,'structure_context_available':st_ok,
                 'microstructure_context_available':micro_ok}
    }

def store(r: Any, p: Dict[str,Any], ttl: int) -> None:
    sym=str(p['symbol']); raw=json.dumps(p,separators=(',',':'),sort_keys=True)
    r.setex(f'shadow:market_context:combined:{sym}',ttl,raw)
    bucket=int(p['observed_at_ms'])//300000
    marker=f'shadow:market_context:combined:last_bucket:{sym}'
    if r.get(marker)!=str(bucket):
        r.xadd('shadow:telemetry:market_context',{'symbol':sym,'json':raw},maxlen=10000,approximate=True)
        r.set(marker,str(bucket),ex=172800)

def main() -> int:
    ap=argparse.ArgumentParser(description='Shadow-only combined MARKET CONTEXT cache')
    ap.add_argument('--symbols',default='NEARUSDT')
    ap.add_argument('--poll-sec',type=float,default=1.0)
    ap.add_argument('--ttl-sec',type=int,default=180)
    a=ap.parse_args()
    syms=[x.strip().upper() for x in a.symbols.split(',') if x.strip()]
    if not syms: raise SystemExit('no_symbols')
    r=RedisConfig().client
    if r is None: raise SystemExit('redis_unavailable')
    print(f"START combined-shadow symbols={','.join(syms)} poll_sec={a.poll_sec} ttl={a.ttl_sec}",flush=True)
    while True:
        for sym in syms:
            try:
                p=build_context(r,sym); store(r,p,a.ttl_sec)
                oi=p['okx_oi']; st=p['binance_structure']; micro=p['binance_microstructure']
                print(f"OK symbol={sym} status={p['status']} oi={oi.get('oi_direction')} struct={st.get('status')} micro={micro.get('status')} spread={micro.get('spread_bps')} support={p['derived']['structure_oi_support']} flow60={p['derived'].get('taker_flow60_completed')} long_exh={p['derived'].get('long_money_flow_exhaustion')}",flush=True)
            except Exception as e:
                print(f"ERR symbol={sym} type={type(e).__name__} msg={str(e)[:160]}",flush=True)
        time.sleep(max(0.5,a.poll_sec))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
