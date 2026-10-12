from pathlib import Path
import pandas as pd, numpy as np, random, os, sys, logging, argparse
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from config.load_env import load_environment_variables
load_environment_variables()
from backtest_mtf import _resolve_build_features
from models.hybrid_inference import HybridModel
import research.scalp.simulate_long1_near_mtf as sim

BASE_THR=float(os.getenv('LONG_THRESHOLD','0.525') or .525)
FLOOR=float(os.getenv('LONG_DYNAMIC_MODEL_GATE_FLOOR','0.5114') or .5114)
LOOKBACK=max(80,int(os.getenv('LONG_DYNAMIC_MODEL_GATE_LOOKBACK','240') or 240))
MIN_HIST=max(30,int(os.getenv('LONG_DYNAMIC_MODEL_GATE_MIN_HISTORY','80') or 80))
MIN_ATR=float(os.getenv('LONG_DYNAMIC_MODEL_GATE_MIN_ATR_RANK','0.60') or .60)
MIN_CLOSE=float(os.getenv('LONG_DYNAMIC_MODEL_GATE_MIN_CLOSE_LOC','0.25') or .25)
MIN_WICK=float(os.getenv('LONG_DYNAMIC_MODEL_GATE_MIN_LOWER_WICK_FRAC','0.25') or .25)
MAX_LAYERS=int(os.getenv('LONG_MAX_ENTRY_LAYERS','3') or 3)
BASE_PCT=float(os.getenv('PER_POSITION_BALANCE_PCT','0.50') or .50)
ADD_PCT=float(os.getenv('LONG_SCALE_IN_ADD_BALANCE_PCT','0.10') or .10)
ADD_FLOOR=float(os.getenv('LONG_SCALE_IN_SCORE_FLOOR','0.5114') or .5114)
REENTRY=float(os.getenv('SAME_SYMBOL_OPEN_COOLDOWN_SEC','180') or 180)
SL=float(os.getenv('SL_PCT','0.0299') or .0299)
CAT=float(os.getenv('LONG_DYNAMIC_STOP_CATASTROPHIC_PCT','0.045') or .045)
CONFIRM=float(os.getenv('LONG_DYNAMIC_STOP_CONFIRM_SEC','60') or 60)
STALL_MIN=float(os.getenv('STALL_MIN_PROFIT_PCT','0.0010') or .0010)
FEE=float(os.getenv('OUTCOME_TAKER_FEE_RATE','.0004') or .0004)
sim.SL=SL; sim.ROI_STOP=float(os.getenv('ROI_HARD_STOP_PCT','-0.135') or -.135)

ap=argparse.ArgumentParser(); ap.add_argument('--days',type=int,required=True); ap.add_argument('--end',default='2026-10-11 21:36:00+00:00'); ap.add_argument('--tag',required=True)
args=ap.parse_args(); END=pd.Timestamp(args.end); END=END.tz_convert('UTC') if END.tzinfo else END.tz_localize('UTC'); START=END-pd.Timedelta(days=args.days)

# union historical + forward, de-duplicate on open_time
parts=[]
for fp in [ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv',ROOT/'research/data/NEARUSDT_1m_1month.csv']:
    d=pd.read_csv(fp); parts.append(d)
df=pd.concat(parts,ignore_index=True).drop_duplicates('open_time').sort_values('open_time').reset_index(drop=True)
for c in ('open','high','low','close','volume'): df[c]=pd.to_numeric(df[c],errors='coerce')
ts=pd.to_datetime(df.open_time,unit='ms',utc=True)
# retain prehistory for gate/features then horizon later
pre_start=START-pd.Timedelta(days=3)
df=df[(ts>=pre_start)&(ts<END)].copy().reset_index(drop=True)

# completed 3m candles
D=df.copy(); D['bucket']=pd.to_datetime(D.open_time,unit='ms',utc=True).dt.floor('3min')
amap={'open':('open','first'),'high':('high','max'),'low':('low','min'),'close':('close','last'),'volume':('volume','sum'),'open_time':('open_time','first'),'close_time':('close_time','last'),'n':('open_time','size')}
for c in ('quote_asset_volume','number_of_trades','taker_buy_base_volume','taker_buy_quote_volume'):
    if c in D.columns: amap[c]=(c,'sum')
if 'ignore' in D.columns: amap['ignore']=('ignore','last')
a=D.groupby('bucket',sort=True).agg(**amap).reset_index(drop=True); a=a[a.n==3].drop(columns='n').reset_index(drop=True)

# exact dynamic gate inputs, causal
prev=a.close.shift(1)
tr=pd.concat([(a.high-a.low).abs(),(a.high-prev).abs(),(a.low-prev).abs()],axis=1).max(axis=1)
atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean(); atr_pct=atr/a.close.replace(0,np.nan)
rng=(a.high-a.low).replace(0,np.nan)
close_loc=((a.close-a.low)/rng).clip(0,1)
lower=(np.minimum(a.open,a.close)-a.low).clip(lower=0)
wick=(lower/rng).clip(0,1)
atr_rank=np.full(len(a),np.nan)
for i in range(len(a)):
    hist=atr_pct.iloc[max(0,i-LOOKBACK):i].dropna()
    if len(hist)>=MIN_HIST and pd.notna(atr_pct.iloc[i]): atr_rank[i]=float((hist<=atr_pct.iloc[i]).mean())

feat=_resolve_build_features(logging.getLogger('prod_replay'))(a,interval='3m')
m=HybridModel(model_dir=os.getenv('MODELS_DIR',None),interval='3m',symbol='NEARUSDT',logger=logging.getLogger('prod_replay'))
p,_=m.predict_proba(feat); p=np.asarray(p,float)
if len(p)!=len(a):
    off=len(a)-len(p); a=a.iloc[off:].reset_index(drop=True); atr_rank=atr_rank[off:]; close_loc=close_loc.iloc[off:].reset_index(drop=True); wick=wick.iloc[off:].reset_index(drop=True)
n=min(len(a),len(p)); a=a.iloc[-n:].reset_index(drop=True); p=p[-n:]; atr_rank=np.asarray(atr_rank[-n:]); close_loc=np.asarray(close_loc.iloc[-n:]); wick=np.asarray(wick.iloc[-n:])

opens=df.open_time.to_numpy(np.int64); events={}; reasons={}
start_ms=int(START.timestamp()*1000)
for idx,(r,s) in enumerate(zip(a.itertuples(index=False),p)):
    if int(r.close_time)<start_ms: continue
    strong=(np.isfinite(atr_rank[idx]) and atr_rank[idx]>=MIN_ATR and (close_loc[idx]>=MIN_CLOSE or wick[idx]>=MIN_WICK))
    thr=min(BASE_THR,FLOOR) if strong else BASE_THR
    if float(s)<thr: continue
    j=int(np.searchsorted(opens,int(r.close_time)+1,'left'))
    if j<len(df) and int(df.iloc[j].open_time)>=start_ms:
        if float(s)>events.get(j,-np.inf):
            events[j]=float(s); reasons[j]='strong_recovery' if strong else 'base'
items=sorted(events.items())
# cache production-gated raw events for fast exit-grid replay
evrows=[{'row_i':int(i),'score':float(sc),'gate_reason':reasons.get(i,'')} for i,sc in items]
pd.DataFrame(evrows).to_csv(ROOT/'research/results/LONG1_NEAR_PROD_6M_EVENTS.csv',index=False)
print(f'HORIZON {START} -> {END} days={args.days} rows1m={sum(pd.to_datetime(df.open_time,unit="ms",utc=True)>=START)} events={len(items)} base={sum(reasons[i]=="base" for i,_ in items)} recovery={sum(reasons[i]=="strong_recovery" for i,_ in items)}',flush=True)

print('EVENT_CACHE_WRITTEN',len(items),flush=True)
sys.exit(0)

def run(seed):
    bal=1000.; trades=[]; entries=[]; eptr=0; i=0; pos=None; last_exit=-10**30; nrows=len(df)
    def evprog(ei): return random.Random(seed*1000003+int(df.iloc[ei].open_time)*17//60000+19).uniform(sim.PROGRESS_MIN,sim.PROGRESS_MAX)
    while i<nrows:
        while eptr<len(items) and items[eptr][0]<i: eptr+=1
        if pos is None:
            if eptr>=len(items): break
            ei,score=items[eptr]; i=ei; row=df.iloc[i]; oms=int(row.open_time)
            if oms<last_exit+int(REENTRY*1000): eptr+=1; continue
            q=evprog(ei); px=sim.interp(sim.nodes(row),q); notion=bal*BASE_PCT; qty=notion/px; t0=oms+int(q*60000)
            pos={'qty':qty,'avg':px,'notional':notion,'layers':1,'best_pnl':0.,'best_roi':0.,'last_best':t0,'armed':False,'last_add':t0,'fees_open':notion*FEE,'entry_ms':t0,'pending_ts':None,'start_bal':bal}
            entries.append((seed,t0,1,score,reasons.get(ei,''),px,notion)); eptr+=1
        closed=False
        for k in range(i,nrows):
            r=df.iloc[k]; oms=int(r.open_time); be=[]
            while eptr<len(items) and items[eptr][0]==k: be.append(items[eptr]); eptr+=1
            adds=[]
            for event_i,score in be:
                if pos['layers']<MAX_LAYERS and score>=ADD_FLOOR: adds.append((evprog(event_i),score,event_i))
            pts=[('px',q,px,None,None) for q,px in sim.samples(r,0.0)]+[('add',q,None,sc,ei) for q,sc,ei in adds]
            pts.sort(key=lambda x:(x[1],0 if x[0]=='px' else 1))
            for typ,q,px,sc,ei in pts:
                now=oms+int(q*60000)
                if typ=='add':
                    if pos['layers']>=MAX_LAYERS or now-pos['last_add']<REENTRY*1000: continue
                    apx=sim.interp(sim.nodes(r),q); notion=bal*ADD_PCT; aq=notion/apx
                    pos['avg']=(pos['avg']*pos['qty']+apx*aq)/(pos['qty']+aq); pos['qty']+=aq; pos['notional']+=notion; pos['fees_open']+=notion*FEE; pos['layers']+=1; pos['last_add']=now
                    pos['best_pnl']=0.; pos['best_roi']=0.; pos['last_best']=now; pos['armed']=False; pos['pending_ts']=None
                    entries.append((seed,now,pos['layers'],sc,reasons.get(ei,''),apx,notion)); continue
                pnl=(px-pos['avg'])/pos['avg']; roi=pnl*sim.LEV
                if pnl>pos['best_pnl']: pos['best_pnl']=pnl; pos['last_best']=now
                if roi>pos['best_roi']: pos['best_roi']=roi
                if pos['best_roi']>=sim.ROI_TP: pos['armed']=True
                reason=None
                # production priority: catastrophic ROI/price safety; 60 sec dynamic confirmation
                if pnl<=-CAT or roi<=sim.ROI_STOP:
                    reason='dynamic_stop_catastrophic'
                else:
                    if pnl<=-SL:
                        if pos['pending_ts'] is None: pos['pending_ts']=now
                        elif now-pos['pending_ts']>=CONFIRM*1000: reason='dynamic_stop_confirmed'
                    elif pos['pending_ts'] is not None:
                        pos['pending_ts']=None
                    if reason is None and pos['armed'] and roi<=pos['best_roi']-sim.ROI_GB: reason='fixed_roi_giveback'
                    elif reason is None and px>=pos['avg']*(1+sim.TP): reason='tp_hit'
                    elif reason is None and pnl>=STALL_MIN and (now-pos['last_best'])/1000>=sim.STALL: reason='stall_netprofit'
                if reason:
                    before=bal; gross=(px-pos['avg'])*pos['qty']; fees=pos['fees_open']+pos['qty']*px*FEE; net=gross-fees; bal+=net
                    trades.append((seed,pos['entry_ms'],now,pos['layers'],pos['avg'],px,pos['notional'],gross,fees,net,reason,before,bal))
                    last_exit=now; pos=None; i=k; closed=True; break
            if closed: break
        if not closed: break
    T=pd.DataFrame(trades,columns=['seed','entry_ms','exit_ms','layers','avg_entry','exit_price','notional','gross','fees','net','reason','balance_before','balance_after'])
    E=pd.DataFrame(entries,columns=['seed','ts','layer','score','gate_reason','price','notional'])
    return T,E,bal

allT=[]; allE=[]; rows=[]
for seed in range(1,7):
    T,E,b=run(seed); allT.append(T); allE.append(E)
    eq=np.r_[1000.,T.balance_after.to_numpy(float)] if len(T) else np.array([1000.]); peak=np.maximum.accumulate(eq); dd=(eq/peak-1)*100
    rows.append({'seed':seed,'final':b,'ret_pct':(b/1000-1)*100,'positions':len(T),'entries':len(E),'entries_day':len(E)/args.days,'win_pct':100*(T.net>0).mean() if len(T) else 0,'gross_pre_fee':T.gross.sum(),'fees':T.fees.sum(),'net':T.net.sum(),'pf':T.loc[T.net>0,'net'].sum()/max(-T.loc[T.net<0,'net'].sum(),1e-12),'max_closed_dd_pct':dd.min()})
S=pd.DataFrame(rows); T=pd.concat(allT,ignore_index=True); E=pd.concat(allE,ignore_index=True)
print('\nSEEDS\n'+S.to_string(index=False),flush=True)
print('\nMEAN',S.mean(numeric_only=True).to_dict(),flush=True)

T['entry_dt']=pd.to_datetime(T.entry_ms,unit='ms',utc=True); E['dt']=pd.to_datetime(E.ts,unit='ms',utc=True)
# monthly per seed, continuous balances: return = net / first balance_before that month
m=[]; d=[]
for seed in range(1,7):
    ts=T[T.seed==seed].copy(); es=E[E.seed==seed].copy()
    ts['month']=ts.entry_dt.dt.strftime('%Y-%m'); es['month']=es.dt.dt.strftime('%Y-%m')
    ts['date']=ts.entry_dt.dt.strftime('%Y-%m-%d'); es['date']=es.dt.dt.strftime('%Y-%m-%d')
    for period,gg in ts.groupby('month'):
        ee=es[es.month==period]; startbal=float(gg.iloc[0].balance_before); m.append({'seed':seed,'period':period,'positions':len(gg),'entries':len(ee),'net':gg.net.sum(),'return_pct':100*gg.net.sum()/startbal,'win_pct':100*(gg.net>0).mean(),'fees':gg.fees.sum()})
    # include days with zero trades across horizon
    dates=pd.date_range(START.floor('D'),(END-pd.Timedelta(minutes=1)).floor('D'),freq='D',tz='UTC')
    for day in dates:
        ds=day.strftime('%Y-%m-%d'); gg=ts[ts.date==ds]; ee=es[es.date==ds]
        if len(gg): startbal=float(gg.iloc[0].balance_before); ret=100*gg.net.sum()/startbal; net=gg.net.sum(); win=100*(gg.net>0).mean(); fees=gg.fees.sum()
        else: ret=0.; net=0.; win=np.nan; fees=0.
        d.append({'seed':seed,'date':ds,'positions':len(gg),'entries':len(ee),'net':net,'return_pct':ret,'win_pct':win,'fees':fees})
M=pd.DataFrame(m); DD=pd.DataFrame(d)
MO=M.groupby('period').agg(positions=('positions','mean'),entries=('entries','mean'),net=('net','mean'),return_pct=('return_pct','mean'),win_pct=('win_pct','mean'),fees=('fees','mean')).reset_index()
DA=DD.groupby('date').agg(positions=('positions','mean'),entries=('entries','mean'),net=('net','mean'),return_pct=('return_pct','mean'),win_pct=('win_pct','mean'),fees=('fees','mean')).reset_index()
print('\nMONTHLY\n'+MO.to_string(index=False),flush=True)
print('\nDAILY_SUMMARY',{'days':len(DA),'avg_entries':DA.entries.mean(),'median_entries':DA.entries.median(),'p90_entries':DA.entries.quantile(.9),'max_entries':DA.entries.max(),'avg_positions':DA.positions.mean(),'profitable_days_pct':100*(DA.net>0).mean(),'losing_days_pct':100*(DA.net<0).mean(),'flat_days_pct':100*(DA.net==0).mean(),'avg_daily_return_pct':DA.return_pct.mean(),'median_daily_return_pct':DA.return_pct.median(),'best_daily_return_pct':DA.return_pct.max(),'worst_daily_return_pct':DA.return_pct.min()},flush=True)
print('\nBEST_DAYS\n'+DA.nlargest(10,'return_pct').to_string(index=False),flush=True)
print('\nWORST_DAYS\n'+DA.nsmallest(10,'return_pct').to_string(index=False),flush=True)

out=ROOT/'research/results'; out.mkdir(exist_ok=True)
S.to_csv(out/f'{args.tag}_SEEDS.csv',index=False); T.to_csv(out/f'{args.tag}_TRADES.csv',index=False); E.to_csv(out/f'{args.tag}_ENTRIES.csv',index=False); MO.to_csv(out/f'{args.tag}_MONTHLY.csv',index=False); DA.to_csv(out/f'{args.tag}_DAILY.csv',index=False)
