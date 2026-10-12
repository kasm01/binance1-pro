from pathlib import Path
import pandas as pd, numpy as np, random, os, sys
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from config.load_env import load_environment_variables
load_environment_variables()
import research.scalp.simulate_long1_near_mtf as sim
START=pd.Timestamp('2026-03-18 19:24:00',tz='UTC'); END=pd.Timestamp('2026-09-14 19:24:00',tz='UTC')
parts=[]
for fp in [ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv',ROOT/'research/data/NEARUSDT_1m_1month.csv']:
    parts.append(pd.read_csv(fp))
df=pd.concat(parts,ignore_index=True).drop_duplicates('open_time').sort_values('open_time').reset_index(drop=True)
ts=pd.to_datetime(df.open_time,unit='ms',utc=True); pre=START-pd.Timedelta(days=3)
df=df[(ts>=pre)&(ts<END)].copy().reset_index(drop=True)
for c in ('open','high','low','close'): df[c]=pd.to_numeric(df[c],errors='coerce')
ev=pd.read_csv(ROOT/'research/results/LONG1_NEAR_PROD_6M_EVENTS.csv')
items=[(int(r.row_i),float(r.score)) for r in ev.itertuples(index=False)]
BASE=.50; ADD=.10; MAXL=3; REENTRY=180; FEE=float(os.getenv('OUTCOME_TAKER_FEE_RATE','.0004')); SL=.0299; CAT=.045; CONFIRM=60; STALL_MIN=.001; STALL=2400.; LEV=3.; TP_PRICE=.02

def prog(seed,ei):
    return random.Random(seed*1000003+int(df.iloc[ei].open_time)*17//60000+19).uniform(.08,.52)

def run(seed, roi_tp, roi_gb, base_pct, add_pct):
    bal=1000.; trades=[]; ep=0; i=0; pos=None; last_exit=-10**30; n=len(df)
    while i<n:
        while ep<len(items) and items[ep][0]<i: ep+=1
        if pos is None:
            if ep>=len(items): break
            ei,sc=items[ep]; i=ei; r=df.iloc[i]; oms=int(r.open_time)
            if oms<last_exit+REENTRY*1000: ep+=1; continue
            q=prog(seed,ei); px=sim.interp(sim.nodes(r),q); notion=bal*base_pct; qty=notion/px; t0=oms+int(q*60000)
            pos={'qty':qty,'avg':px,'notional':notion,'layers':1,'bestp':0.,'bestr':0.,'lastbest':t0,'armed':False,'lastadd':t0,'fees':notion*FEE,'pending':None,'entry':t0,'before':bal}; ep+=1
        closed=False
        for k in range(i,n):
            r=df.iloc[k]; oms=int(r.open_time); bes=[]
            while ep<len(items) and items[ep][0]==k: bes.append(items[ep]); ep+=1
            adds=[(prog(seed,ei),sc,ei) for ei,sc in bes if pos['layers']<MAXL]
            pts=[('p',q,px,None) for q,px in sim.samples(r,0.0)]+[('a',q,None,sc) for q,sc,_ in adds]; pts.sort(key=lambda x:(x[1],0 if x[0]=='p' else 1))
            for typ,q,px,sc in pts:
                now=oms+int(q*60000)
                if typ=='a':
                    if pos['layers']>=MAXL or now-pos['lastadd']<REENTRY*1000: continue
                    ap=sim.interp(sim.nodes(r),q); notion=bal*add_pct; aq=notion/ap
                    pos['avg']=(pos['avg']*pos['qty']+ap*aq)/(pos['qty']+aq); pos['qty']+=aq; pos['notional']+=notion; pos['fees']+=notion*FEE; pos['layers']+=1; pos['lastadd']=now; pos['bestp']=0.; pos['bestr']=0.; pos['lastbest']=now; pos['armed']=False; pos['pending']=None; continue
                pnl=(px-pos['avg'])/pos['avg']; roi=pnl*LEV
                if pnl>pos['bestp']: pos['bestp']=pnl; pos['lastbest']=now
                if roi>pos['bestr']: pos['bestr']=roi
                if pos['bestr']>=roi_tp: pos['armed']=True
                reason=None
                if pnl<=-CAT: reason='cat'
                else:
                    if pnl<=-SL:
                        if pos['pending'] is None: pos['pending']=now
                        elif now-pos['pending']>=CONFIRM*1000: reason='sl'
                    elif pos['pending'] is not None: pos['pending']=None
                if reason is None and pos['armed'] and roi<=pos['bestr']-roi_gb: reason='gb'
                elif reason is None and px>=pos['avg']*(1+TP_PRICE): reason='tp'
                elif reason is None and pnl>=STALL_MIN and (now-pos['lastbest'])/1000>=STALL: reason='stall'
                if reason:
                    gross=(px-pos['avg'])*pos['qty']; fees=pos['fees']+pos['qty']*px*FEE; net=gross-fees; bal+=net
                    trades.append((now,pos['layers'],net,fees,reason,bal)); last_exit=now; pos=None; i=k; closed=True; break
            if closed: break
        if not closed: break
    t=pd.DataFrame(trades,columns=['exit','layers','net','fees','reason','bal'])
    eq=np.r_[1000.,t.bal.to_numpy(float)] if len(t) else np.array([1000.]); peak=np.maximum.accumulate(eq); dd=(eq/peak-1)*100
    gp=t.loc[t.net>0,'net'].sum(); gl=-t.loc[t.net<0,'net'].sum()
    return {'ret':(bal/1000-1)*100,'n':len(t),'win':100*(t.net>0).mean() if len(t) else 0,'pf':gp/max(gl,1e-9),'dd':dd.min(),'fees':t.fees.sum(),'net':t.net.sum()}

configs=[(.50,.10),(.75,.15),(1.00,.20),(1.00,.25),(1.00,.35),(1.00,.50)]
rows=[]
for base,add in configs:
  ss=[]
  for seed in range(1,7): ss.append(run(seed,.04,.0024,base,add))
  d=pd.DataFrame(ss)
  rec={'base':base,'add':add,'max_notional_x':base+2*add,'margin_frac_at_3x':(base+2*add)/3,'ret_mean':d.ret.mean(),'ret_min':d.ret.min(),'ret_max':d.ret.max(),'win':d.win.mean(),'pf':d.pf.mean(),'dd_mean':d.dd.mean(),'dd_worst':d.dd.min(),'fees':d.fees.mean(),'n':d.n.mean()}
  rows.append(rec); print('SIZE',rec,flush=True)
R=pd.DataFrame(rows).sort_values('ret_mean',ascending=False); R.to_csv(ROOT/'research/results/LONG1_SIZE_GRID_VALID.csv',index=False); print('\nSIZES\n'+R.to_string(index=False),flush=True)
