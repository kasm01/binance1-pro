from pathlib import Path
import pandas as pd, numpy as np
ROOT=Path('/home/kasm920/binance1-pro')
LONG_DIR=ROOT/'research/results/LONG1_SINGLE_F60_020_POSITIONS_20261021'
SHORT_DIR=Path('/home/kasm920/binance1/research/short/results/SHORT1_V49B_TRADE_CONFIRM/V49B_R70_W2')
OUT=ROOT/'research/results/LONG1_SHORT1_EXPOSURE_OVERLAP_V1_20261021'
OUT.mkdir(parents=True,exist_ok=True)

def prep_short():
    e=pd.read_csv(SHORT_DIR/'entries.csv'); c=pd.read_csv(SHORT_DIR/'closed_positions.csv')
    e['ts']=pd.to_datetime(e.ts,utc=True); c['open_ts']=pd.to_datetime(c.open_ts,utc=True); c['close_ts']=pd.to_datetime(c.close_ts,utc=True)
    # V49B is single-position. Exact open timestamps should map one-to-one to layer1 entry.
    e=e[e.layer==1].copy().sort_values('ts')
    m=c.merge(e[['ts','notional']],left_on='open_ts',right_on='ts',how='left',validate='one_to_one')
    if m.notional.isna().any():
        raise RuntimeError(f'short_notional_missing={m.notional.isna().sum()}')
    # Reconstruct pre-trade equity recursively from realized pnl; start equity = 1000.
    eq=[]; bal=1000.0
    for r in m.sort_values('close_ts').itertuples():
        # open positions do not overlap within this strategy, so balance before open equals prior realized balance.
        eq.append((r.open_ts,bal))
        bal += float(r.pnl_net)
    eqmap={t:b for t,b in eq}
    m['engine_equity_before']=m.open_ts.map(eqmap)
    m['requested_ratio']=m.notional/m.engine_equity_before
    return m[['open_ts','close_ts','notional','engine_equity_before','requested_ratio','pnl_net','reason']].sort_values('open_ts')

def prep_long(seed):
    p=LONG_DIR/f'seed{seed}.csv'
    x=pd.read_csv(p)
    x['open_ts']=pd.to_datetime(x.entry_ts,utc=True,format='mixed'); x['close_ts']=pd.to_datetime(x.exit_ts,utc=True,format='mixed')
    x['engine_equity_before']=x['before'].astype(float)
    x['requested_ratio']=x['notional'].astype(float)/x['engine_equity_before']
    return x[['open_ts','close_ts','notional','engine_equity_before','requested_ratio','net','reason']].sort_values('open_ts')

def active_at(df,t):
    z=df[(df.open_ts<=t)&(df.close_ts>t)]
    return z.iloc[0] if len(z) else None

def analyze(seed, L, S):
    start=max(L.open_ts.min(),S.open_ts.min()); end=min(L.close_ts.max(),S.close_ts.max())
    # Piecewise-constant requested exposure changes only at opens/closes.
    times=sorted(set([start,end]+L.loc[(L.open_ts>=start)&(L.open_ts<=end),'open_ts'].tolist()+L.loc[(L.close_ts>=start)&(L.close_ts<=end),'close_ts'].tolist()+S.loc[(S.open_ts>=start)&(S.open_ts<=end),'open_ts'].tolist()+S.loc[(S.close_ts>=start)&(S.close_ts<=end),'close_ts'].tolist()))
    rows=[]
    for a,b in zip(times[:-1],times[1:]):
        if b<=a: continue
        mid=a+(b-a)/2
        lr=active_at(L,mid); sr=active_at(S,mid)
        lreq=float(lr.requested_ratio) if lr is not None else 0.0
        sreq=float(sr.requested_ratio) if sr is not None else 0.0
        # 50/50 strategy allocation: engine ratio is relative to its half-budget.
        l50=.5*lreq; s50=.5*sreq
        dur=(b-a).total_seconds()
        rows.append({'seed':seed,'start':a,'end':b,'duration_sec':dur,'long_active':lr is not None,'short_active':sr is not None,
                     'long_native_ratio':lreq,'short_native_ratio':sreq,
                     'gross_native_ratio':lreq+sreq,'abs_net_native_ratio':abs(lreq-sreq),
                     'long_eq50_ratio':l50,'short_eq50_ratio':s50,
                     'gross_eq50_ratio':l50+s50,'abs_net_eq50_ratio':abs(l50-s50)})
    R=pd.DataFrame(rows)
    if R.empty: raise RuntimeError('empty overlap')
    total=R.duration_sec.sum(); both=R.loc[R.long_active & R.short_active,'duration_sec'].sum()
    def twavg(col): return float((R[col]*R.duration_sec).sum()/total)
    def twpct(cond): return float(R.loc[cond,'duration_sec'].sum()/total*100)
    # Time-weighted empirical quantiles by expanding duration weights approximately via sorted cumulative weights.
    def wq(col,q):
        z=R[[col,'duration_sec']].sort_values(col); cw=z.duration_sec.cumsum(); target=q*z.duration_sec.sum(); return float(z.loc[cw>=target,col].iloc[0])
    rec={'seed':seed,'window_start':start,'window_end':end,'days':(end-start).total_seconds()/86400,
         'both_active_time_pct':both/total*100,
         'any_active_time_pct':twpct(R.long_active|R.short_active),
         'flat_time_pct':twpct(~R.long_active&~R.short_active),
         'gross_eq50_twavg':twavg('gross_eq50_ratio'),'net_eq50_twavg':twavg('abs_net_eq50_ratio'),
         'gross_eq50_p90':wq('gross_eq50_ratio',.90),'gross_eq50_p95':wq('gross_eq50_ratio',.95),'gross_eq50_p99':wq('gross_eq50_ratio',.99),'gross_eq50_max':float(R.gross_eq50_ratio.max()),
         'net_eq50_p90':wq('abs_net_eq50_ratio',.90),'net_eq50_p95':wq('abs_net_eq50_ratio',.95),'net_eq50_p99':wq('abs_net_eq50_ratio',.99),'net_eq50_max':float(R.abs_net_eq50_ratio.max()),
         'gross_native_max':float(R.gross_native_ratio.max()),'net_native_max':float(R.abs_net_native_ratio.max())}
    R.to_csv(OUT/f'intervals_seed{seed}.csv',index=False)
    return rec

S=prep_short(); S.to_csv(OUT/'short_positions_normalized.csv',index=False)
print('SHORT ratios',S.requested_ratio.describe(percentiles=[.1,.5,.9,.99]).to_dict(),flush=True)
rows=[]
for seed in range(1,7):
    L=prep_long(seed); L.to_csv(OUT/f'long_seed{seed}_positions_normalized.csv',index=False)
    rec=analyze(seed,L,S); rows.append(rec); print('SEED',seed,rec,flush=True)
R=pd.DataFrame(rows); R.to_csv(OUT/'summary_by_seed.csv',index=False)
print('\nAGG')
for c in ['both_active_time_pct','any_active_time_pct','gross_eq50_twavg','gross_eq50_p90','gross_eq50_p95','gross_eq50_p99','gross_eq50_max','net_eq50_p95','net_eq50_p99','net_eq50_max']:
    print(c,'mean',R[c].mean(),'min',R[c].min(),'max',R[c].max())
