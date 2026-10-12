from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig

# Redundant aliases are intentionally removed:
# - microprice_dev_bps ~ l1_imbalance (rho ~ 0.997)
# - t5_buy_ratio ~ t5_signed_ratio (rho ~ 1.0)
# - t15_buy_ratio ~ t15_signed_ratio (rho ~ 1.0)
FEATURES=[
 'l1_imbalance','depth5_imbalance','depth20_imbalance',
 't5_signed_ratio','t15_signed_ratio','t30_signed_ratio',
 'spread_bps','basis_bps','funding_rate'
]
HORIZONS=(10,30,60,180)
# Project replay default is 4 bps taker fee per side => 8 bps round trip.
# 10/12 bps scenarios add 1/2 bps slippage per side respectively.
COSTS=(8.0,10.0,12.0)

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
        out[f'fwd_{h}s_bps']=((m['future_mid'].to_numpy()/base['mid'].to_numpy())-1.0)*1e4
    return out

def nonoverlap(z:pd.DataFrame,h:int)->pd.DataFrame:
    if z.empty: return z
    keep=[]; last=None; gap=h*1000
    for i,t in zip(z.index,z['observed_at_ms']):
        if last is None or t-last>=gap:
            keep.append(i); last=t
    return z.loc[keep]

def bootstrap_ci(x:np.ndarray,seed:int=42):
    x=np.asarray(x,dtype=float); x=x[np.isfinite(x)]
    if len(x)<10: return (np.nan,np.nan)
    rng=np.random.default_rng(seed)
    means=np.empty(2000)
    for i in range(len(means)):
        means[i]=rng.choice(x,size=len(x),replace=True).mean()
    return tuple(np.quantile(means,[.025,.975]))

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--count',type=int,default=20000)
    ap.add_argument('--train-frac',type=float,default=.70)
    ap.add_argument('--out',default=str(ROOT/'research/results/NEAR_MICRO_ROBUST.csv'))
    a=ap.parse_args(); r=RedisConfig().client
    if r is None: raise SystemExit('redis_unavailable')
    df=add_forward_returns(load_rows(r,a.count))
    print('rows',len(df))
    if len(df)<80: print('INSUFFICIENT_DATA_FOR_ROBUST_TEST'); return 0
    rows=[]
    for h in HORIZONS:
        y=f'fwd_{h}s_bps'
        for f in FEATURES:
            if f not in df.columns: continue
            z=df[['observed_at_ms',f,y]].dropna().sort_values('observed_at_ms')
            if len(z)<60 or z[f].nunique()<5: continue
            cut=max(30,min(len(z)-20,int(len(z)*a.train_frac)))
            tr=z.iloc[:cut].copy(); te=z.iloc[cut:].copy()
            rho=tr[f].corr(tr[y],method='spearman')
            if not np.isfinite(rho) or abs(rho)<1e-12: continue
            orient=1.0 if rho>0 else -1.0
            tr['score']=orient*tr[f]; te['score']=orient*te[f]
            q20,q80=tr['score'].quantile([.2,.8])
            te=nonoverlap(te,h)
            te['side']=np.where(te['score']>=q80,1,np.where(te['score']<=q20,-1,0))
            sig=te[te['side']!=0].copy()
            sig['gross_bps']=sig['side']*sig[y]
            gross=sig['gross_bps'].to_numpy(dtype=float)
            ci_lo,ci_hi=bootstrap_ci(gross,seed=42+h)
            rec={
              'horizon_s':h,'feature':f,'raw_n':len(z),'train_n':len(tr),'test_nonoverlap_n':len(te),
              'train_spearman':rho,'orientation':'HIGH_LONG' if orient>0 else 'LOW_LONG',
              'trades':len(sig),'longs':int((sig['side']==1).sum()),'shorts':int((sig['side']==-1).sum()),
              'gross_ev_bps':float(np.nanmean(gross)) if len(gross) else np.nan,
              'gross_median_bps':float(np.nanmedian(gross)) if len(gross) else np.nan,
              'gross_winrate':float(np.mean(gross>0)) if len(gross) else np.nan,
              'gross_ci95_lo':ci_lo,'gross_ci95_hi':ci_hi,
            }
            for c in COSTS:
                rec[f'net_ev_{int(c)}bps']=rec['gross_ev_bps']-c if np.isfinite(rec['gross_ev_bps']) else np.nan
            # Conservative research acceptance gate: never promote tiny samples.
            if rec['trades'] < 20:
                rec['evidence_status']='INSUFFICIENT_TRADES'
            elif not np.isfinite(rec['gross_ci95_lo']) or rec['gross_ci95_lo'] <= 0:
                rec['evidence_status']='UNCERTAIN_CI'
            elif rec['net_ev_8bps'] <= 0:
                rec['evidence_status']='REJECT_AFTER_COST'
            else:
                rec['evidence_status']='CANDIDATE'
            rows.append(rec)
    res=pd.DataFrame(rows)
    Path(a.out).parent.mkdir(parents=True,exist_ok=True); res.to_csv(a.out,index=False)
    if len(res):
        show=res[res['trades']>=3].sort_values(['horizon_s','net_ev_8bps'],ascending=[True,False])
        cols=['horizon_s','feature','train_spearman','test_nonoverlap_n','trades','longs','shorts','gross_ev_bps','gross_winrate','gross_ci95_lo','gross_ci95_hi','net_ev_8bps','net_ev_10bps','net_ev_12bps','evidence_status']
        print(show.groupby('horizon_s').head(5)[cols].to_string(index=False))
    print('out',a.out)
    return 0
if __name__=='__main__': raise SystemExit(main())
