from pathlib import Path
import sys, os, logging, random
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.load_env import load_environment_variables
from backtest_mtf import _resolve_build_features
from models.hybrid_inference import HybridModel
import research.scalp.simulate_long1_near_mtf as sim
load_environment_variables()

DATA=ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv'
OUT=ROOT/'research/results'
SYMBOL='NEARUSDT'; START=1000.0
SEEDS=(1,2,3,4,5,6)
BASE=float(os.getenv('LONG_THRESHOLD','0.525') or .525)
FLOOR=float(os.getenv('LONG_DYNAMIC_MODEL_GATE_FLOOR','0.516') or .516)
MIN_ATR_RANK=float(os.getenv('LONG_DYNAMIC_MODEL_GATE_MIN_ATR_RANK','0.60') or .60)
MIN_CLOSE_LOC=float(os.getenv('LONG_DYNAMIC_MODEL_GATE_MIN_CLOSE_LOC','0.25') or .25)
MIN_WICK=float(os.getenv('LONG_DYNAMIC_MODEL_GATE_MIN_LOWER_WICK_FRAC','0.25') or .25)
OPEN_MIN=float(os.getenv('COIN_LONG_MIN_SCORE_NEARUSDT',os.getenv('OPEN_MIN_SCORE','.515')) or .515)
WARM=200
END=pd.Timestamp('2026-09-14 19:24:00',tz='UTC')
START6=END-pd.Timedelta(days=180)

def aggregate(df):
    d=df.copy(); d['bucket']=pd.to_datetime(d.open_time,unit='ms',utc=True).dt.floor('3min')
    amap={'open':('open','first'),'high':('high','max'),'low':('low','min'),'close':('close','last'),'volume':('volume','sum'),
          'open_time':('open_time','first'),'close_time':('close_time','last'),'n':('open_time','size')}
    for c in ('quote_asset_volume','number_of_trades','taker_buy_base_volume','taker_buy_quote_volume'):
        if c in d.columns: amap[c]=(c,'sum')
    if 'ignore' in d.columns: amap['ignore']=('ignore','last')
    a=d.groupby('bucket',sort=True).agg(**amap).reset_index(drop=True)
    return a[a.n==3].drop(columns='n').reset_index(drop=True)

def build_events(df):
    agg=aggregate(df)
    log=logging.getLogger('near6m')
    feat=_resolve_build_features(log)(agg,interval='3m')
    model=HybridModel(model_dir=os.getenv('MODELS_DIR',None),interval='3m',symbol=SYMBOL,logger=log)
    p,_=model.predict_proba(feat); p=np.asarray(p,float)
    if len(p)!=len(agg): agg=agg.iloc[max(0,len(agg)-len(p)):].reset_index(drop=True)
    n=min(len(agg),len(p)); agg=agg.iloc[-n:].reset_index(drop=True); p=p[-n:]
    # causal ATR pct
    c=pd.to_numeric(agg.close,errors='coerce'); h=pd.to_numeric(agg.high,errors='coerce'); l=pd.to_numeric(agg.low,errors='coerce'); o=pd.to_numeric(agg.open,errors='coerce')
    prev=c.shift(1); tr=pd.concat([(h-l).abs(),(h-prev).abs(),(l-prev).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean(); ap=(atr/c.replace(0,np.nan)).to_numpy(float)
    opens=df.open_time.to_numpy(np.int64); events={}; emeta={}; candidates=[]
    for k,(r,score) in enumerate(zip(agg.itertuples(index=False),p)):
        if k<WARM or not np.isfinite(score) or float(score)<OPEN_MIN: continue
        cur=ap[k]
        hist=ap[max(0,k-240):k]; hist=hist[np.isfinite(hist)]
        atr_rank=float(np.mean(hist<=cur)) if np.isfinite(cur) and len(hist)>=80 else np.nan
        rng=float(r.high)-float(r.low)
        close_loc=max(0,min(1,(float(r.close)-float(r.low))/rng)) if rng>0 else 0
        lw=max(0,min(float(r.open),float(r.close))-float(r.low)); wick=max(0,min(1,lw/rng)) if rng>0 else 0
        strong=np.isfinite(atr_rank) and atr_rank>=MIN_ATR_RANK and (close_loc>=MIN_CLOSE_LOC or wick>=MIN_WICK)
        thr=FLOOR if strong else BASE
        kind='strong_recovery' if strong else 'base'
        passed=float(score)>=max(thr,OPEN_MIN)
        candidates.append((int(r.close_time),float(score),thr,kind,atr_rank,close_loc,wick,passed))
        if not passed: continue
        j=int(np.searchsorted(opens,int(r.close_time)+1,side='left'))
        if j<len(df):
            events[j]=max(float(score),events.get(j,-np.inf)); emeta[j]={'thr':thr,'kind':kind,'atr_rank':atr_rank,'close_loc':close_loc,'wick':wick}
    return events,emeta,p,agg,model,pd.DataFrame(candidates,columns=['close_time','score','thr','kind','atr_rank','close_loc','wick','passed'])

def run(df,events,seed,start_bal=START,allowed_start=None,allowed_end=None):
    rng=random.Random(seed); bal=float(start_bal); trades=[]; last_close=-10**30
    event_items=sorted((int(i),float(sc)) for i,sc in events.items())
    nrows=len(df)
    for entry_i,score in event_items:
        if entry_i<0 or entry_i>=nrows: continue
        row=df.iloc[entry_i]; open_ms=int(row.open_time)
        if allowed_start is not None and open_ms<allowed_start: continue
        if allowed_end is not None and open_ms>=allowed_end: continue
        if open_ms < last_close + int(sim.COOLDOWN*1000): continue
        prog=rng.uniform(sim.PROGRESS_MIN,sim.PROGRESS_MAX); ep=sim.interp(sim.nodes(row),prog)
        notion=bal*sim.BAL_PCT; qty=notion/max(ep,1e-12)
        pos={'entry_i':entry_i,'entry_ms':open_ms+int(prog*60000),'entry':ep,'qty':qty,'notional':notion,'score':score,
             'best_roi':0.0,'best_pnl':0.0,'last_best':open_ms+int(prog*60000),'armed':False,'progress':prog,
             'ever_neg':False,'neg_start':None,'first_green':None}
        closed=False
        for i in range(entry_i,nrows):
            r=df.iloc[i]; oms=int(r.open_time); start_q=prog if i==entry_i else 0
            for q,px in sim.samples(r,start_q):
                now=oms+int(q*60000); pnl=(px-ep)/ep; roi=pnl*sim.LEV
                if pnl<0 and not pos['ever_neg']: pos['ever_neg']=True; pos['neg_start']=now
                if pos['ever_neg'] and pos['first_green'] is None and pnl>0: pos['first_green']=now
                if pnl>pos['best_pnl']: pos['best_pnl']=pnl; pos['last_best']=now
                if roi>pos['best_roi']: pos['best_roi']=roi
                if pos['best_roi']>=sim.ROI_TP: pos['armed']=True
                reason=None
                if roi<=sim.ROI_STOP: reason='roi_hard_stop_lifecycle'
                elif pos['armed'] and roi<=pos['best_roi']-sim.ROI_GB: reason='fixed_roi_giveback'
                elif px<=ep*(1-sim.SL): reason='sl_hit'
                elif px>=ep*(1+sim.TP): reason='tp_hit'
                elif pnl>0 and (now-pos['last_best'])/1000>=sim.STALL: reason='stall_exit'
                if reason:
                    exnot=qty*px; gross=(px-ep)*qty; fees=(notion+exnot)*sim.FEE; net=gross-fees; bal+=net
                    trades.append({'seed':seed,'entry_i':entry_i,'entry_ms':pos['entry_ms'],'exit_ms':now,'score':score,'entry_progress':prog,
                                   'entry_price':ep,'exit_price':px,'gross_pnl_usdt':gross,'net_pnl_usdt':net,'fees_usdt':fees,'close_reason':reason,'balance_after':bal})
                    last_close=now; closed=True; break
            if closed: break
    return pd.DataFrame(trades),bal

def stats(t,b,start_bal=START):
    if t.empty: return {'final':b,'return_pct':(b/start_bal-1)*100,'trades':0,'wins':0,'losses':0,'win_rate':0,'gross_profit':0,'gross_loss':0,'gross_pnl':0,'fees':0,'net_pnl':b-start_bal,'profit_factor':0,'max_dd_pct':0}
    win=t[t.net_pnl_usdt>0]; loss=t[t.net_pnl_usdt<0]
    gp=float(win.net_pnl_usdt.sum()); gl=float(-loss.net_pnl_usdt.sum()); eq=np.r_[start_bal,t.balance_after.to_numpy(float)]; pk=np.maximum.accumulate(eq); dd=float((eq/pk-1).min()*100)
    return {'final':b,'return_pct':(b/start_bal-1)*100,'trades':len(t),'wins':len(win),'losses':len(loss),'win_rate':100*len(win)/len(t),'gross_profit':gp,'gross_loss':gl,'gross_pnl':float(t.gross_pnl_usdt.sum()),'fees':float(t.fees_usdt.sum()),'net_pnl':float(t.net_pnl_usdt.sum()),'profit_factor':gp/gl if gl>0 else (np.inf if gp>0 else 0),'max_dd_pct':dd}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(DATA)
    for c in ('open','high','low','close','volume'): df[c]=pd.to_numeric(df[c],errors='coerce')
    ts=pd.to_datetime(df.open_time,unit='ms',utc=True); df=df[(ts>=START6)&(ts<END)].copy().reset_index(drop=True)
    print('RANGE',START6,'->',END,'rows',len(df),flush=True)
    events,meta,p,agg,model,cand=build_events(df)
    print('MODEL_META_SYMBOL',(getattr(model,'meta',None) or getattr(model,'model_meta',{}) or {}).get('symbol'))
    print('EVENTS',len(events),'strong',sum(1 for x in meta.values() if x['kind']=='strong_recovery'),'base',sum(1 for x in meta.values() if x['kind']=='base'),'candidate_rows',len(cand),flush=True)
    cand.to_csv(OUT/'LONG1_NEAR_6M_CANDIDATES.csv',index=False)
    # 6 x 30d blocks, final block exact remainder to END
    bounds=[START6+pd.Timedelta(days=30*i) for i in range(7)]; bounds[-1]=END
    block_rows=[]; block_tr=[]
    for bi in range(6):
        a,b=bounds[bi],bounds[bi+1]; am=int(a.timestamp()*1000); bm=int(b.timestamp()*1000)
        for seed in SEEDS:
            t,bal=run(df,events,seed,START,am,bm); st=stats(t,bal); st.update({'block':bi+1,'start':str(a),'end':str(b),'seed':seed}); block_rows.append(st)
            if not t.empty: t=t.copy(); t['block']=bi+1; block_tr.append(t)
        sdf=pd.DataFrame([r for r in block_rows if r['block']==bi+1])
        print('BLOCK',bi+1,str(a.date()),str(b.date()),{'mean_return':sdf.return_pct.mean(),'mean_trades':sdf.trades.mean(),'mean_gp':sdf.gross_profit.mean(),'mean_gl':sdf.gross_loss.mean(),'mean_fees':sdf.fees.mean(),'mean_net':sdf.net_pnl.mean(),'mean_pf_finite':sdf.profit_factor.replace(np.inf,np.nan).mean(),'worst_dd':sdf.max_dd_pct.min(),'min_return':sdf.return_pct.min(),'max_return':sdf.return_pct.max()},flush=True)
    # continuous 180d per seed
    cont=[]; conttr=[]
    for seed in SEEDS:
        t,bal=run(df,events,seed,START); st=stats(t,bal); st['seed']=seed; cont.append(st)
        if not t.empty: t=t.copy(); t['mode']='continuous'; conttr.append(t)
        print('CONT',seed,st,flush=True)
    bs=pd.DataFrame(block_rows); cs=pd.DataFrame(cont)
    print('CONT_SUMMARY',{'mean_final':cs.final.mean(),'mean_return':cs.return_pct.mean(),'median_return':cs.return_pct.median(),'min_return':cs.return_pct.min(),'max_return':cs.return_pct.max(),'mean_trades':cs.trades.mean(),'mean_gp':cs.gross_profit.mean(),'mean_gl':cs.gross_loss.mean(),'mean_fees':cs.fees.mean(),'mean_net':cs.net_pnl.mean(),'mean_win':cs.win_rate.mean(),'mean_pf_finite':cs.profit_factor.replace(np.inf,np.nan).mean(),'worst_dd':cs.max_dd_pct.min()},flush=True)
    bs.to_csv(OUT/'LONG1_NEAR_6M_SL299_PROFITSTALL_SEEDS.csv',index=False); cs.to_csv(OUT/'LONG1_NEAR_6M_CONTINUOUS_SEEDS.csv',index=False)
    if block_tr: pd.concat(block_tr,ignore_index=True).to_csv(OUT/'LONG1_NEAR_6M_SL299_PROFITSTALL_TRADES.csv',index=False)
    if conttr: pd.concat(conttr,ignore_index=True).to_csv(OUT/'LONG1_NEAR_6M_CONTINUOUS_TRADES.csv',index=False)

if __name__=='__main__': main()
