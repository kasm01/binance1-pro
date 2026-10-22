from __future__ import annotations
from pathlib import Path
import json, os, random, sys
import joblib
import numpy as np
import pandas as pd

ROOT=Path('/home/kasm920/binance1-pro'); sys.path.insert(0,str(ROOT))
from config.load_env import load_environment_variables
load_environment_variables()
from features.fe_labels import build_features
import research.scalp.simulate_long1_near_mtf as sim

SYM='AVAXUSDT'
HIST_START=pd.Timestamp('2025-09-22 00:00:00',tz='UTC')
HIST_END=pd.Timestamp('2026-09-14 19:20:00',tz='UTC')
FWD_START=HIST_END
FWD_END=pd.Timestamp('2026-10-11 21:36:00',tz='UTC')
FEE=float(os.getenv('OUTCOME_TAKER_FEE_RATE','.0004') or .0004)
SL=.0299; CAT=.035; CONFIRM=30.; STALL_MIN=.001; STALL=2400.; LEV=3.; TP_PRICE=.02; ROI_TP=.04; ROI_GB=.0024; REENTRY=180
OUT=ROOT/'research/results/LONG2_AVAX_VALIDATION_V1_20261022'; OUT.mkdir(parents=True,exist_ok=True)

def load_scored():
    parts=[pd.read_csv(ROOT/'data/offline_cache/AVAXUSDT_1m_360d.csv'),pd.read_csv(ROOT/'research/data/AVAXUSDT_1m_1month.csv')]
    d=pd.concat(parts,ignore_index=True).drop_duplicates('open_time').sort_values('open_time').reset_index(drop=True)
    ts=pd.to_datetime(d.open_time,unit='ms',utc=True)
    d=d[(ts>=HIST_START-pd.Timedelta(days=3))&(ts<FWD_END)].copy().reset_index(drop=True)
    for c in ('open','high','low','close','volume','quote_asset_volume','taker_buy_quote_volume'):
        d[c]=pd.to_numeric(d[c],errors='coerce')
    q=d.quote_asset_volume; b=d.taker_buy_quote_volume; net=2*b-q
    d['flow60_prev']=(net.rolling(60,min_periods=60).sum()/q.rolling(60,min_periods=60).sum()).shift(1)
    D=d.copy(); D['bucket']=pd.to_datetime(D.open_time,unit='ms',utc=True).dt.floor('3min')
    amap={'open':('open','first'),'high':('high','max'),'low':('low','min'),'close':('close','last'),'volume':('volume','sum'),'open_time':('open_time','first'),'close_time':('close_time','last'),'n':('open_time','size')}
    for c in ('quote_asset_volume','number_of_trades','taker_buy_base_volume','taker_buy_quote_volume'):
        if c in D.columns: amap[c]=(c,'sum')
    if 'ignore' in D.columns: amap['ignore']=('ignore','last')
    a=D.groupby('bucket',sort=True).agg(**amap).reset_index(drop=True); a=a[a.n==3].drop(columns='n').reset_index(drop=True)
    meta=json.loads((ROOT/'models/model_meta_AVAXUSDT_3m.json').read_text()); model=joblib.load(ROOT/'models/online_model_AVAXUSDT_3m_best.joblib')
    feat=build_features(a,interval='3m').reindex(columns=list(meta['feature_schema'])).apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan).fillna(0.0)
    proba=np.asarray(model.predict_proba(feat.to_numpy(float)),float); score=proba[:,-1] if proba.ndim==2 else proba.reshape(-1); score=score[-len(a):]
    opens=d.open_time.to_numpy(np.int64); rows=[]
    for r,sc in zip(a.itertuples(index=False),score):
        j=int(np.searchsorted(opens,int(r.close_time)+1,'left'))
        if j<len(d): rows.append((j,float(sc),int(d.iloc[j].open_time)))
    return d,rows

def run(d,scored,seed,threshold=.54,flowmax=.20):
    items=[(j,sc) for j,sc,_ in scored if sc>=threshold]; bal=1000.; trades=[]; ep=0; i=0; pos=None; last_exit=-10**30; n=len(d)
    def prog(ei): return random.Random(seed*1000003+int(d.iloc[ei].open_time)*17//60000+19).uniform(.08,.52)
    while i<n:
        while ep<len(items) and items[ep][0]<i: ep+=1
        if pos is None:
            if ep>=len(items): break
            ei,_=items[ep]; i=ei; r=d.iloc[i]; oms=int(r.open_time); ep+=1
            if oms<last_exit+REENTRY*1000: continue
            f60=float(r.flow60_prev) if pd.notna(r.flow60_prev) else np.nan
            if flowmax is not None and np.isfinite(f60) and f60>=flowmax: continue
            q=prog(ei); px=sim.interp(sim.nodes(r),q); notion=bal; qty=notion/px; t0=oms+int(q*60000)
            pos={'qty':qty,'avg':px,'notional':notion,'bestp':0.,'bestr':0.,'lastbest':t0,'armed':False,'fees':notion*FEE,'pending':None,'entry':t0,'entry_row':i,'entry_progress':q}; continue
        closed=False
        for k in range(i,n):
            r=d.iloc[k]; oms=int(r.open_time); min_q=float(pos['entry_progress']) if k==pos['entry_row'] else 0.0
            for q,px in sim.samples(r,0.0):
                if q<min_q: continue
                now=oms+int(q*60000); pnl=(px-pos['avg'])/pos['avg']; roi=pnl*LEV
                if pnl>pos['bestp']: pos['bestp']=pnl; pos['lastbest']=now
                if roi>pos['bestr']: pos['bestr']=roi
                if pos['bestr']>=ROI_TP: pos['armed']=True
                reason=None
                if pnl<=-CAT: reason='cat'
                else:
                    if pnl<=-SL:
                        if pos['pending'] is None: pos['pending']=now
                        elif now-pos['pending']>=CONFIRM*1000: reason='sl'
                    elif pos['pending'] is not None: pos['pending']=None
                if reason is None and pos['armed'] and roi<=pos['bestr']-ROI_GB: reason='gb'
                elif reason is None and px>=pos['avg']*(1+TP_PRICE): reason='tp'
                elif reason is None and pnl>=STALL_MIN and (now-pos['lastbest'])/1000>=STALL: reason='stall'
                if reason:
                    before=bal; gross=(px-pos['avg'])*pos['qty']; fees=pos['fees']+pos['qty']*px*FEE; net=gross-fees; bal+=net
                    trades.append((pos['entry'],now,pos['notional'],net,fees,reason,before,bal)); last_exit=now; pos=None; i=k; closed=True; break
            if closed: break
        if not closed: break
    t=pd.DataFrame(trades,columns=['entry','exit','notional','net','fees','reason','before','bal'])
    eq=np.r_[1000.,t.bal.to_numpy(float)] if len(t) else np.array([1000.]); pk=np.maximum.accumulate(eq); dd=100*(eq/pk-1)
    gp=t.loc[t.net>0,'net'].sum(); gl=-t.loc[t.net<0,'net'].sum()
    return {'return_pct':(bal/1000-1)*100,'trades':len(t),'win_pct':100*(t.net>0).mean() if len(t) else 0.,'pf':gp/max(gl,1e-12),'dd_pct':dd.min(),'fees':t.fees.sum()},t

def period_rows(trades,seed,freq):
    if len(trades)==0:return []
    z=trades.copy(); z['ts']=pd.to_datetime(z.exit,unit='ms',utc=True)
    if freq=='daily': z['period']=z.ts.dt.strftime('%Y-%m-%d')
    elif freq=='weekly':
        iso=z.ts.dt.isocalendar(); z['period']=iso.year.astype(str)+'-W'+iso.week.astype(str).str.zfill(2)
    else:z['period']=z.ts.dt.strftime('%Y-%m')
    out=[]
    for per,g in z.groupby('period'):
        start=float(g.iloc[0].before); ret=100*float(g.net.sum())/start if start>0 else np.nan; gp=g.loc[g.net>0,'net'].sum(); gl=-g.loc[g.net<0,'net'].sum()
        eq=np.r_[start,g.bal.to_numpy(float)]; pk=np.maximum.accumulate(eq); dd=100*(eq/pk-1).min()
        out.append({'seed':seed,'period':per,'return_pct':ret,'dd_pct':dd,'pf':gp/max(gl,1e-12),'trades':len(g)})
    return out

def main():
    d,all_scored=load_scored(); hist0=int(HIST_START.timestamp()*1000); hist1=int(HIST_END.timestamp()*1000); fwd1=int(FWD_END.timestamp()*1000)
    hist=[x for x in all_scored if hist0<=x[2]<hist1]; fwd=[x for x in all_scored if hist1<=x[2]<fwd1]
    grid=[]
    for th in (.520,.525,.530,.535):
        for fm in (None,.15,.20,.25):
            rr=[]
            for seed in range(1,7):
                s,_=run(d,hist,seed,th,fm); rr.append(s)
            z=pd.DataFrame(rr); grid.append({'threshold':th,'flow60_max':'NONE' if fm is None else fm,'return_mean':z.return_pct.mean(),'return_min':z.return_pct.min(),'return_std':z.return_pct.std(),'pf_mean':z.pf.mean(),'dd_mean':z.dd_pct.mean(),'dd_worst':z.dd_pct.min(),'trades_mean':z.trades.mean(),'win_mean':z.win_pct.mean(),'fees_mean':z.fees.mean()})
    G=pd.DataFrame(grid); G.to_csv(OUT/'threshold_flow_grid.csv',index=False); print('GRID\n'+G.to_string(index=False),flush=True)
    base=[]; temporal={'daily':[],'weekly':[],'monthly':[]}
    for seed in range(1,7):
        s,t=run(d,hist,seed,.525,.20); base.append({'seed':seed,**s}); t.to_csv(OUT/f'hist_seed{seed}_trades.csv',index=False)
        for freq in temporal: temporal[freq]+=period_rows(t,seed,freq)
    B=pd.DataFrame(base); B.to_csv(OUT/'hist_base_by_seed.csv',index=False); print('HIST_BASE\n'+B.to_string(index=False),flush=True)
    for freq,rows in temporal.items():
        x=pd.DataFrame(rows); x.to_csv(OUT/f'{freq}_by_seed.csv',index=False)
        a=x.groupby('period').agg(return_mean=('return_pct','mean'),return_min=('return_pct','min'),return_max=('return_pct','max'),dd_worst=('dd_pct','min'),pf_mean=('pf','mean'),trades_mean=('trades','mean')).reset_index(); a.to_csv(OUT/f'{freq}_aggregate.csv',index=False)
        print(freq.upper(),'n',len(a),'positive',int((a.return_mean>0).sum()),'negative',int((a.return_mean<0).sum()),'worst',a.nsmallest(5,'return_mean').to_dict('records'),'best',a.nlargest(5,'return_mean').to_dict('records'),flush=True)
    fw=[]
    for seed in range(1,7):
        s,t=run(d,fwd,seed,.525,.20); fw.append({'seed':seed,**s}); t.to_csv(OUT/f'fwd_seed{seed}_trades.csv',index=False)
    F=pd.DataFrame(fw); F.to_csv(OUT/'forward_by_seed.csv',index=False); print('FORWARD\n'+F.to_string(index=False),flush=True); print('FORWARD_MEAN',F.mean(numeric_only=True).to_dict(),flush=True)
if __name__=='__main__':main()
