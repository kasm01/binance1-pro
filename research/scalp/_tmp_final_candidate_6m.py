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
BASE=1.0; ADD=.50; MAXL=3; REENTRY=180; FEE=float(os.getenv('OUTCOME_TAKER_FEE_RATE','.0004')); SL=.0299; CAT=.035; CONFIRM=30.; STALL_MIN=.001; STALL=2400.; LEV=3.; TP_PRICE=.02; ROI_TP=.04; ROI_GB=.0024

def prog(seed,ei):
    return random.Random(seed*1000003+int(df.iloc[ei].open_time)*17//60000+19).uniform(.08,.52)

def day_key(ms):
    return pd.Timestamp(int(ms),unit='ms',tz='UTC').strftime('%Y-%m-%d')

def run(seed, trigger=None, recover=None, reduced_base=.5, reduced_add=.1, daily_loss=None):
    bal=1000.; peak=1000.; reduced=False; trades=[]; entries=[]; ep=0; i=0; pos=None; last_exit=-10**30; n=len(df)
    cur_day=None; day_start=bal; day_real=0.
    def rollover(now):
        nonlocal cur_day,day_start,day_real
        dk=day_key(now)
        if dk!=cur_day: cur_day=dk; day_start=bal; day_real=0.
    def day_block():
        return daily_loss is not None and day_start>0 and day_real/day_start <= -abs(daily_loss)
    def sizes():
        return (reduced_base,reduced_add) if reduced else (1.0,.50)
    while i<n:
        while ep<len(items) and items[ep][0]<i: ep+=1
        if pos is None:
            if ep>=len(items): break
            ei,sc=items[ep]; i=ei; r=df.iloc[i]; oms=int(r.open_time); rollover(oms)
            if oms<last_exit+REENTRY*1000 or day_block(): ep+=1; continue
            bsz,asz=sizes(); q=prog(seed,ei); px=sim.interp(sim.nodes(r),q); notion=bal*bsz; qty=notion/px; t0=oms+int(q*60000); rollover(t0)
            if day_block(): ep+=1; continue
            pos={'qty':qty,'avg':px,'notional':notion,'layers':1,'bestp':0.,'bestr':0.,'lastbest':t0,'armed':False,'lastadd':t0,'fees':notion*FEE,'pending':None,'entry':t0,'before':bal,'add_pct':asz}; entries.append((t0,1,reduced)); ep+=1
        closed=False
        for k in range(i,n):
            r=df.iloc[k]; oms=int(r.open_time); rollover(oms); bes=[]
            while ep<len(items) and items[ep][0]==k: bes.append(items[ep]); ep+=1
            adds=[(prog(seed,ei),sc,ei) for ei,sc in bes if pos['layers']<MAXL]
            pts=[('p',q,px,None) for q,px in sim.samples(r,0.0)]+[('a',q,None,sc) for q,sc,_ in adds]; pts.sort(key=lambda x:(x[1],0 if x[0]=='p' else 1))
            for typ,q,px,sc in pts:
                now=oms+int(q*60000); rollover(now)
                if typ=='a':
                    if pos['layers']>=MAXL or now-pos['lastadd']<REENTRY*1000 or day_block(): continue
                    ap=sim.interp(sim.nodes(r),q); notion=bal*pos['add_pct']; aq=notion/ap
                    pos['avg']=(pos['avg']*pos['qty']+ap*aq)/(pos['qty']+aq); pos['qty']+=aq; pos['notional']+=notion; pos['fees']+=notion*FEE; pos['layers']+=1; pos['lastadd']=now; pos['bestp']=0.; pos['bestr']=0.; pos['lastbest']=now; pos['armed']=False; pos['pending']=None; entries.append((now,pos['layers'],reduced)); continue
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
                    gross=(px-pos['avg'])*pos['qty']; fees=pos['fees']+pos['qty']*px*FEE; net=gross-fees; before=bal; bal+=net; day_real+=net
                    peak=max(peak,bal); dd=bal/peak-1
                    if trigger is not None:
                        if (not reduced) and dd <= -abs(trigger): reduced=True
                        elif reduced and dd >= -abs(recover): reduced=False
                    trades.append((pos['entry'],now,pos['layers'],net,fees,reason,before,bal,dd,reduced)); last_exit=now; pos=None; i=k; closed=True; break
            if closed: break
        if not closed: break
    t=pd.DataFrame(trades,columns=['entry','exit','layers','net','fees','reason','before','bal','dd','reduced_after'])
    eq=np.r_[1000.,t.bal.to_numpy(float)] if len(t) else np.array([1000.]); pk=np.maximum.accumulate(eq); dds=(eq/pk-1)*100
    gp=t.loc[t.net>0,'net'].sum(); gl=-t.loc[t.net<0,'net'].sum()
    return {'ret':(bal/1000-1)*100,'n':len(t),'entries':len(entries),'win':100*(t.net>0).mean() if len(t) else 0,'pf':gp/max(gl,1e-9),'dd':dds.min(),'fees':t.fees.sum(),'net':t.net.sum(),'reduced_closes':int(t.reduced_after.sum()) if len(t) else 0}

configs=[('final_candidate',.08,.04,.5,.1,None)]
rows=[]
for name,tr,rc,rb,ra,dl in configs:
    ss=[run(seed,tr,rc,rb,ra,dl) for seed in range(1,7)]; d=pd.DataFrame(ss)
    rec={'name':name,'ret_mean':d.ret.mean(),'ret_min':d.ret.min(),'ret_max':d.ret.max(),'entries':d.entries.mean(),'win':d.win.mean(),'pf':d.pf.mean(),'dd_mean':d.dd.mean(),'dd_worst':d.dd.min(),'fees':d.fees.mean(),'n':d.n.mean()}
    rows.append(rec); print('FINAL',rec,flush=True); print(d.to_string(index=False),flush=True)
R=pd.DataFrame(rows); R.to_csv(ROOT/'research/results/LONG1_FINAL_CANDIDATE_6M.csv',index=False)
