from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig

FEATURES=[
 'microprice_dev_bps','l1_imbalance','depth5_imbalance','depth20_imbalance',
 't5_signed_ratio','t15_signed_ratio','t30_signed_ratio','t5_buy_ratio','t15_buy_ratio',
 'spread_bps','basis_bps','funding_rate'
]
HORIZONS=(10,30,60,180)

def load_rows(r,count:int)->pd.DataFrame:
    rows=[]
    for _,fields in r.xrevrange('shadow:telemetry:microstructure',count=count):
        raw=fields.get('json') if isinstance(fields,dict) else None
        if not raw: continue
        try: d=json.loads(raw)
        except Exception: continue
        if str(d.get('symbol') or '').upper()=='NEARUSDT': rows.append(d)
    if not rows: return pd.DataFrame()
    df=pd.DataFrame(rows).drop_duplicates(subset=['observed_at_ms']).sort_values('observed_at_ms')
    for c in ['observed_at_ms','mid',*FEATURES]:
        if c in df.columns: df[c]=pd.to_numeric(df[c],errors='coerce')
    return df.reset_index(drop=True)

def add_forward_returns(df:pd.DataFrame)->pd.DataFrame:
    base=df[['observed_at_ms','mid']].dropna().sort_values('observed_at_ms')
    out=df.copy()
    future=base.rename(columns={'observed_at_ms':'future_ms','mid':'future_mid'})
    for h in HORIZONS:
        left=base[['observed_at_ms']].copy(); left['target_ms']=left['observed_at_ms']+h*1000
        m=pd.merge_asof(left.sort_values('target_ms'),future.sort_values('future_ms'),left_on='target_ms',right_on='future_ms',direction='nearest',tolerance=max(3000,int(h*250)))
        vals=((m['future_mid'].to_numpy()/base['mid'].to_numpy())-1.0)*1e4
        out[f'fwd_{h}s_bps']=vals
    return out

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--count',type=int,default=20000); ap.add_argument('--out',default=str(ROOT/'research/results/NEAR_MICRO_ALPHA_SUMMARY.csv'))
    a=ap.parse_args(); r=RedisConfig().client
    if r is None: raise SystemExit('redis_unavailable')
    df=load_rows(r,a.count)
    print('rows',len(df))
    if len(df)<20: print('INSUFFICIENT_DATA'); return 0
    df=add_forward_returns(df)
    rows=[]
    for h in HORIZONS:
        y=f'fwd_{h}s_bps'
        for f in FEATURES:
            if f not in df.columns: continue
            z=df[[f,y]].dropna()
            if len(z)<20 or z[f].nunique()<3: continue
            rho=z[f].corr(z[y],method='spearman')
            qlo=z[f].quantile(.2); qhi=z[f].quantile(.8)
            lo=z.loc[z[f]<=qlo,y]; hi=z.loc[z[f]>=qhi,y]
            spread=(hi.mean()-lo.mean()) if len(lo) and len(hi) else np.nan
            rows.append({'horizon_s':h,'feature':f,'n':len(z),'spearman':rho,'q80_minus_q20_fwd_bps':spread,'q20_fwd_bps':lo.mean(),'q80_fwd_bps':hi.mean()})
    res=pd.DataFrame(rows)
    Path(a.out).parent.mkdir(parents=True,exist_ok=True); res.to_csv(a.out,index=False)
    if len(res):
        res['abs_rho']=res['spearman'].abs(); print(res.sort_values(['horizon_s','abs_rho'],ascending=[True,False]).groupby('horizon_s').head(5).drop(columns='abs_rho').to_string(index=False))
    print('out',a.out)
    return 0
if __name__=='__main__': raise SystemExit(main())
