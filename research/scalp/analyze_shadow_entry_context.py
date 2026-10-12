from __future__ import annotations
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig

MICRO=['l1_imbalance','depth5_imbalance','depth20_imbalance','t5_signed_ratio','t15_signed_ratio','t30_signed_ratio','spread_bps','basis_bps']
CONTEXT=['m1_ret1','m1_ret3','m3_ret1','recovery_from_low','m3_ret1_mean3','m3_accel','m3_imbalance','m3_imb_mean3','m3_body','m3_range','m3_close_loc','price_vs_ema99_bps','ema7_vs_ema25_bps','oi_ret_period']
HORIZONS=(30,60,180)
COSTS=(8.0,10.0,12.0)
MIN_TRADES=30
MIN_UNIQUE_STRUCT=20
MIN_ABS_TRAIN_RHO=0.03
SESSION_GAP_MS=120_000


def load_rows(r,count=20000):
    rows=[]
    for _,f in r.xrevrange('shadow:telemetry:entry_context_research',count=count):
        raw=f.get('json') if isinstance(f,dict) else None
        if not raw: continue
        try: d=json.loads(raw)
        except Exception: continue
        if str(d.get('symbol') or '').upper()!='NEARUSDT': continue
        schema=int(d.get('schema_version') or 0)
        legacy_current=(d.get('m1_ret3') is not None and d.get('structure_close_time_ms') is not None)
        if schema < 2 and not legacy_current: continue
        if d.get('mid') is None or d.get('observed_at_ms') is None: continue
        rows.append(d)
    if not rows: return pd.DataFrame()
    df=pd.DataFrame(rows).drop_duplicates(subset=['observed_at_ms']).sort_values('observed_at_ms')
    nums=['observed_at_ms','mid','structure_close_time_ms','m3_close_time_ms','oi_source_ts_ms',*MICRO,*CONTEXT]
    for c in nums:
        if c in df.columns: df[c]=pd.to_numeric(df[c],errors='coerce')
    df=df.reset_index(drop=True)
    gap=df.observed_at_ms.diff().fillna(0)
    df['session_id']=(gap>SESSION_GAP_MS).cumsum().astype(int)
    return df


def add_fwd(df):
    out=df.copy()
    for h in HORIZONS: out[f'fwd_{h}s_bps']=np.nan
    for sid,g in df.groupby('session_id',sort=False):
        base=g[['observed_at_ms','mid']].dropna().sort_values('observed_at_ms')
        if base.empty: continue
        fut=base.rename(columns={'observed_at_ms':'future_ms','mid':'future_mid'})
        for h in HORIZONS:
            left=base[['observed_at_ms']].copy(); left['target_ms']=left.observed_at_ms+h*1000
            m=pd.merge_asof(left.sort_values('target_ms'),fut.sort_values('future_ms'),left_on='target_ms',right_on='future_ms',direction='nearest',tolerance=max(3000,int(h*250)))
            vals=((m.future_mid.to_numpy()/base.mid.to_numpy())-1)*1e4
            out.loc[base.index,f'fwd_{h}s_bps']=vals
    return out


def nonoverlap(z,h):
    keep=[]; gap=h*1000
    for _,g in z.sort_values('observed_at_ms').groupby('session_id',sort=False):
        last=None
        for i,t in zip(g.index,g.observed_at_ms):
            if last is None or t-last>=gap:
                keep.append(i); last=t
    return z.loc[keep]


def block_bootstrap_ci(x,seed=42,n_boot=2000,block=3):
    x=np.asarray(x,dtype=float); x=x[np.isfinite(x)]
    n=len(x)
    if n<10: return (np.nan,np.nan)
    b=max(1,min(int(block),n))
    starts=np.arange(0,n-b+1)
    rng=np.random.default_rng(seed); means=np.empty(n_boot)
    need=int(np.ceil(n/b))
    for k in range(n_boot):
        chunks=[x[s:s+b] for s in rng.choice(starts,size=need,replace=True)]
        sample=np.concatenate(chunks)[:n]
        means[k]=sample.mean()
    return tuple(np.quantile(means,[.025,.975]))


def side_stats(sig,side_value,cost=8.0):
    s=sig[sig.side==side_value]
    g=s.gross_bps.to_numpy(float)
    if len(g)==0: return (0,np.nan,np.nan)
    return (len(g),float(np.mean(g)-cost),float(np.mean(g>0)))


def main():
    r=RedisConfig().client; df=load_rows(r)
    print('rows',len(df),'sessions',df.session_id.nunique() if not df.empty else 0)
    if len(df)<120:
        print('INSUFFICIENT_ENRICHED_DATA need>=120'); return
    df=add_fwd(df); rows=[]; side_rows=[]
    for h in HORIZONS:
        y=f'fwd_{h}s_bps'
        for a,b in itertools.product(MICRO,CONTEXT):
            if a not in df or b not in df: continue
            cols=['observed_at_ms','session_id','structure_close_time_ms',a,b,y]
            z=df[cols].dropna().sort_values('observed_at_ms')
            if len(z)<100: continue
            cut=max(60,min(len(z)-30,int(len(z)*.70)))
            tr=z.iloc[:cut].copy(); te=z.iloc[cut:].copy()
            pair_rho=tr[a].corr(tr[b],method='spearman')
            if np.isfinite(pair_rho) and abs(pair_rho)>=.85: continue
            ra=tr[a].corr(tr[y],method='spearman'); rb=tr[b].corr(tr[y],method='spearman')
            if not np.isfinite(ra) or not np.isfinite(rb): continue
            valid=True
            for col,rho in ((a,ra),(b,rb)):
                mu=tr[col].mean(); sd=tr[col].std(ddof=0)
                if not np.isfinite(sd) or sd<1e-12: valid=False; break
                tr[col+'_z']=(tr[col]-mu)/sd; te[col+'_z']=(te[col]-mu)/sd
            if not valid: continue
            tr['score']=(1 if ra>=0 else -1)*tr[a+'_z']+(1 if rb>=0 else -1)*tr[b+'_z']
            te['score']=(1 if ra>=0 else -1)*te[a+'_z']+(1 if rb>=0 else -1)*te[b+'_z']
            q20,q80=tr.score.quantile([.2,.8]); te=nonoverlap(te,h)
            te['side']=np.where(te.score>=q80,1,np.where(te.score<=q20,-1,0))
            sig=te[te.side!=0].copy(); sig['gross_bps']=sig.side*sig[y]
            g=sig.gross_bps.to_numpy(float)
            gross=float(np.mean(g)) if len(g) else np.nan
            unique_struct=int(sig.structure_close_time_ms.nunique()) if len(sig) else 0
            ci_lo,ci_hi=block_bootstrap_ci(g,seed=42+h,block=3)
            win=float(np.mean(g>0)) if len(g) else np.nan
            long_n,long_net8,long_win=side_stats(sig,1,8.0)
            short_n,short_net8,short_win=side_stats(sig,-1,8.0)
            base={'horizon_s':h,'micro_feature':a,'context_feature':b,'pair_rho':pair_rho,
                  'train_rho_micro':ra,'train_rho_context':rb,'trades':len(sig),
                  'unique_structure_buckets':unique_struct,'sessions_tested':int(sig.session_id.nunique()) if len(sig) else 0,
                  'longs':long_n,'shorts':short_n,'gross_ev_bps':gross,'gross_ci95_lo_block':ci_lo,'gross_ci95_hi_block':ci_hi,
                  'winrate':win,'long_net_ev_8bps':long_net8,'short_net_ev_8bps':short_net8,'long_winrate':long_win,'short_winrate':short_win}
            for cost in COSTS:
                base[f'net_ev_{int(cost)}bps']=gross-cost if np.isfinite(gross) else np.nan
                base[f'net_ci95_lo_{int(cost)}bps']=ci_lo-cost if np.isfinite(ci_lo) else np.nan
                base[f'net_ci95_hi_{int(cost)}bps']=ci_hi-cost if np.isfinite(ci_hi) else np.nan
            if len(sig)<MIN_TRADES:
                status='INSUFFICIENT_TRADES'
            elif unique_struct<MIN_UNIQUE_STRUCT:
                status='INSUFFICIENT_BUCKETS'
            elif min(abs(ra),abs(rb))<MIN_ABS_TRAIN_RHO:
                status='WEAK_TRAIN_SIGNAL'
            elif not np.isfinite(base['net_ci95_lo_8bps']) or base['net_ci95_lo_8bps']<=0:
                status='UNCERTAIN_BLOCK_CI'
            elif base['net_ev_8bps']>0 and win>=.55:
                status='CANDIDATE'
            else:
                status='REJECT_AFTER_COST'
            base['evidence_status']=status; rows.append(base)

            for side_value,side_name in ((1,'long'),(-1,'short')):
                ss=sig[sig.side==side_value].copy()
                sg=ss.gross_bps.to_numpy(float)
                sn=len(ss)
                sb=int(ss.structure_close_time_ms.nunique()) if sn else 0
                sci_lo,sci_hi=block_bootstrap_ci(sg,seed=142+h+(0 if side_value==1 else 1),block=3)
                swin=float(np.mean(sg>0)) if sn else np.nan
                srow={'side':side_name,'horizon_s':h,'micro_feature':a,'context_feature':b,
                      'trades':sn,'unique_structure_buckets':sb,
                      'sessions_tested':int(ss.session_id.nunique()) if sn else 0,
                      'gross_ev_bps':float(np.mean(sg)) if sn else np.nan,
                      'gross_ci95_lo_block':sci_lo,'gross_ci95_hi_block':sci_hi,'winrate':swin}
                for cost in COSTS:
                    srow[f'net_ev_{int(cost)}bps']=srow['gross_ev_bps']-cost if np.isfinite(srow['gross_ev_bps']) else np.nan
                    srow[f'net_ci95_lo_{int(cost)}bps']=sci_lo-cost if np.isfinite(sci_lo) else np.nan
                    srow[f'net_ci95_hi_{int(cost)}bps']=sci_hi-cost if np.isfinite(sci_hi) else np.nan
                if sn<MIN_TRADES:
                    sstatus='INSUFFICIENT_TRADES'
                elif sb<MIN_UNIQUE_STRUCT:
                    sstatus='INSUFFICIENT_BUCKETS'
                elif not np.isfinite(srow['net_ci95_lo_8bps']) or srow['net_ci95_lo_8bps']<=0:
                    sstatus='UNCERTAIN_BLOCK_CI'
                elif srow['net_ev_8bps']>0 and swin>=.55:
                    sstatus='CANDIDATE'
                else:
                    sstatus='REJECT_AFTER_COST'
                srow['evidence_status']=sstatus
                side_rows.append(srow)
    res=pd.DataFrame(rows); out=ROOT/'research/results/NEAR_ENTRY_CONTEXT_ROBUST.csv'; out.parent.mkdir(parents=True,exist_ok=True); res.to_csv(out,index=False)
    sres=pd.DataFrame(side_rows); sout=ROOT/'research/results/NEAR_ENTRY_CONTEXT_BY_SIDE.csv'; sres.to_csv(sout,index=False)
    if len(res):
        cols=['horizon_s','micro_feature','context_feature','trades','unique_structure_buckets','gross_ev_bps','net_ev_8bps','net_ev_10bps','net_ev_12bps','long_net_ev_8bps','short_net_ev_8bps','winrate','evidence_status']
        print(res.sort_values(['horizon_s','net_ev_8bps'],ascending=[True,False]).groupby('horizon_s').head(8)[cols].to_string(index=False))
    print('out',out)

if __name__=='__main__': main()
