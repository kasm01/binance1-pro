from __future__ import annotations
import json, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig
load_dotenv(ROOT/'.env',override=False)

H=(30,60,180); COSTS=(8.0,10.0,12.0); SESSION_GAP_MS=120_000
MIN_BODY=float(os.getenv('ENTRY_CONFIRM_MIN_BODY_RATIO','0.18'))
MAX_RET=float(os.getenv('ENTRY_CONFIRM_MAX_RETRACE_RATIO','0.45'))
REJ_RET=float(os.getenv('ENTRY_CONFIRM_REJECT_RETRACE_RATIO','0.70'))
MIN_Q=float(os.getenv('ENTRY_CONFIRM_MIN_QUALITY','0.55'))
MIN_P=float(os.getenv('SNIPER_ENTRY_MIN_CANDLE_PROGRESS','0.08'))
MAX_P=float(os.getenv('SNIPER_ENTRY_MAX_CANDLE_PROGRESS','0.52'))


def load(r):
    rows=[]
    for _,f in r.xrevrange('shadow:telemetry:entry_context_research',count=20000):
        try:d=json.loads(f.get('json') or '{}')
        except Exception:continue
        schema=int(d.get('schema_version') or 0)
        legacy_current=(d.get('m1_ret3') is not None and d.get('structure_close_time_ms') is not None)
        if d.get('symbol')=='NEARUSDT' and (schema>=2 or legacy_current) and d.get('mid') is not None:
            rows.append(d)
    if not rows:return pd.DataFrame()
    df=pd.DataFrame(rows).drop_duplicates('observed_at_ms').sort_values('observed_at_ms')
    nums=['observed_at_ms','mid','live1m_start_ms','live1m_progress','live1m_body_ratio','live1m_long_retrace_ratio','live1m_short_retrace_ratio','live1m_long_location','live1m_short_location']
    for c in nums:
        if c in df:df[c]=pd.to_numeric(df[c],errors='coerce')
    df=df.reset_index(drop=True)
    gap=df.observed_at_ms.diff().fillna(0)
    df['session_id']=(gap>SESSION_GAP_MS).cumsum().astype(int)
    return df


def add_fwd(df):
    out=df.copy()
    for h in H:out[f'fwd_{h}s_bps']=np.nan
    for sid,g in df.groupby('session_id',sort=False):
        base=g[['observed_at_ms','mid']].dropna().sort_values('observed_at_ms')
        if base.empty:continue
        fut=base.rename(columns={'observed_at_ms':'future_ms','mid':'future_mid'})
        for h in H:
            left=base[['observed_at_ms']].copy(); left['target']=left.observed_at_ms+h*1000
            m=pd.merge_asof(left.sort_values('target'),fut.sort_values('future_ms'),left_on='target',right_on='future_ms',direction='nearest',tolerance=max(3000,int(h*250)))
            vals=((m.future_mid.to_numpy()/base.mid.to_numpy())-1)*1e4
            out.loc[base.index,f'fwd_{h}s_bps']=vals
    return out


def quality(direction,body,retrace,loc):
    b=min(1.0,body/max(MIN_BODY,1e-9)); rq=max(0.0,1.0-retrace); dq=1.0 if direction else 0.0
    return .30*dq+.25*b+.25*rq+.20*max(0.0,min(1.0,loc))


def nonoverlap(z,h):
    keep=[];gap=h*1000
    for _,g in z.sort_values('observed_at_ms').groupby('session_id',sort=False):
        last=None
        for i,t in zip(g.index,g.observed_at_ms):
            if last is None or t-last>=gap:
                keep.append(i);last=t
    return z.loc[keep]


def block_ci(x,seed=42,n_boot=2000,block=3):
    x=np.asarray(x,dtype=float);x=x[np.isfinite(x)];n=len(x)
    if n<10:return (np.nan,np.nan)
    b=max(1,min(block,n));starts=np.arange(0,n-b+1);need=int(np.ceil(n/b));rng=np.random.default_rng(seed);means=[]
    for _ in range(n_boot):
        s=np.concatenate([x[i:i+b] for i in rng.choice(starts,size=need,replace=True)])[:n]
        means.append(float(np.mean(s)))
    return tuple(np.quantile(means,[.025,.975]))


def main():
    r=RedisConfig().client;df=load(r);print('rows',len(df),'sessions',df.session_id.nunique() if not df.empty else 0)
    if df.empty:return
    complete=df.get('live1m_complete_from_open',pd.Series(False,index=df.index)).astype('boolean').fillna(False).astype(bool)
    df=df[complete].copy()
    print('full_live1m_rows',len(df),'minute_buckets',df.live1m_start_ms.nunique() if 'live1m_start_ms' in df else 0)
    if len(df)<120 or df.live1m_start_ms.nunique()<20:
        print('INSUFFICIENT_ENTRY_CONFIRM_DATA need>=120 rows and >=20 minute buckets');return
    df=add_fwd(df);rec=[]
    for side in ('long','short'):
        direction=df[f'live1m_{side}_direction_support'].astype('boolean').fillna(False).astype(bool)
        retrace=pd.to_numeric(df[f'live1m_{side}_retrace_ratio'],errors='coerce')
        loc=pd.to_numeric(df[f'live1m_{side}_location'],errors='coerce')
        body=pd.to_numeric(df.live1m_body_ratio,errors='coerce')
        q=pd.Series([quality(a,b,c,d) if np.isfinite(b) and np.isfinite(c) and np.isfinite(d) else np.nan for a,b,c,d in zip(direction,body,retrace,loc)],index=df.index)
        timing=(df.live1m_progress>=MIN_P)&(df.live1m_progress<=MAX_P)
        ready=timing&direction&(retrace<MAX_RET)&(body>=MIN_BODY)&(q>=MIN_Q)
        block=retrace>=REJ_RET
        for h in H:
            cols=['observed_at_ms','session_id','live1m_start_ms',f'fwd_{h}s_bps']
            z=df[cols].copy();z['ready']=ready;z['block']=block;z=nonoverlap(z.dropna(),h)
            for label,mask in [('READY',z.ready),('NOT_READY',~z.ready),('STRONG_REVERSAL',z.block)]:
                x=z.loc[mask,f'fwd_{h}s_bps'].to_numpy(float);signed=x if side=='long' else -x
                if not len(signed):continue
                gross=float(np.mean(signed));ci_lo,ci_hi=block_ci(signed,seed=100+h+(0 if side=='long' else 1))
                row={'side':side,'horizon_s':h,'state':label,'n':len(signed),'minute_buckets':int(z.loc[mask,'live1m_start_ms'].nunique()),'sessions':int(z.loc[mask,'session_id'].nunique()),'gross_ev_bps':gross,'gross_ci95_lo_block':ci_lo,'gross_ci95_hi_block':ci_hi,'winrate':float(np.mean(signed>0))}
                for cost in COSTS:
                    row[f'net_ev_{int(cost)}bps']=gross-cost
                    row[f'net_ci95_lo_{int(cost)}bps']=ci_lo-cost if np.isfinite(ci_lo) else np.nan
                    row[f'net_ci95_hi_{int(cost)}bps']=ci_hi-cost if np.isfinite(ci_hi) else np.nan
                row['status']='INSUFFICIENT' if len(signed)<30 or row['minute_buckets']<20 else ('UNCERTAIN_BLOCK_CI' if not np.isfinite(row['net_ci95_lo_8bps']) or row['net_ci95_lo_8bps']<=0 else 'CANDIDATE')
                rec.append(row)
    res=pd.DataFrame(rec);out=ROOT/'research/results/NEAR_ENTRY_CONFIRMATION_SHADOW.csv';out.parent.mkdir(parents=True,exist_ok=True);res.to_csv(out,index=False)
    if len(res):
        cols=['side','horizon_s','state','n','minute_buckets','gross_ev_bps','net_ev_8bps','net_ev_10bps','net_ev_12bps','winrate','status']
        print(res[cols].to_string(index=False))
    print('out',out)

if __name__=='__main__':main()
