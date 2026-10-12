from pathlib import Path
import os, sys, logging, random
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.load_env import load_environment_variables
from backtest_mtf import _resolve_build_features
from models.hybrid_inference import HybridModel

DATA=ROOT/'research/data/NEARUSDT_1m_1month.csv'
OUT=ROOT/'research/results'
SYMBOL='NEARUSDT'; MODEL_INTERVAL='3m'; START_EQUITY=1000.0
SEEDS=(1,2,3,4,5,6); PROGRESS_MIN=.08; PROGRESS_MAX=.52; WARMUP_3M_BARS=200
load_environment_variables()
LEV=float(os.getenv('DEFAULT_ORDER_LEVERAGE','3') or 3)
BAL_PCT=float(os.getenv('PER_POSITION_BALANCE_PCT','.50') or .50)
MODEL_THR=float(os.getenv('COIN_LONG_THRESHOLD_NEARUSDT', os.getenv('LONG_THRESHOLD','.525')) or .525)
OPEN_MIN=float(os.getenv('COIN_LONG_MIN_SCORE_NEARUSDT', os.getenv('OPEN_MIN_SCORE','.515')) or .515)
LONG_THR=float(os.getenv('LONG_THRESHOLD','.525') or .525)
REQ_SCORE=max(MODEL_THR,OPEN_MIN,LONG_THR)
COOLDOWN=float(os.getenv('SAME_SYMBOL_OPEN_COOLDOWN_SEC','180') or 180)
SL=float(os.getenv('SL_PCT','.02') or .02); TP=float(os.getenv('TP_PCT','.02') or .02)
ROI_STOP=float(os.getenv('ROI_HARD_STOP_PCT','-.075') or -.075)
ROI_TP=float(os.getenv('FIXED_ROI_TP_PCT','.012') or .012)
ROI_GB=float(os.getenv('FIXED_ROI_TP_GIVEBACK','.0024') or .0024)
STALL=float(os.getenv('STALL_TTL_SEC','2400') or 2400)
FEE=float(os.getenv('OUTCOME_TAKER_FEE_RATE','.0004') or .0004)

def nodes(row):
    o,h,l,c=[float(row[k]) for k in ('open','high','low','close')]
    return [(0,o),(.25,l),(.75,h),(1,c)] if c>=o else [(0,o),(.25,h),(.75,l),(1,c)]

def interp(ns,q):
    for (t0,p0),(t1,p1) in zip(ns[:-1],ns[1:]):
        if t0<=q<=t1:
            z=(q-t0)/(t1-t0) if t1>t0 else 0
            return p0+(p1-p0)*z
    return ns[-1][1]

def samples(row,start_q=0,step=5):
    ns=nodes(row); out=[]; first=max(0,int(np.ceil(start_q*60/step))*step)
    for s in range(first,61,step):
        q=s/60
        if q+1e-12>=start_q: out.append((q,interp(ns,q)))
    if not out or out[-1][0]<1: out.append((1,ns[-1][1]))
    return out

def build_decisions(df1):
    d=df1.copy()
    ts=pd.to_datetime(d.open_time,unit='ms',utc=True)
    d['bucket']=ts.dt.floor('3min')
    agg_map={
        'open':('open','first'),'high':('high','max'),'low':('low','min'),'close':('close','last'),'volume':('volume','sum'),
        'open_time':('open_time','first'),'close_time':('close_time','last'),'n':('open_time','size'),
    }
    for col in ('quote_asset_volume','number_of_trades','taker_buy_base_volume','taker_buy_quote_volume'):
        if col in d.columns: agg_map[col]=(col,'sum')
    if 'ignore' in d.columns: agg_map['ignore']=('ignore','last')
    agg=d.groupby('bucket',sort=True).agg(**agg_map).reset_index(drop=True)
    agg=agg[agg.n==3].drop(columns='n').reset_index(drop=True)
    log=logging.getLogger('long1-near-mtf')
    feat=_resolve_build_features(log)(agg,interval='3m')
    model=HybridModel(model_dir=os.getenv('MODELS_DIR',None),interval='3m',symbol=SYMBOL,logger=log)
    p,_=model.predict_proba(feat); p=np.asarray(p,dtype=float)
    if len(p)!=len(agg):
        # feature builders/models may drop warmup rows; align to tail as production-style latest rows
        off=max(0,len(agg)-len(p)); agg=agg.iloc[off:].reset_index(drop=True)
    n=min(len(agg),len(p)); agg=agg.iloc[-n:].reset_index(drop=True); p=p[-n:]
    # only one entry opportunity: first 1m candle strictly after completed 3m decision bar
    events={}
    opens=df1.open_time.to_numpy(dtype=np.int64)
    for k,(r,score) in enumerate(zip(agg.itertuples(index=False),p)):
        if k < WARMUP_3M_BARS: continue
        if not np.isfinite(score) or float(score)<REQ_SCORE: continue
        j=int(np.searchsorted(opens,int(r.close_time)+1,side='left'))
        if j<len(df1): events[j]=max(float(score),events.get(j,-np.inf))
    return events, p, agg, model

def run(df,events,seed):
    rng=random.Random(seed); bal=START_EQUITY; trades=[]; pos=None; last_close=-10**30
    for i,row in df.iterrows():
        open_ms=int(row.open_time)
        if pos is None and i in events and open_ms>=last_close+int(COOLDOWN*1000):
            prog=rng.uniform(PROGRESS_MIN,PROGRESS_MAX); ep=interp(nodes(row),prog)
            notion=bal*BAL_PCT; qty=notion/max(ep,1e-12)
            pos={'entry_i':i,'entry_ms':open_ms+int(prog*60000),'entry':ep,'qty':qty,'notional':notion,'score':events[i],
                 'best_roi':0.0,'best_pnl':0.0,'last_best':open_ms+int(prog*60000),'armed':False,'progress':prog,
                 'min':ep,'max':ep,'ever_neg':False,'neg_start':None,'first_green':None}
        if pos is None: continue
        start_q=pos['progress'] if pos['entry_i']==i else 0
        for q,px in samples(row,start_q):
            now=open_ms+int(q*60000); ep=pos['entry']; pnl=(px-ep)/ep; roi=pnl*LEV
            pos['min']=min(pos['min'],px); pos['max']=max(pos['max'],px)
            if pnl<0 and not pos['ever_neg']: pos['ever_neg']=True; pos['neg_start']=now
            if pos['ever_neg'] and pos['first_green'] is None and pnl>0: pos['first_green']=now
            if pnl>pos['best_pnl']: pos['best_pnl']=pnl; pos['last_best']=now
            if roi>pos['best_roi']: pos['best_roi']=roi
            if pos['best_roi']>=ROI_TP: pos['armed']=True
            reason=None
            if roi<=ROI_STOP: reason='roi_hard_stop_lifecycle'
            elif pos['armed'] and roi<=pos['best_roi']-ROI_GB: reason='fixed_roi_giveback'
            elif px<=ep*(1-SL): reason='sl_hit'
            elif px>=ep*(1+TP): reason='tp_hit'
            elif (now-pos['last_best'])/1000>=STALL: reason='stall_exit'
            if reason:
                exnot=pos['qty']*px; gross=(px-ep)*pos['qty']; fees=(pos['notional']+exnot)*FEE; net=gross-fees; bal+=net
                trades.append({'seed':seed,'entry_i':pos['entry_i'],'exit_i':i,'score':pos['score'],'entry_progress':pos['progress'],
                    'entry_price':ep,'exit_price':px,'net_pnl_usdt':net,'fees_usdt':fees,'close_reason':reason,
                    'net_on_position_pct':net/pos['notional']*100,'duration_sec':(now-pos['entry_ms'])/1000,
                    'ever_negative':pos['ever_neg'],'negative_to_green_sec':((pos['first_green']-pos['neg_start'])/1000 if pos['first_green'] and pos['neg_start'] else np.nan),
                    'balance_after':bal})
                last_close=now; pos=None; break
    return pd.DataFrame(trades),bal

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(DATA)
    for c in ('open','high','low','close','volume'): df[c]=pd.to_numeric(df[c],errors='coerce')
    events,p,agg,model=build_decisions(df)
    print('CONFIG',{'symbol':SYMBOL,'model_interval':MODEL_INTERVAL,'required_score':REQ_SCORE,'lev':LEV,'tp_roi':ROI_TP,'giveback':ROI_GB,'sl':SL,'stall':STALL})
    print('MODEL_META_SYMBOL', (getattr(model,'meta',None) or getattr(model,'model_meta',{}) or {}).get('symbol'))
    pe=p[WARMUP_3M_BARS:]
    print('MODEL_SCORE',{'n':len(pe),'mean':float(np.nanmean(pe)),'max':float(np.nanmax(pe)),'raw_candidates':int(np.sum(pe>=REQ_SCORE)),'entry_events':len(events),'warmup_3m_bars':WARMUP_3M_BARS})
    rows=[]; alltr=[]
    for seed in SEEDS:
        t,b=run(df,events,seed); alltr.append(t)
        w=int((t.net_pnl_usdt>0).sum()) if len(t) else 0
        rows.append({'seed':seed,'final':b,'return_pct':(b/START_EQUITY-1)*100,'trades':len(t),'win_rate':(100*w/len(t) if len(t) else 0),'fees':float(t.fees_usdt.sum()) if len(t) else 0})
        print('RESULT',rows[-1],flush=True)
    s=pd.DataFrame(rows); tr=pd.concat(alltr,ignore_index=True) if alltr else pd.DataFrame()
    print('SUMMARY',{'mean_final':float(s.final.mean()),'mean_return_pct':float(s.return_pct.mean()),'median_return_pct':float(s.return_pct.median()),'min_return_pct':float(s.return_pct.min()),'max_return_pct':float(s.return_pct.max()),'mean_trades':float(s.trades.mean()),'mean_win_rate':float(s.win_rate.mean()),'mean_fees':float(s.fees.mean())})
    s.to_csv(OUT/'LONG1_NEAR_30D_MTF_SEEDS.csv',index=False); tr.to_csv(OUT/'LONG1_NEAR_30D_MTF_TRADES.csv',index=False)

if __name__=='__main__': main()
