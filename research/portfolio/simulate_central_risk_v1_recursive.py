#!/usr/bin/env python3
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path('/home/kasm920/binance1-pro')
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from orchestration.risk.central_risk_master import (
    CentralRiskConfig, CentralRiskMaster, EntryRiskRequest,
    PortfolioRiskState, PositionExposure,
)

LONG_DIR=ROOT/'research/results/LONG1_SINGLE_F60_015_CAUSAL_POSITIONS_20261021'
SHORT_POS=ROOT/'research/results/SHORT1_V49B_R70_W2_POSITION_EXPOSURE_20261021.csv'
SHORT_Q=Path('/home/kasm920/binance1/research/short/results/SHORT1_V49B_TRADE_CONFIRM/V49B_R70_W2/equity_curve.csv')
OUT=ROOT/'research/results/CENTRAL_RISK_V1_RECURSIVE_CAUSAL015_20261021'; OUT.mkdir(parents=True,exist_ok=True)
START_EQ=1000.0; ENGINE_WEIGHT=0.50

def short_mode_mult(mode): return {'NORMAL':1.0,'RECOVERY':.70,'REDUCED':.50}.get(str(mode).upper(),1.0)

def load_short():
    s=pd.read_csv(SHORT_POS); q=pd.read_csv(SHORT_Q,usecols=['ts','sizing_mode'])
    s['entry_ts']=pd.to_datetime(s.open_ts,utc=True,format='mixed'); s['exit_ts']=pd.to_datetime(s.close_ts,utc=True,format='mixed')
    q['ts']=pd.to_datetime(q.ts,utc=True,format='mixed')
    s=s.merge(q.rename(columns={'ts':'entry_ts'}),on='entry_ts',how='left')
    s['source_return']=s.pnl_net/s.notional
    s['context_mult']=s.ratio/s.sizing_mode.map(short_mode_mult)
    s['context_mult']=s.context_mult.clip(.49,1.01).where(s.context_mult>.75,.50).where(s.context_mult<=.75,1.0)
    return s

SHORT=load_short()

def load_long(seed):
    d=pd.read_csv(LONG_DIR/f'seed{seed}.csv')
    d['entry_ts']=pd.to_datetime(d.entry_ts,utc=True,format='mixed'); d['exit_ts']=pd.to_datetime(d.exit_ts,utc=True,format='mixed')
    d['source_return']=d.net/d.notional; d['context_mult']=1.0
    return d

def event_book(seed):
    l=load_long(seed); s=SHORT.copy()
    start=max(l.entry_ts.min(),s.entry_ts.min()); end=min(l.exit_ts.max(),s.exit_ts.max())
    rows=[]
    for i,r in l.iterrows():
        if r.entry_ts>=start and r.exit_ts<=end:
            tid=f'L{seed}_{i}'; rows += [(r.entry_ts,1,'ENTRY',tid,'LONG1','NEARUSDT','long',r.source_return,r.reason,r.context_mult),(r.exit_ts,0,'EXIT',tid,'LONG1','NEARUSDT','long',r.source_return,r.reason,r.context_mult)]
    for i,r in s.iterrows():
        if r.entry_ts>=start and r.exit_ts<=end:
            tid=f'S_{i}'; rows += [(r.entry_ts,1,'ENTRY',tid,'SHORT1','INJUSDT','short',r.source_return,r.reason,r.context_mult),(r.exit_ts,0,'EXIT',tid,'SHORT1','INJUSDT','short',r.source_return,r.reason,r.context_mult)]
    # EXIT first at identical timestamps, then ENTRY.
    return pd.DataFrame(rows,columns=['ts','order','kind','trade_id','strategy','symbol','side','source_return','reason','context_mult']).sort_values(['ts','order']).reset_index(drop=True)

def scenario_config(gross, central_state=True):
    if central_state:
        nm,rm,dm=1.0,.70,.50
    else:
        nm=rm=dm=1.0
    return CentralRiskConfig(
        normal_multiplier=nm,recovery_multiplier=rm,reduced_multiplier=dm,
        max_open_positions=8,min_order_notional=10,
        max_gross_exposure_ratio=gross,max_long_exposure_ratio=.50,
        max_short_exposure_ratio=.50,max_abs_net_exposure_ratio=.50,
        max_symbol_exposure_ratio=.50,
    )

def run(seed,name,gross,central_state=True):
    ev=event_book(seed); master=CentralRiskMaster(scenario_config(gross,central_state)); state=PortfolioRiskState(START_EQ,'NORMAL',0)
    equity=START_EQ; peak=equity; openp={}; curve=[]; closed=[]; decisions=[]
    for r in ev.itertuples(index=False):
        if r.kind=='EXIT':
            p=openp.pop(r.trade_id,None)
            if p is None: continue
            pnl=p['notional']*float(r.source_return); equity+=pnl; peak=max(peak,equity); dd=equity/peak-1.0
            stop=str(r.reason).lower() in {'sl','cat','soft_stop_1m_confirm','catastrophic','dynamic_stop_confirmed','dynamic_stop_catastrophic'}
            state,reasons=master.update_state_on_close(state=state,equity_after=equity,pnl_net=pnl,opened_risk_mode=p['opened_mode'],is_risk_stop=stop)
            closed.append({'ts':r.ts,'trade_id':r.trade_id,'strategy':r.strategy,'pnl':pnl,'return_frac':r.source_return,'reason':r.reason,'notional':p['notional'],'opened_mode':p['opened_mode'],'mode_after':state.mode,'equity':equity,'dd':dd,'state_reasons':'|'.join(reasons)})
        else:
            positions=[PositionExposure(v['strategy'],v['symbol'],v['side'],v['notional'],v['opened_mode']) for v in openp.values()]
            requested=equity*ENGINE_WEIGHT
            req=EntryRiskRequest(r.strategy,r.symbol,r.side,requested,float(r.context_mult))
            dec=master.evaluate_entry(request=req,state=state,portfolio_equity=equity,positions=positions)
            clipped=dec.allowed_notional+1e-9 < dec.risk_scaled_notional
            decisions.append({'ts':r.ts,'trade_id':r.trade_id,'strategy':r.strategy,'mode':state.mode,'requested':requested,'context_mult':r.context_mult,'risk_scaled':dec.risk_scaled_notional,'allowed':dec.allowed_notional,'clipped':clipped,'decision':dec.state,'reasons':'|'.join(dec.reason_codes)})
            if dec.allowed_notional>0:
                openp[r.trade_id]={'strategy':r.strategy,'symbol':r.symbol,'side':r.side,'notional':dec.allowed_notional,'opened_mode':state.mode}
        gross=sum(v['notional'] for v in openp.values())/max(equity,1e-12); net=sum((1 if v['side']=='long' else -1)*v['notional'] for v in openp.values())/max(equity,1e-12)
        curve.append({'ts':r.ts,'equity':equity,'mode':state.mode,'recovery_successes':state.recovery_successes,'gross_ratio':gross,'net_ratio':net,'open_positions':len(openp)})
    C=pd.DataFrame(closed); Q=pd.DataFrame(curve); D=pd.DataFrame(decisions)
    p=C.pnl.to_numpy(float) if len(C) else np.array([]); gp=p[p>0].sum(); gl=-p[p<0].sum(); eqv=Q.equity.to_numpy(float); pk=np.maximum.accumulate(eqv); dd=np.min(eqv/pk-1)*100
    result={'seed':seed,'scenario':name,'return_pct':(equity/START_EQ-1)*100,'pf':gp/gl if gl>0 else np.nan,'maxdd_pct':dd,'closed':len(C),'entry_decisions':len(D),'rejected':int((D.decision=='REJECT').sum()),'clipped':int(D.clipped.sum()),'clipped_pct':100*D.clipped.mean(),'max_gross':Q.gross_ratio.max(),'max_abs_net':Q.net_ratio.abs().max(),'reduced_entries':int((D['mode']=='REDUCED').sum()),'recovery_entries':int((D['mode']=='RECOVERY').sum())}
    C.to_csv(OUT/f'{name}_seed{seed}_closed.csv',index=False); Q.to_csv(OUT/f'{name}_seed{seed}_curve.csv',index=False); D.to_csv(OUT/f'{name}_seed{seed}_decisions.csv',index=False)
    return result

def main():
    scenarios=[('STATE_G100',1.00,True),('STATE_G075',.75,True),('STATE_G050',.50,True),('NOSTATE_G100',1.00,False)]
    rows=[]
    for name,g,state_on in scenarios:
        for seed in range(1,7):
            x=run(seed,name,g,state_on); rows.append(x); print(x,flush=True)
    R=pd.DataFrame(rows); R.to_csv(OUT/'summary_by_seed.csv',index=False)
    A=R.groupby('scenario').agg(return_mean=('return_pct','mean'),return_min=('return_pct','min'),return_max=('return_pct','max'),pf_mean=('pf','mean'),dd_mean=('maxdd_pct','mean'),dd_worst=('maxdd_pct','min'),clipped_mean=('clipped_pct','mean'),max_gross=('max_gross','max'),max_abs_net=('max_abs_net','max'),reduced_entries=('reduced_entries','mean'),recovery_entries=('recovery_entries','mean')).reset_index()
    A.to_csv(OUT/'summary_aggregate.csv',index=False); print('\nAGGREGATE\n'+A.to_string(index=False),flush=True)
if __name__=='__main__': main()
