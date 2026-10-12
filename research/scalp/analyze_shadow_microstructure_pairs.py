from __future__ import annotations
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig

FEATURES=['l1_imbalance','depth5_imbalance','depth20_imbalance','t5_signed_ratio','t15_signed_ratio','t30_signed_ratio','spread_bps','basis_bps','funding_rate']
HORIZONS=(30,60,180)
COSTS=(8.0,10.0,12.0)


def load_rows(r,count=20000):
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


def add_fwd(df):
    base=df[['observed_at_ms','mid']].dropna().sort_values('observed_at_ms')
    out=df.copy(); fut=base.rename(columns={'observed_at_ms':'future_ms','mid':'future_mid'})
    for h in HORIZONS:
        left=base[['observed_at_ms']].copy(); left['target_ms']=left['observed_at_ms']+h*1000
        m=pd.merge_asof(left.sort_values('target_ms'),fut.sort_values('future_ms'),left_on='target_ms',right_on='future_ms',direction='nearest',tolerance=max(3000,int(h*250)))
        out[f'fwd_{h}s_bps']=((m['future_mid'].to_numpy()/base['mid'].to_numpy())-1)*1e4
    return out


def nonoverlap(z,h):
    keep=[]; last=None; gap=h*1000
    for i,t in zip(z.index,z.observed_at_ms):
        if last is None or t-last>=gap: keep.append(i); last=t
    return z.loc[keep]


def zscore_apply(train,test,col):
    mu=train[col].mean(); sd=train[col].std(ddof=0)
    if not np.isfinite(sd) or sd<1e-12: return None,None
    return (train[col]-mu)/sd,(test[col]-mu)/sd


def main():
    r=RedisConfig().client
    df=add_fwd(load_rows(r))
    print('rows',len(df))
    rows=[]
    for h in HORIZONS:
        y=f'fwd_{h}s_bps'
        for a,b in itertools.combinations(FEATURES,2):
            z=df[['observed_at_ms',a,b,y]].dropna().sort_values('observed_at_ms')
            if len(z)<100: continue
            cut=max(60,min(len(z)-30,int(len(z)*.70)))
            tr=z.iloc[:cut].copy(); te=z.iloc[cut:].copy()
            rho_ab=tr[a].corr(tr[b],method='spearman')
            if not np.isfinite(rho_ab) or abs(rho_ab)>=.85: continue
            ra=tr[a].corr(tr[y],method='spearman'); rb=tr[b].corr(tr[y],method='spearman')
            if not np.isfinite(ra) or not np.isfinite(rb): continue
            za_tr,za_te=zscore_apply(tr,te,a); zb_tr,zb_te=zscore_apply(tr,te,b)
            if za_tr is None or zb_tr is None: continue
            oa=1 if ra>=0 else -1; ob=1 if rb>=0 else -1
            tr['score']=oa*za_tr+ob*zb_tr; te['score']=oa*za_te+ob*zb_te
            q20,q80=tr.score.quantile([.2,.8])
            te=nonoverlap(te,h)
            te['side']=np.where(te.score>=q80,1,np.where(te.score<=q20,-1,0))
            sig=te[te.side!=0].copy(); sig['gross_bps']=sig.side*sig[y]
            g=sig.gross_bps.to_numpy(float)
            gross=float(np.mean(g)) if len(g) else np.nan
            rec={'horizon_s':h,'feature_a':a,'feature_b':b,'pair_rho':rho_ab,'train_rho_a':ra,'train_rho_b':rb,'test_nonoverlap_n':len(te),'trades':len(sig),'longs':int((sig.side==1).sum()),'shorts':int((sig.side==-1).sum()),'gross_ev_bps':gross,'winrate':float(np.mean(g>0)) if len(g) else np.nan}
            for c in COSTS: rec[f'net_ev_{int(c)}bps']=gross-c if np.isfinite(gross) else np.nan
            rec['evidence_status']='INSUFFICIENT_TRADES' if len(sig)<20 else ('CANDIDATE' if rec['net_ev_8bps']>0 and rec['winrate']>=.55 else 'REJECT_AFTER_COST')
            rows.append(rec)
    res=pd.DataFrame(rows)
    out=ROOT/'research/results/NEAR_MICRO_PAIR_ROBUST.csv'; out.parent.mkdir(parents=True,exist_ok=True); res.to_csv(out,index=False)
    if len(res):
        show=res.sort_values(['horizon_s','net_ev_8bps'],ascending=[True,False]).groupby('horizon_s').head(10)
        print(show[['horizon_s','feature_a','feature_b','pair_rho','trades','longs','shorts','gross_ev_bps','net_ev_8bps','winrate','evidence_status']].to_string(index=False))
    print('out',out)

if __name__=='__main__': main()
