import os, json, logging
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
import sys
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.load_env import load_environment_variables
from backtest_mtf import _resolve_build_features
from models.hybrid_inference import HybridModel

DATA=ROOT/'research/data/NEARUSDT_1m_1month.csv'
OUT=ROOT/'research/results'
PROGRESS_SCENARIOS=(0.08,0.20,0.30,0.40,0.52)
START_EQUITY=1000.0

load_environment_variables()
LEV=float(os.getenv('SIM_LEVERAGE', os.getenv('DEFAULT_ORDER_LEVERAGE','3')) or 3)
BAL_PCT=float(os.getenv('PER_POSITION_BALANCE_PCT','0.50') or .50)
BASE_SCORE=float(os.getenv('OPEN_MIN_SCORE','0.515') or .515)
LONG_SIGNAL_THRESHOLD=float(os.getenv('LONG_THRESHOLD','0.525') or .525)
REENTRY_COOLDOWN_SEC=float(os.getenv('SAME_SYMBOL_OPEN_COOLDOWN_SEC','180') or 180)
DYN_ENABLE=str(os.getenv('DYNAMIC_COIN_SCORE_ENABLE','0')).lower() in ('1','true','yes','on')
DYN_MIN=float(os.getenv('DYNAMIC_SCORE_MIN','0.515') or .515)
DYN_MAX=float(os.getenv('DYNAMIC_SCORE_MAX','0.560') or .560)
ATR_BOOST=float(os.getenv('DYNAMIC_SCORE_ATR_BOOST','0') or 0)
SL=float(os.getenv('SIM_SL_PCT', os.getenv('SL_PCT','0.01')) or .01)
TP=float(os.getenv('TP_PCT','0.02') or .02)
ROI_STOP=float(os.getenv('ROI_HARD_STOP_PCT','-0.075') or -.075)
ROI_TP=float(os.getenv('SIM_ROI_TP_PCT', os.getenv('FIXED_ROI_TP_PCT','0.0045')) or .0045)
ROI_GB=float(os.getenv('SIM_ROI_GIVEBACK', os.getenv('FIXED_ROI_TP_GIVEBACK','0.0008')) or .0008)
STALL=float(os.getenv('STALL_TTL_SEC','1200') or 1200)
FEE=float(os.getenv('OUTCOME_TAKER_FEE_RATE','0.0004') or .0004)


def path_nodes(row):
    o,h,l,c=[float(row[k]) for k in ('open','high','low','close')]
    if c>=o: return [(0.,o),(.25,l),(.75,h),(1.,c)]
    return [(0.,o),(.25,h),(.75,l),(1.,c)]


def interp(nodes,q):
    q=float(np.clip(q,0,1))
    for (t0,p0),(t1,p1) in zip(nodes[:-1],nodes[1:]):
        if t0<=q<=t1:
            z=(q-t0)/(t1-t0) if t1>t0 else 0
            return p0+(p1-p0)*z
    return nodes[-1][1]


def sample_after(row, start_q=0.0, step_sec=5):
    nodes=path_nodes(row); times=[]
    first=max(0,int(np.ceil(start_q*60/step_sec))*step_sec)
    for s in range(first,61,step_sec):
        q=s/60.0
        if q+1e-12 < start_q: continue
        times.append((q,interp(nodes,q)))
    if not times or times[-1][0] < 1.0: times.append((1.0,nodes[-1][1]))
    return times


def prepare_probs(df):
    log=logging.getLogger('sim')
    fn=_resolve_build_features(log)
    feat=fn(df,interval='1m')
    model=HybridModel(model_dir=os.getenv('MODELS_DIR',None),interval='1m',logger=log)
    p,_=model.predict_proba(feat)
    p=np.asarray(p,dtype=float)
    atr=pd.to_numeric(feat['atr'],errors='coerce').fillna(0).to_numpy() if 'atr' in feat.columns else np.zeros(len(df))
    return p,atr


def threshold(atr):
    x=BASE_SCORE
    if DYN_ENABLE and atr>0: x+=ATR_BOOST
    return max(DYN_MIN,min(DYN_MAX,x)) if DYN_ENABLE else x


def run_scenario(df,p,atr,entry_progress):
    balance=START_EQUITY; trades=[]; pos=None; last_close_ms=-10**18
    start_i=200
    for i in range(start_i,len(df)):
        row=df.iloc[i]; open_ms=int(row.open_time)
        if pos is None:
            if open_ms < last_close_ms + int(REENTRY_COOLDOWN_SEC*1000):
                continue
            score=float(p[i-1]) if i-1<len(p) else .5
            req=threshold(float(atr[i-1]) if i-1<len(atr) else 0)
            if score>=max(req,LONG_SIGNAL_THRESHOLD):
                nodes=path_nodes(row); ep=interp(nodes,entry_progress)
                notional=balance*BAL_PCT; qty=notional/max(ep,1e-12)
                pos={'entry_i':i,'entry_ms':open_ms+int(entry_progress*60000),'entry_price':ep,'qty':qty,
                     'entry_notional':notional,'score':score,'required_score':req,'best_roi':0.0,'best_pnl':0.0,
                     'last_best_ms':open_ms+int(entry_progress*60000),'armed':False,'min_price':ep,'max_price':ep,
                     'ever_negative':False,'negative_start_ms':None,'first_green_ms':None,'first_net_green_ms':None}
            else:
                continue
        start_q=entry_progress if pos['entry_i']==i else 0.0
        for q,px in sample_after(row,start_q):
            now_ms=open_ms+int(q*60000); ep=pos['entry_price']; px=float(px)
            pnl=(px-ep)/ep; roi=pnl*LEV
            pos['min_price']=min(pos['min_price'],px); pos['max_price']=max(pos['max_price'],px)
            if pnl<0 and not pos['ever_negative']:
                pos['ever_negative']=True; pos['negative_start_ms']=now_ms
            if pos['ever_negative'] and pos['first_green_ms'] is None and pnl>0:
                pos['first_green_ms']=now_ms
            if pos['ever_negative'] and pos['first_net_green_ms'] is None and pnl>(2*FEE):
                pos['first_net_green_ms']=now_ms
            if pnl>pos['best_pnl']:
                pos['best_pnl']=pnl; pos['last_best_ms']=now_ms
            if roi>pos['best_roi']: pos['best_roi']=roi
            if pos['best_roi']>=ROI_TP: pos['armed']=True
            reason=None
            if roi<=ROI_STOP: reason='roi_hard_stop_lifecycle'
            elif pos['armed'] and roi<=pos['best_roi']-ROI_GB: reason='fixed_roi_giveback'
            elif px<=ep*(1-SL): reason='sl_hit'
            elif px>=ep*(1+TP): reason='tp_hit'
            elif (now_ms-pos['last_best_ms'])/1000.0>=STALL: reason='stall_exit'
            if reason:
                exit_notional=pos['qty']*px; gross=(px-ep)*pos['qty']
                fees=(pos['entry_notional']+exit_notional)*FEE; net=gross-fees; balance+=net
                dur=(now_ms-pos['entry_ms'])/1000.0
                trades.append({'entry_progress':entry_progress,'entry_i':pos['entry_i'],'exit_i':i,'entry_ms':pos['entry_ms'],'exit_ms':now_ms,
                    'entry_price':ep,'exit_price':px,'score':pos['score'],'required_score':pos['required_score'],'qty':pos['qty'],
                    'gross_pnl_usdt':gross,'fees_usdt':fees,'net_pnl_usdt':net,'price_return_pct':(px/ep-1)*100,
                    'roi_pct':(px/ep-1)*LEV*100,'net_on_position_pct':net/pos['entry_notional']*100,'close_reason':reason,'duration_sec':dur,
                    'mae_price_pct':(pos['min_price']/ep-1)*100,'mfe_price_pct':(pos['max_price']/ep-1)*100,'ever_negative':pos['ever_negative'],
                    'negative_to_green_sec':((pos['first_green_ms']-pos['negative_start_ms'])/1000.0 if pos['first_green_ms'] and pos['negative_start_ms'] else np.nan),
                    'negative_to_net_green_sec':((pos['first_net_green_ms']-pos['negative_start_ms'])/1000.0 if pos['first_net_green_ms'] and pos['negative_start_ms'] else np.nan),
                    'balance_after':balance})
                last_close_ms=now_ms; pos=None; break
    if pos is not None:
        row=df.iloc[-1]; px=float(row.close); now_ms=int(row.close_time); ep=pos['entry_price']
        exit_notional=pos['qty']*px; gross=(px-ep)*pos['qty']; fees=(pos['entry_notional']+exit_notional)*FEE; net=gross-fees; balance+=net
        trades.append({'entry_progress':entry_progress,'entry_i':pos['entry_i'],'exit_i':len(df)-1,'entry_ms':pos['entry_ms'],'exit_ms':now_ms,
            'entry_price':ep,'exit_price':px,'score':pos['score'],'required_score':pos['required_score'],'qty':pos['qty'],'gross_pnl_usdt':gross,'fees_usdt':fees,
            'net_pnl_usdt':net,'price_return_pct':(px/ep-1)*100,'roi_pct':(px/ep-1)*LEV*100,'net_on_position_pct':net/pos['entry_notional']*100,
            'close_reason':'EOB_FORCE_CLOSE','duration_sec':(now_ms-pos['entry_ms'])/1000.0,'mae_price_pct':(pos['min_price']/ep-1)*100,
            'mfe_price_pct':(pos['max_price']/ep-1)*100,'ever_negative':pos['ever_negative'],'negative_to_green_sec':np.nan,'negative_to_net_green_sec':np.nan,'balance_after':balance})
    return pd.DataFrame(trades),balance


def summarize(t,balance):
    if t.empty:return {}
    winners=t[t.net_pnl_usdt>0]; losers=t[t.net_pnl_usdt<0]; recovered=winners[winners.ever_negative==True]
    return {'trades':len(t),'wins':len(winners),'losses':len(losers),'win_rate_pct':len(winners)/len(t)*100,
            'final_balance_usdt':balance,'net_pnl_usdt':balance-START_EQUITY,'return_pct':(balance/START_EQUITY-1)*100,
            'fees_usdt':t.fees_usdt.sum(),'avg_net_trade_usdt':t.net_pnl_usdt.mean(),'median_loss_position_pct':losers.net_on_position_pct.median() if len(losers) else np.nan,
            'p10_loss_position_pct':losers.net_on_position_pct.quantile(.10) if len(losers) else np.nan,'worst_loss_position_pct':losers.net_on_position_pct.min() if len(losers) else np.nan,
            'recovered_winner_count':len(recovered),'recovered_winner_pct_of_wins':len(recovered)/len(winners)*100 if len(winners) else 0,
            'median_negative_to_green_sec':recovered.negative_to_green_sec.median() if len(recovered) else np.nan,
            'median_negative_to_net_green_sec':recovered.negative_to_net_green_sec.median() if len(recovered) else np.nan,
            'median_duration_sec':t.duration_sec.median()}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(DATA)
    for c in ('open','high','low','close','volume'): df[c]=pd.to_numeric(df[c],errors='coerce')
    p,atr=prepare_probs(df)
    print('DATA',len(df),'P',len(p),'period',pd.to_datetime(df.open_time.iloc[0],unit='ms',utc=True),'->',pd.to_datetime(df.close_time.iloc[-1],unit='ms',utc=True),flush=True)
    summaries=[]; alltr=[]
    for prog in PROGRESS_SCENARIOS:
        t,b=run_scenario(df,p,atr,prog); s=summarize(t,b); s['entry_progress']=prog; summaries.append(s); alltr.append(t)
        print('SCENARIO',prog,s,flush=True)
    td=pd.concat(alltr,ignore_index=True) if alltr else pd.DataFrame(); sd=pd.DataFrame(summaries)
    tag=os.getenv('SIM_TAG','BASE'); td.to_csv(OUT/f'NEAR_LONG_30D_TRADES_{tag}.csv',index=False); sd.to_csv(OUT/f'NEAR_LONG_30D_SUMMARY_{tag}.csv',index=False)
    if not td.empty:
        cr=td.groupby(['entry_progress','close_reason']).agg(n=('net_pnl_usdt','size'),net_pnl_usdt=('net_pnl_usdt','sum'),avg_position_pct=('net_on_position_pct','mean')).reset_index()
        cr.to_csv(OUT/f'NEAR_LONG_30D_CLOSE_REASONS_{tag}.csv',index=False)
        bins=[-999,-5,-3,-2,-1,-.5,0]; labels=['<=-5%','-5..-3%','-3..-2%','-2..-1%','-1..-0.5%','-0.5..0%']
        loss=td[td.net_pnl_usdt<0].copy(); loss['loss_bucket']=pd.cut(loss.net_on_position_pct,bins=bins,labels=labels,include_lowest=True)
        lb=loss.groupby(['entry_progress','loss_bucket'],observed=False).size().reset_index(name='n'); lb.to_csv(OUT/f'NEAR_LONG_30D_LOSS_BUCKETS_{tag}.csv',index=False)
    print('\nSUMMARY\n',sd.to_string(index=False),flush=True)

if __name__=='__main__': main()
