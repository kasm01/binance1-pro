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

SYMS=['NEARUSDT','AVAXUSDT','DOGEUSDT','LINKUSDT','SOLUSDT']
COMMON_START=pd.Timestamp('2025-09-22 00:00:00',tz='UTC')
COMMON_END=pd.Timestamp('2026-09-14 19:20:00',tz='UTC')
FEE=float(os.getenv('OUTCOME_TAKER_FEE_RATE','.0004') or .0004)
SL=.0299; CAT=.035; CONFIRM=30.; STALL_MIN=.001; STALL=2400.; LEV=3.; TP_PRICE=.02; ROI_TP=.04; ROI_GB=.0024; REENTRY=180
FLOW60_MAX=.20
OUT=ROOT/'research/results/LONG2_CANDIDATE_SCREEN_V1_20261022'; OUT.mkdir(parents=True,exist_ok=True)

def threshold(sym):
    return float(os.getenv(f'COIN_LONG_THRESHOLD_{sym}',os.getenv('LONG_THRESHOLD','0.525')) or .525)

def load_symbol(sym):
    d=pd.read_csv(ROOT/f'data/offline_cache/{sym}_1m_360d.csv')
    ts=pd.to_datetime(d.open_time,unit='ms',utc=True)
    d=d[(ts>=COMMON_START-pd.Timedelta(days=3))&(ts<COMMON_END)].copy().reset_index(drop=True)
    for c in ('open','high','low','close','volume','quote_asset_volume','taker_buy_quote_volume'):
        d[c]=pd.to_numeric(d[c],errors='coerce')
    q=d.quote_asset_volume; b=d.taker_buy_quote_volume; net=2*b-q
    d['flow60_prev']=(net.rolling(60,min_periods=60).sum()/q.rolling(60,min_periods=60).sum()).shift(1)
    D=d.copy(); D['bucket']=pd.to_datetime(D.open_time,unit='ms',utc=True).dt.floor('3min')
    amap={'open':('open','first'),'high':('high','max'),'low':('low','min'),'close':('close','last'),'volume':('volume','sum'),'open_time':('open_time','first'),'close_time':('close_time','last'),'n':('open_time','size')}
    for c in ('quote_asset_volume','number_of_trades','taker_buy_base_volume','taker_buy_quote_volume'):
        if c in D.columns: amap[c]=(c,'sum')
    if 'ignore' in D.columns: amap['ignore']=('ignore','last')
    a=D.groupby('bucket',sort=True).agg(**amap).reset_index(drop=True)
    a=a[a.n==3].drop(columns='n').reset_index(drop=True)
    meta=json.loads((ROOT/f'models/model_meta_{sym}_3m.json').read_text())
    model=joblib.load(ROOT/f'models/online_model_{sym}_3m_best.joblib')
    feat=build_features(a,interval='3m').reindex(columns=list(meta['feature_schema'])).apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan).fillna(0.0)
    proba=np.asarray(model.predict_proba(feat.to_numpy(float)),float)
    score=proba[:,-1] if proba.ndim==2 else proba.reshape(-1)
    score=score[-len(a):]
    opens=d.open_time.to_numpy(np.int64); start_ms=int(COMMON_START.timestamp()*1000); th=threshold(sym); events={}
    for r,sc in zip(a.itertuples(index=False),score):
        if int(r.close_time)<start_ms or float(sc)<th: continue
        j=int(np.searchsorted(opens,int(r.close_time)+1,'left'))
        if j<len(d) and int(d.iloc[j].open_time)>=start_ms:
            events[j]=max(float(sc),events.get(j,-np.inf))
    return d,sorted(events.items()),th

def run(d,items,seed,local_dd=False):
    bal=1000.; peak=1000.; reduced=False; trades=[]; ep=0; i=0; pos=None; last_exit=-10**30; n=len(d)
    def prog(ei): return random.Random(seed*1000003+int(d.iloc[ei].open_time)*17//60000+19).uniform(.08,.52)
    while i<n:
        while ep<len(items) and items[ep][0]<i: ep+=1
        if pos is None:
            if ep>=len(items): break
            ei,_sc=items[ep]; i=ei; r=d.iloc[i]; oms=int(r.open_time); ep+=1
            if oms<last_exit+REENTRY*1000: continue
            f60=float(r.flow60_prev) if pd.notna(r.flow60_prev) else np.nan
            if np.isfinite(f60) and f60>=FLOW60_MAX: continue
            pct=.5 if (local_dd and reduced) else 1.0
            q=prog(ei); px=sim.interp(sim.nodes(r),q); notion=bal*pct; qty=notion/px; t0=oms+int(q*60000)
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
                    gross=(px-pos['avg'])*pos['qty']; fees=pos['fees']+pos['qty']*px*FEE; net=gross-fees; bal+=net; peak=max(peak,bal); dd=bal/peak-1
                    if local_dd:
                        if (not reduced) and dd<=-.08: reduced=True
                        elif reduced and dd>=-.04: reduced=False
                    trades.append((pos['entry'],now,pos['notional'],net,fees,reason,bal,dd)); last_exit=now; pos=None; i=k; closed=True; break
            if closed: break
        if not closed: break
    t=pd.DataFrame(trades,columns=['entry','exit','notional','net','fees','reason','bal','dd'])
    eq=np.r_[1000.,t.bal.to_numpy(float)] if len(t) else np.array([1000.]); pk=np.maximum.accumulate(eq); dds=eq/pk-1
    gp=t.loc[t.net>0,'net'].sum(); gl=-t.loc[t.net<0,'net'].sum()
    return {'return_pct':(bal/1000-1)*100,'trades':len(t),'win_pct':100*(t.net>0).mean() if len(t) else 0.,'pf':gp/max(gl,1e-12),'dd_pct':100*dds.min(),'fees':t.fees.sum()}

def main():
    rows=[]
    for sym in SYMS:
        d,items,th=load_symbol(sym); print('EVENTS',sym,'threshold',th,'events',len(items),flush=True)
        for mode,local in [('STATIC',False),('LOCAL8_4',True)]:
            chunk=[]
            for seed in range(1,7):
                s=run(d,items,seed,local_dd=local); row={'symbol':sym,'mode':mode,'seed':seed,'threshold':th,'events':len(items),**s}; rows.append(row); chunk.append(row)
            z=pd.DataFrame(chunk)
            print('SUMMARY',sym,mode,{'ret_mean':z.return_pct.mean(),'ret_min':z.return_pct.min(),'pf_mean':z.pf.mean(),'dd_mean':z.dd_pct.mean(),'dd_worst':z.dd_pct.min(),'trades_mean':z.trades.mean(),'win_mean':z.win_pct.mean()},flush=True)
    R=pd.DataFrame(rows); R.to_csv(OUT/'by_seed.csv',index=False)
    A=R.groupby(['symbol','mode']).agg(threshold=('threshold','first'),events=('events','first'),return_mean=('return_pct','mean'),return_min=('return_pct','min'),return_max=('return_pct','max'),return_std=('return_pct','std'),pf_mean=('pf','mean'),dd_mean=('dd_pct','mean'),dd_worst=('dd_pct','min'),trades_mean=('trades','mean'),win_mean=('win_pct','mean'),fees_mean=('fees','mean')).reset_index()
    A.to_csv(OUT/'summary.csv',index=False); print('\nFINAL\n'+A.to_string(index=False),flush=True)
if __name__=='__main__': main()
