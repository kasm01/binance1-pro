from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig

HORIZONS=(30,60,180)
COST_BPS=8.0
MIN_ROWS=120
MIN_BUCKETS=20


def load_rows(r,count=20000):
    rows=[]
    for _,f in r.xrevrange('shadow:telemetry:entry_context_research',count=count):
        raw=f.get('json') if isinstance(f,dict) else None
        if not raw: continue
        try: d=json.loads(raw)
        except Exception: continue
        if str(d.get('symbol') or '').upper()!='NEARUSDT': continue
        if d.get('mid') is None or d.get('observed_at_ms') is None: continue
        rows.append(d)
    if not rows: return pd.DataFrame()
    df=pd.DataFrame(rows).drop_duplicates(subset=['observed_at_ms']).sort_values('observed_at_ms')
    for c in ['observed_at_ms','mid','structure_close_time_ms','price_vs_ema99_bps','ema7_vs_ema25_bps']:
        if c in df.columns: df[c]=pd.to_numeric(df[c],errors='coerce')
    return df.reset_index(drop=True)


def add_fwd(df):
    base=df[['observed_at_ms','mid']].dropna().sort_values('observed_at_ms')
    out=df.copy(); fut=base.rename(columns={'observed_at_ms':'future_ms','mid':'future_mid'})
    for h in HORIZONS:
        left=base[['observed_at_ms']].copy(); left['target_ms']=left['observed_at_ms']+h*1000
        m=pd.merge_asof(left.sort_values('target_ms'),fut.sort_values('future_ms'),left_on='target_ms',right_on='future_ms',direction='nearest',tolerance=max(3000,int(h*250)))
        out[f'fwd_{h}s_bps']=((m.future_mid.to_numpy()/base.mid.to_numpy())-1.0)*1e4
    return out


def nonoverlap(z,h):
    keep=[]; last=None; gap=h*1000
    for i,t in zip(z.index,z.observed_at_ms):
        if last is None or t-last>=gap:
            keep.append(i); last=t
    return z.loc[keep]


def main():
    r=RedisConfig().client; df=load_rows(r)
    print('rows',len(df))
    valid=df.dropna(subset=['price_vs_ema99_bps','ema7_vs_ema25_bps'])
    print('ema_rows',len(valid),'structure_buckets',valid['structure_close_time_ms'].nunique() if 'structure_close_time_ms' in valid else 0)
    if len(valid)<MIN_ROWS:
        print(f'INSUFFICIENT_EMA_DATA need>={MIN_ROWS}')
        return
    df=add_fwd(valid)
    rules={
      'PRICE_GT_EMA99': lambda z: z['price_vs_ema99_bps']>0,
      'EMA7_GT_EMA25': lambda z: z['ema7_vs_ema25_bps']>0,
      'BOTH_LONG_REGIME': lambda z: (z['price_vs_ema99_bps']>0)&(z['ema7_vs_ema25_bps']>0),
      'BOTH_SHORT_REGIME': lambda z: (z['price_vs_ema99_bps']<0)&(z['ema7_vs_ema25_bps']<0),
    }
    rows=[]
    for h in HORIZONS:
        y=f'fwd_{h}s_bps'
        z=nonoverlap(df.dropna(subset=[y]).sort_values('observed_at_ms'),h)
        for name,fn in rules.items():
            mask=fn(z); sig=z[mask].copy()
            side=-1.0 if name=='BOTH_SHORT_REGIME' else 1.0
            gross=side*sig[y].to_numpy(float)
            buckets=sig['structure_close_time_ms'].nunique() if 'structure_close_time_ms' in sig else 0
            gross_ev=float(np.mean(gross)) if len(gross) else np.nan
            rows.append({'horizon_s':h,'rule':name,'samples':len(sig),'structure_buckets':int(buckets),'gross_ev_bps':gross_ev,'net_ev_8bps':gross_ev-COST_BPS if np.isfinite(gross_ev) else np.nan,'winrate':float(np.mean(gross>0)) if len(gross) else np.nan,'status':'INSUFFICIENT_BUCKETS' if buckets<MIN_BUCKETS else 'OBSERVE'})
    res=pd.DataFrame(rows)
    out=ROOT/'research/results/NEAR_EMA_REGIME.csv'; out.parent.mkdir(parents=True,exist_ok=True); res.to_csv(out,index=False)
    print(res.to_string(index=False)); print('out',out)

if __name__=='__main__': main()
