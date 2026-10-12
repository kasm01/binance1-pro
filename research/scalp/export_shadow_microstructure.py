from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--count',type=int,default=20000); ap.add_argument('--out',default=str(ROOT/'research/results/NEAR_SHADOW_MICROSTRUCTURE.csv'))
    a=ap.parse_args(); r=RedisConfig().client
    if r is None: raise SystemExit('redis_unavailable')
    rows=[]
    for _,fields in r.xrevrange('shadow:telemetry:microstructure',count=a.count):
        raw=fields.get('json') if isinstance(fields,dict) else None
        if not raw: continue
        try: d=json.loads(raw)
        except Exception: continue
        if str(d.get('symbol') or '').upper()!='NEARUSDT': continue
        rows.append(d)
    rows.reverse(); df=pd.DataFrame(rows)
    if len(df): df=df.drop_duplicates(subset=['observed_at_ms']).sort_values('observed_at_ms')
    Path(a.out).parent.mkdir(parents=True,exist_ok=True); df.to_csv(a.out,index=False)
    print('rows',len(df),'out',a.out)
    if len(df): print(df[['observed_at_ms','spread_bps','basis_bps','funding_rate','depth5_imbalance','t15_signed_ratio','t15_count']].tail(5).to_string(index=False))
    return 0
if __name__=='__main__': raise SystemExit(main())
