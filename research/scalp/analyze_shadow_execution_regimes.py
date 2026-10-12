import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig

L1_STREAM='shadow:telemetry:execution_l1'
QUEUE_CSV=ROOT/'research/results/NEAR_SHADOW_EXECUTION_QUEUE.csv'
OUT=ROOT/'research/results/NEAR_SHADOW_EXECUTION_REGIMES.csv'
ANCHOR_OUT=ROOT/'research/results/NEAR_SHADOW_EXECUTION_REGIME_ANCHORS.csv'
SYMBOL='NEARUSDT'


def _load_l1(r,count=20000):
    rows=[]
    for _,f in r.xrevrange(L1_STREAM,count=count):
        try:d=json.loads(f.get('json') or '{}')
        except Exception:continue
        if str(d.get('symbol') or '').upper()!=SYMBOL:continue
        if int(d.get('schema_version') or 0)<2:continue
        rows.append(d)
    if not rows:return pd.DataFrame()
    x=pd.DataFrame(rows).drop_duplicates('observed_at_ms').sort_values('observed_at_ms')
    for c in ('observed_at_ms','mid','spread_bps'):
        x[c]=pd.to_numeric(x[c],errors='coerce')
    return x.dropna(subset=['observed_at_ms','mid','spread_bps']).reset_index(drop=True)


def _rv_bps(g,t0,sec):
    w=g[(g.observed_at_ms>=t0-sec*1000)&(g.observed_at_ms<=t0)]
    if len(w)<max(4,sec//3):return np.nan
    p=w.mid.to_numpy(float)
    p=p[np.isfinite(p)&(p>0)]
    if len(p)<4:return np.nan
    r=np.diff(np.log(p))*1e4
    return float(np.sqrt(np.sum(r*r))) if len(r) else np.nan


def _abs_move_bps(g,t0,sec):
    w=g[(g.observed_at_ms>=t0-sec*1000)&(g.observed_at_ms<=t0)]
    if len(w)<2:return np.nan
    a=float(w.iloc[0].mid); b=float(w.iloc[-1].mid)
    return abs((b-a)/a*1e4) if a>0 else np.nan


def _label_tercile(s):
    s=pd.to_numeric(s,errors='coerce')
    valid=s.dropna()
    if valid.nunique()<3:return pd.Series(['MID' if pd.notna(v) else 'NA' for v in s],index=s.index)
    q1,q2=valid.quantile([1/3,2/3]).tolist()
    def lab(v):
        if pd.isna(v):return 'NA'
        if v<=q1:return 'LOW'
        if v<=q2:return 'MID'
        return 'HIGH'
    return s.map(lab)


def main():
    if not QUEUE_CSV.exists():
        print('MISSING_QUEUE_CSV'); return
    q=pd.read_csv(QUEUE_CSV)
    if q.empty:
        print('EMPTY_QUEUE_CSV'); return
    r=RedisConfig().client
    l1=_load_l1(r)
    if l1.empty:
        print('NO_V2_L1'); return

    anchors=pd.DataFrame({'anchor_ms':sorted(pd.to_numeric(q.anchor_ms,errors='coerce').dropna().astype('int64').unique())})
    feats=[]
    for t0 in anchors.anchor_ms:
        prior=l1[l1.observed_at_ms<=t0]
        if prior.empty:continue
        a=prior.iloc[-1]
        age=t0-float(a.observed_at_ms)
        if age>1800:continue
        feats.append({'anchor_ms':int(t0),'spread_bps':float(a.spread_bps),
                      'rv10_bps':_rv_bps(l1,t0,10),'rv30_bps':_rv_bps(l1,t0,30),
                      'abs_move10_bps':_abs_move_bps(l1,t0,10),'abs_move30_bps':_abs_move_bps(l1,t0,30)})
    a=pd.DataFrame(feats)
    if a.empty:
        print('NO_MATCHED_REGIME_ANCHORS'); return
    a['spread_regime']=_label_tercile(a.spread_bps)
    a['vol10_regime']=_label_tercile(a.rv10_bps)
    a['vol30_regime']=_label_tercile(a.rv30_bps)
    a['regime']=a.spread_regime.astype(str)+'_SPREAD__'+a.vol30_regime.astype(str)+'_VOL30'
    a.to_csv(ANCHOR_OUT,index=False)

    x=q.merge(a,on='anchor_ms',how='inner')
    rows=[]
    dims=[('spread_regime','SPREAD'),('vol30_regime','VOL30'),('regime','JOINT')]
    for col,label in dims:
        for keys,g in x.groupby(['side','wait_s','queue_mult','maker_fee_bps',col]):
            side,wait,qm,mf,reg=keys
            # size robust inside each regime: compute per-size means, then take worst size.
            ps=[]
            for notion,gn in g.groupby('notional_usdt'):
                ps.append({'notional':float(notion),'n':int(gn.anchor_ms.nunique()),
                           'adv':float(gn.advantage_vs_market_bps.mean()),
                           'maker':float(gn.maker_incremental_bps.mean()),
                           'timing':float(gn.wait_timing_bps.mean()),
                           'fill':float(gn.fill_fraction.mean()),
                           'm5':float(gn.maker_weighted_markout_5s_bps.mean()),
                           'm15':float(gn.maker_weighted_markout_15s_bps.mean())})
            p=pd.DataFrame(ps)
            if p.empty:continue
            rows.append({'dimension':label,'regime':reg,'side':side,'wait_s':int(wait),
                         'queue_mult':float(qm),'maker_fee_bps':float(mf),
                         'notional_count':int(p.notional.nunique()),'n_min':int(p.n.min()),
                         'worst_advantage_bps':float(p.adv.min()),
                         'worst_maker_incremental_bps':float(p.maker.min()),
                         'worst_wait_timing_bps':float(p.timing.min()),
                         'min_fill_fraction':float(p.fill.min()),
                         'worst_markout5_bps':float(p.m5.min()),
                         'worst_markout15_bps':float(p.m15.min())})
    out=pd.DataFrame(rows)
    out.to_csv(OUT,index=False)
    print('anchors',len(a),'queue_rows',len(x),'regime_rows',len(out))
    print('spread_terciles')
    print(a.groupby('spread_regime').agg(n=('anchor_ms','size'),spread_mean=('spread_bps','mean')).to_string())
    print('vol30_terciles')
    print(a.groupby('vol30_regime').agg(n=('anchor_ms','size'),rv30_mean=('rv30_bps','mean')).to_string())
    focus=out[(out.queue_mult>=1.0)&(out.maker_fee_bps>=2.0)&(out.n_min>=8)].copy()
    if len(focus):
        print('\nCONSERVATIVE_RESEARCH_SEGMENTS')
        print(focus.sort_values('worst_maker_incremental_bps',ascending=False).head(30).to_string(index=False))
    print('out',OUT); print('anchors_out',ANCHOR_OUT)

if __name__=='__main__':main()
