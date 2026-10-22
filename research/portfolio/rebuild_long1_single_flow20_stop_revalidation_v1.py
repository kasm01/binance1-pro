from pathlib import Path
import pandas as pd, numpy as np, random, os, sys
ROOT=Path('/home/kasm920/binance1-pro'); sys.path.insert(0,str(ROOT))
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
for c in ('quote_asset_volume','taker_buy_quote_volume'):
    df[c]=pd.to_numeric(df[c],errors='coerce')
_q=df['quote_asset_volume']; _b=df['taker_buy_quote_volume']; _net=2.0*_b-_q
# causal: only completed bars prior to candidate minute
_df15=(_net.rolling(15,min_periods=15).sum()/_q.rolling(15,min_periods=15).sum()).shift(1)
_df60=(_net.rolling(60,min_periods=60).sum()/_q.rolling(60,min_periods=60).sum()).shift(1)
df['flow15_prev']=_df15; df['flow60_prev']=_df60
ev=pd.read_csv(ROOT/'research/results/LONG1_NEAR_PROD_1Y_EVENTS.csv')
items=[(int(r.row_i),float(r.score)) for r in ev.itertuples(index=False)]
BASE=1.0; ADD=.50; MAXL=3; REENTRY=180; FEE=float(os.getenv('OUTCOME_TAKER_FEE_RATE','.0004')); SL=.0299; CAT=.035; CONFIRM=30.; STALL_MIN=.001; STALL=2400.; LEV=3.; TP_PRICE=.02; ROI_TP=.04; ROI_GB=.0024

def prog(seed,ei):
    return random.Random(seed*1000003+int(df.iloc[ei].open_time)*17//60000+19).uniform(.08,.52)

def day_key(ms):
    return pd.Timestamp(int(ms),unit='ms',tz='UTC').strftime('%Y-%m-%d')

def run(seed, trigger=None, recover=None, reduced_base=.5, reduced_add=.1, daily_loss=None, max_layers=3, flow60_max=None, soft_flow15=False):
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
            f60=float(r.get('flow60_prev')) if pd.notna(r.get('flow60_prev')) else float('nan')
            f15=float(r.get('flow15_prev')) if pd.notna(r.get('flow15_prev')) else float('nan')
            if flow60_max is not None and np.isfinite(f60) and f60>=float(flow60_max): ep+=1; continue
            if soft_flow15 and sc<0.525 and (not np.isfinite(f15) or f15<=0.0): ep+=1; continue
            bsz,asz=sizes(); q=prog(seed,ei); px=sim.interp(sim.nodes(r),q); notion=bal*bsz; qty=notion/px; t0=oms+int(q*60000); rollover(t0)
            if day_block(): ep+=1; continue
            pos={'qty':qty,'avg':px,'notional':notion,'orig_notional':notion,'orig_qty':qty,'layers':1,'bestp':0.,'bestr':0.,'lastbest':t0,'armed':False,'lastadd':t0,'fees':notion*FEE,'pending':None,'entry':t0,'entry_row':i,'entry_progress':q,'before':bal,'add_pct':asz,'rescue':False,'rescue_deadline':0,'rescue_net':0.0,'rescue_fees':0.0}; entries.append((t0,1,reduced)); ep+=1
        closed=False
        for k in range(i,n):
            r=df.iloc[k]; oms=int(r.open_time); rollover(oms); bes=[]
            while ep<len(items) and items[ep][0]==k: bes.append(items[ep]); ep+=1
            adds=[(prog(seed,ei),sc,ei) for ei,sc in bes if pos['layers']<max_layers]
            min_q=float(pos.get('entry_progress',0.0)) if k==int(pos.get('entry_row',-1)) else 0.0
            pts=[('p',q,px,None) for q,px in sim.samples(r,0.0) if q>=min_q]+[('a',q,None,sc) for q,sc,_ in adds if q>=min_q]; pts.sort(key=lambda x:(x[1],0 if x[0]=='p' else 1))
            for typ,q,px,sc in pts:
                now=oms+int(q*60000); rollover(now)
                if typ=='a':
                    if pos['layers']>=max_layers or now-pos['lastadd']<REENTRY*1000 or day_block(): continue
                    f60=float(r.get('flow60_prev')) if pd.notna(r.get('flow60_prev')) else float('nan')
                    f15=float(r.get('flow15_prev')) if pd.notna(r.get('flow15_prev')) else float('nan')
                    if flow60_max is not None and np.isfinite(f60) and f60>=float(flow60_max): continue
                    if soft_flow15 and sc<0.525 and (not np.isfinite(f15) or f15<=0.0): continue
                    ap=sim.interp(sim.nodes(r),q); notion=bal*pos['add_pct']; aq=notion/ap
                    pos['avg']=(pos['avg']*pos['qty']+ap*aq)/(pos['qty']+aq); pos['qty']+=aq; pos['notional']+=notion; pos['fees']+=notion*FEE; pos['layers']+=1; pos['lastadd']=now; pos['bestp']=0.; pos['bestr']=0.; pos['lastbest']=now; pos['armed']=False; pos['pending']=None; entries.append((now,pos['layers'],reduced)); continue
                pnl=(px-pos['avg'])/pos['avg']; roi=pnl*LEV
                if pos.get('rescue'):
                    reason=None
                    if pnl<=-CAT: reason='sl_rescue_cat'
                    elif px>=pos['avg']: reason='sl_rescue_recover'
                    elif now>=pos.get('rescue_deadline',0): reason='sl_rescue_timeout'
                    if reason:
                        gross=(px-pos['avg'])*pos['qty']; close_fee=pos['qty']*px*FEE; net_rem=gross-close_fee-pos['fees']; bal+=net_rem; day_real+=net_rem
                        net=pos.get('rescue_net',0.0)+net_rem; fees=pos.get('rescue_fees',0.0)+pos['fees']+close_fee; before=pos['before']
                        peak=max(peak,bal); dd=bal/peak-1
                        if trigger is not None:
                            if (not reduced) and dd <= -abs(trigger): reduced=True
                            elif reduced and dd >= -abs(recover): reduced=False
                        trades.append((pos['entry'],now,pos['layers'],pos.get('orig_notional',pos['notional']),pos['avg'],px,pos.get('orig_qty',pos['qty']),net,fees,reason,before,bal,dd,reduced)); last_exit=now; pos=None; i=k; closed=True; break
                    continue
                if pnl>pos['bestp']: pos['bestp']=pnl; pos['lastbest']=now
                if roi>pos['bestr']: pos['bestr']=roi
                if pos['bestr']>=ROI_TP: pos['armed']=True
                reason=None
                if pnl<=-CAT: reason='cat'
                else:
                    if pnl<=-SL:
                        if pos['pending'] is None: pos['pending']=now
                        elif now-pos['pending']>=CONFIRM*1000:
                            # STOP REVALIDATION V1: realize 50% now; hold residual <=120m,
                            # but never beyond the existing -3.5% catastrophic boundary.
                            frac=.50; part_qty=pos['qty']*frac; part_open_fee=pos['fees']*frac; part_close_fee=part_qty*px*FEE
                            part_net=(px-pos['avg'])*part_qty-part_open_fee-part_close_fee
                            bal+=part_net; day_real+=part_net
                            pos['rescue_net']=part_net; pos['rescue_fees']=part_open_fee+part_close_fee
                            pos['qty']-=part_qty; pos['notional']*=1-frac; pos['fees']-=part_open_fee
                            pos['rescue']=True; pos['rescue_deadline']=now+120*60*1000; pos['pending']=None
                            continue
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
                    trades.append((pos['entry'],now,pos['layers'],pos['notional'],pos['avg'],px,pos['qty'],net,fees,reason,before,bal,dd,reduced)); last_exit=now; pos=None; i=k; closed=True; break
            if closed: break
        if not closed: break
    t=pd.DataFrame(trades,columns=['entry','exit','layers','notional','entry_price','exit_price','qty','net','fees','reason','before','bal','dd','reduced_after'])
    eq=np.r_[1000.,t.bal.to_numpy(float)] if len(t) else np.array([1000.]); pk=np.maximum.accumulate(eq); dds=(eq/pk-1)*100
    gp=t.loc[t.net>0,'net'].sum(); gl=-t.loc[t.net<0,'net'].sum()
    summary={'ret':(bal/1000-1)*100,'n':len(t),'entries':len(entries),'win':100*(t.net>0).mean() if len(t) else 0,'pf':gp/max(gl,1e-9),'dd':dds.min(),'fees':t.fees.sum(),'net':t.net.sum(),'reduced_closes':int(t.reduced_after.sum()) if len(t) else 0}
    return summary,t

OUT=ROOT/'research/results/LONG1_SINGLE_F60_020_STOP_REVALIDATION_V1_20261022'
OUT.mkdir(parents=True,exist_ok=True)
rows=[]
for seed in range(1,7):
    summary,trades=run(seed,.08,.04,.5,.1,None,max_layers=1,flow60_max=.20,soft_flow15=False)
    trades=trades.copy(); trades['seed']=seed
    trades['entry_ts']=pd.to_datetime(trades.entry,unit='ms',utc=True); trades['exit_ts']=pd.to_datetime(trades.exit,unit='ms',utc=True)
    trades.to_csv(OUT/f'seed{seed}.csv',index=False)
    rows.append({'seed':seed,**summary})
    print('SEED',seed,summary,flush=True)
R=pd.DataFrame(rows); R.to_csv(OUT/'summary.csv',index=False); print(R.to_string(index=False),flush=True)
for seed in range(1,7):
    z=pd.read_csv(OUT/f'seed{seed}.csv')
    assert (pd.to_numeric(z.exit)>pd.to_numeric(z.entry)).all(), f'noncausal_exit_seed{seed}'
print('CAUSAL_EXIT_INVARIANT_OK',flush=True)
