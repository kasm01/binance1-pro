from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig

STREAM='shadow:telemetry:execution_l1'
SYMBOL='NEARUSDT'
WAIT_SECS=(1,2,3)
TAKER_BPS=4.0
MAKER_BPS_SCENARIOS=(0.0,2.0,4.0)
ANCHOR_GAP_MS=10000
SESSION_GAP_MS=120000


def load_rows(r,count=20000):
    rows=[]
    for _,f in r.xrevrange(STREAM,count=count):
        try:d=json.loads(f.get('json') or '{}')
        except Exception:continue
        if str(d.get('symbol') or '').upper()!=SYMBOL: continue
        if int(d.get('schema_version') or 0) < 2: continue
        if d.get('observed_at_ms') is None: continue
        rows.append(d)
    if not rows:return pd.DataFrame()
    df=pd.DataFrame(rows).drop_duplicates('observed_at_ms').sort_values('observed_at_ms')
    nums=['observed_at_ms','best_bid','best_ask','mid','spread_bps','t1_count','t1_min_price','t1_max_price']
    for c in nums:
        if c in df: df[c]=pd.to_numeric(df[c],errors='coerce')
    df=df.dropna(subset=['observed_at_ms','best_bid','best_ask','mid']).reset_index(drop=True)
    gap=df.observed_at_ms.diff().fillna(0)
    df['session_id']=(gap>SESSION_GAP_MS).cumsum().astype(int)
    return df


def anchors(df):
    keep=[]
    for sid,g in df.groupby('session_id',sort=False):
        last=None
        for i,t in zip(g.index,g.observed_at_ms):
            if last is None or t-last>=ANCHOR_GAP_MS:
                keep.append(i); last=t
    return df.loc[keep].copy()


def at_or_after(g,target_ms,max_lag_ms=1800):
    x=g[g.observed_at_ms>=target_ms]
    if x.empty:return None
    row=x.iloc[0]
    if row.observed_at_ms-target_ms>max_lag_ms:return None
    return row


def _has_exact_trade_touch(levels,side,limit_px):
    if not isinstance(levels,list): return False
    for item in levels:
        if not isinstance(item,(list,tuple)) or len(item)<2: continue
        try: px=float(item[0]); q=float(item[1])
        except Exception: continue
        if q<=0 or px<=0: continue
        if side=='long' and px<=limit_px: return True
        if side=='short' and px>=limit_px: return True
    return False


def fill_touch(window,side,limit_px):
    if window.empty:return None
    col='interval_sell_levels' if side=='long' else 'interval_buy_levels'
    if col not in window.columns:return None
    return bool(any(_has_exact_trade_touch(v,side,limit_px) for v in window[col].tolist()))


def fill_cross(window,side,limit_px):
    if window.empty:return False
    if side=='long': return bool((window.best_ask<=limit_px).any())
    return bool((window.best_bid>=limit_px).any())


def entry_edge_bps(side,ref_mid,entry_px,fee_bps):
    if side=='long': px_edge=(ref_mid-entry_px)/ref_mid*1e4
    else: px_edge=(entry_px-ref_mid)/ref_mid*1e4
    return float(px_edge-fee_bps)


def main():
    r=RedisConfig().client; df=load_rows(r)
    print('rows',len(df),'sessions',df.session_id.nunique() if len(df) else 0)
    if len(df)<30:
        for name in ('NEAR_SHADOW_EXECUTION.csv','NEAR_SHADOW_EXECUTION_SUMMARY.csv'):
            q=ROOT/'research/results'/name
            if q.exists(): q.unlink()
        print('INSUFFICIENT_EXECUTION_DATA_V2'); return
    anc=anchors(df); rec=[]
    for _,a in anc.iterrows():
        g=df[df.session_id==a.session_id]
        t0=float(a.observed_at_ms); bid=float(a.best_bid); ask=float(a.best_ask); mid=float(a.mid)
        if bid<=0 or ask<=0 or mid<=0: continue
        for side in ('long','short'):
            market_px=ask if side=='long' else bid
            market_edge=entry_edge_bps(side,mid,market_px,TAKER_BPS)
            limit_px=bid if side=='long' else ask
            for wait in WAIT_SECS:
                deadline=t0+wait*1000
                window=g[(g.observed_at_ms>t0)&(g.observed_at_ms<=deadline+300)]
                touch=fill_touch(window,side,limit_px)
                cross=fill_cross(window,side,limit_px)
                fb=at_or_after(g,deadline)
                if fb is None: continue
                fallback_px=float(fb.best_ask if side=='long' else fb.best_bid)
                for maker_fee in MAKER_BPS_SCENARIOS:
                    models=[('BOOK_CROSS',cross)]
                    if touch is not None: models.append(('TRADE_TOUCH',touch))
                    for model,filled in models:
                        if filled:
                            exec_px=limit_px; fee=maker_fee; used_fallback=False
                        else:
                            exec_px=fallback_px; fee=TAKER_BPS; used_fallback=True
                        edge=entry_edge_bps(side,mid,exec_px,fee)
                        rec.append({
                            'side':side,'wait_s':wait,'fill_model':model,'maker_fee_bps':maker_fee,
                            'filled_maker':bool(filled),'fallback':bool(used_fallback),
                            'spread_bps':float(a.spread_bps) if np.isfinite(a.spread_bps) else np.nan,
                            'market_now_edge_bps':market_edge,'strategy_edge_bps':edge,
                            'advantage_vs_market_bps':edge-market_edge,
                            'fallback_move_bps':((fallback_px-market_px)/mid*1e4)*(1 if side=='short' else -1),
                            'session_id':int(a.session_id),'anchor_ms':int(a.observed_at_ms),
                        })
    x=pd.DataFrame(rec)
    out=ROOT/'research/results/NEAR_SHADOW_EXECUTION.csv'; out.parent.mkdir(parents=True,exist_ok=True); x.to_csv(out,index=False)
    if x.empty:
        print('NO_EXECUTION_ROWS'); return
    s=(x.groupby(['side','wait_s','fill_model','maker_fee_bps'])
       .agg(n=('filled_maker','size'),sessions=('session_id','nunique'),maker_fill_pct=('filled_maker','mean'),fallback_pct=('fallback','mean'),
            avg_advantage_bps=('advantage_vs_market_bps','mean'),median_advantage_bps=('advantage_vs_market_bps','median'),
            avg_fallback_move_bps=('fallback_move_bps','mean'))
       .reset_index())
    ci_lo=[]; ci_hi=[]
    rng=np.random.default_rng(42)
    for _,row in s.iterrows():
        g=x[(x.side==row.side)&(x.wait_s==row.wait_s)&(x.fill_model==row.fill_model)&(x.maker_fee_bps==row.maker_fee_bps)]
        vals=g.advantage_vs_market_bps.to_numpy(float)
        if len(vals)<20:
            ci_lo.append(np.nan); ci_hi.append(np.nan); continue
        means=[rng.choice(vals,size=len(vals),replace=True).mean() for _ in range(2000)]
        lo,hi=np.quantile(means,[.025,.975]); ci_lo.append(float(lo)); ci_hi.append(float(hi))
    s['adv_ci95_lo_bps']=ci_lo; s['adv_ci95_hi_bps']=ci_hi
    s['maker_fill_pct']*=100; s['fallback_pct']*=100
    s['status']=np.where(s['n']>=30,'OBSERVE','INSUFFICIENT_ANCHORS')
    sout=ROOT/'research/results/NEAR_SHADOW_EXECUTION_SUMMARY.csv'; s.to_csv(sout,index=False)
    print(s.sort_values(['fill_model','maker_fee_bps','wait_s','side']).to_string(index=False))
    print('out',out); print('summary',sout)

if __name__=='__main__': main()
