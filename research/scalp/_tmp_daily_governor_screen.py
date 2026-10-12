from pathlib import Path
import pandas as pd, numpy as np, random, os, sys
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from config.load_env import load_environment_variables
load_environment_variables()
import research.scalp.simulate_long1_near_mtf as sim
START=pd.Timestamp('2025-10-11 21:36:00',tz='UTC'); END=pd.Timestamp('2026-10-11 21:36:00',tz='UTC')
parts=[]
for fp in [ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv',ROOT/'research/data/NEARUSDT_1m_1month.csv']:
    parts.append(pd.read_csv(fp))
df=pd.concat(parts,ignore_index=True).drop_duplicates('open_time').sort_values('open_time').reset_index(drop=True)
ts=pd.to_datetime(df.open_time,unit='ms',utc=True); pre=START-pd.Timedelta(days=3)
df=df[(ts>=pre)&(ts<END)].copy().reset_index(drop=True)
for c in ('open','high','low','close'): df[c]=pd.to_numeric(df[c],errors='coerce')
ev=pd.read_csv(ROOT/'research/results/LONG1_NEAR_PROD_1Y_EVENTS.csv')
items=[(int(r.row_i),float(r.score)) for r in ev.itertuples(index=False)]
BASE=1.0; ADD=.50; MAXL=3; REENTRY=180; FEE=float(os.getenv('OUTCOME_TAKER_FEE_RATE','.0004')); SL=.0299; CAT=.045; CONFIRM=60.; STALL_MIN=.001; STALL=2400.; LEV=3.; TP_PRICE=.02; ROI_TP=.04; ROI_GB=.0024

def prog(seed,ei):
    return random.Random(seed*1000003+int(df.iloc[ei].open_time)*17//60000+19).uniform(.08,.52)

def day_key(ms):
    return pd.Timestamp(int(ms),unit='ms',tz='UTC').strftime('%Y-%m-%d')

def run(seed, daily_loss_limit=None, max_daily_entries=None):
    bal=1000.; trades=[]; entries=[]; ep=0; i=0; pos=None; last_exit=-10**30; n=len(df)
    cur_day=None; day_start_bal=bal; day_realized=0.; day_entries=0
    def rollover(now):
        nonlocal cur_day,day_start_bal,day_realized,day_entries
        dk=day_key(now)
        if dk!=cur_day:
            cur_day=dk; day_start_bal=bal; day_realized=0.; day_entries=0
    def blocked():
        if daily_loss_limit is not None and day_start_bal>0 and day_realized/day_start_bal <= -abs(daily_loss_limit): return True
        if max_daily_entries is not None and day_entries>=max_daily_entries: return True
        return False
    while i<n:
        while ep<len(items) and items[ep][0]<i: ep+=1
        if pos is None:
            if ep>=len(items): break
            ei,sc=items[ep]; i=ei; r=df.iloc[i]; oms=int(r.open_time); rollover(oms)
            if oms<last_exit+REENTRY*1000 or blocked(): ep+=1; continue
            q=prog(seed,ei); px=sim.interp(sim.nodes(r),q); notion=bal*BASE; qty=notion/px; t0=oms+int(q*60000); rollover(t0)
            if blocked(): ep+=1; continue
            pos={'qty':qty,'avg':px,'notional':notion,'layers':1,'bestp':0.,'bestr':0.,'lastbest':t0,'armed':False,'lastadd':t0,'fees':notion*FEE,'pending':None,'entry':t0,'before':bal}; entries.append((t0,1)); day_entries+=1; ep+=1
        closed=False
        for k in range(i,n):
            r=df.iloc[k]; oms=int(r.open_time); rollover(oms); bes=[]
            while ep<len(items) and items[ep][0]==k: bes.append(items[ep]); ep+=1
            adds=[(prog(seed,ei),sc,ei) for ei,sc in bes if pos['layers']<MAXL]
            pts=[('p',q,px,None) for q,px in sim.samples(r,0.0)]+[('a',q,None,sc) for q,sc,_ in adds]; pts.sort(key=lambda x:(x[1],0 if x[0]=='p' else 1))
            for typ,q,px,sc in pts:
                now=oms+int(q*60000); rollover(now)
                if typ=='a':
                    if pos['layers']>=MAXL or now-pos['lastadd']<REENTRY*1000 or blocked(): continue
                    ap=sim.interp(sim.nodes(r),q); notion=bal*ADD; aq=notion/ap
                    pos['avg']=(pos['avg']*pos['qty']+ap*aq)/(pos['qty']+aq); pos['qty']+=aq; pos['notional']+=notion; pos['fees']+=notion*FEE; pos['layers']+=1; pos['lastadd']=now; pos['bestp']=0.; pos['bestr']=0.; pos['lastbest']=now; pos['armed']=False; pos['pending']=None; entries.append((now,pos['layers'])); day_entries+=1; continue
                pnl=(px-pos['avg'])/pos['avg']; roi=pnl*LEV
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
                    gross=(px-pos['avg'])*pos['qty']; fees=pos['fees']+pos['qty']*px*FEE; net=gross-fees; before=bal; bal+=net; day_realized+=net
                    trades.append((pos['entry'],now,pos['layers'],net,fees,reason,before,bal,cur_day,day_realized,day_start_bal)); last_exit=now; pos=None; i=k; closed=True; break
            if closed: break
        if not closed: break
    t=pd.DataFrame(trades,columns=['entry','exit','layers','net','fees','reason','before','bal','day','day_realized','day_start_bal'])
    eq=np.r_[1000.,t.bal.to_numpy(float)] if len(t) else np.array([1000.]); peak=np.maximum.accumulate(eq); dd=(eq/peak-1)*100
    gp=t.loc[t.net>0,'net'].sum(); gl=-t.loc[t.net<0,'net'].sum()
    return {'ret':(bal/1000-1)*100,'n':len(t),'entries':len(entries),'win':100*(t.net>0).mean() if len(t) else 0,'pf':gp/max(gl,1e-9),'dd':dd.min(),'fees':t.fees.sum(),'net':t.net.sum(),'worst_day': (t.groupby('day').net.sum()/t.groupby('day').before.first()*100).min() if len(t) else 0}

configs=[('none',None,None),('loss2',.02,None),('loss3',.03,None),('loss4',.04,None),('loss5',.05,None),('loss6',.06,None),('loss2_cap6',.02,6),('loss3_cap6',.03,6),('loss4_cap6',.04,6),('cap6',None,6)]
rows=[]
for name,lim,cap in configs:
    x=run(1,lim,cap); rec={'name':name,'limit':lim,'cap':cap,**x}; rows.append(rec); print('SCREEN',rec,flush=True)
R=pd.DataFrame(rows).sort_values(['dd','ret'],ascending=[False,False]); R.to_csv(ROOT/'research/results/LONG1_DAILY_GOV_SCREEN.csv',index=False); print('\nSCREEN_RESULTS\n'+R.to_string(index=False),flush=True)
