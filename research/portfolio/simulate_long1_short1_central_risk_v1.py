from pathlib import Path
import sys
ROOT=Path('/home/kasm920/binance1-pro')
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import pandas as pd, numpy as np
from orchestration.risk.central_risk_master import CentralRiskConfig, CentralRiskMaster, PortfolioRiskState, PositionExposure, EntryRiskRequest
LONG_DIR=ROOT/'research/results/LONG1_SINGLE_F60_020_POSITIONS_20261021'
SHORT_DIR=Path('/home/kasm920/binance1/research/short/results/SHORT1_V49B_TRADE_CONFIRM/V49B_R70_W2')
OUT=ROOT/'research/results/LONG1_SHORT1_CENTRAL_RISK_V1_20261021'; OUT.mkdir(parents=True,exist_ok=True)

def load_short():
    e=pd.read_csv(SHORT_DIR/'entries.csv'); c=pd.read_csv(SHORT_DIR/'closed_positions.csv'); q=pd.read_csv(SHORT_DIR/'equity_curve.csv')
    for d,col in [(e,'ts'),(c,'open_ts'),(c,'close_ts'),(q,'ts')]: d[col]=pd.to_datetime(d[col],utc=True,format='mixed')
    e=e[e.layer==1].copy(); m=c.merge(e[['ts','notional']],left_on='open_ts',right_on='ts',how='left',validate='one_to_one')
    m=m.merge(q[['ts','equity','sizing_mode']],left_on='open_ts',right_on='ts',how='left',validate='one_to_one')
    sm=m.sizing_mode.map({'NORMAL':1.0,'RECOVERY':0.7,'REDUCED':0.5})
    ctx=m.notional/(m.equity*sm)
    m['context_mult']=np.where(ctx<.75,.5,1.0)
    m['unit_net_return']=m.pnl_net/m.notional
    m['strategy_id']='SHORT1'; m['symbol']='INJUSDT'; m['side']='short'; m['source_notional']=m.notional
    return m[['open_ts','close_ts','strategy_id','symbol','side','context_mult','unit_net_return','source_notional','reason']].sort_values('open_ts').reset_index(drop=True)

def load_long(seed):
    m=pd.read_csv(LONG_DIR/f'seed{seed}.csv')
    m['open_ts']=pd.to_datetime(m.entry_ts,utc=True,format='mixed'); m['close_ts']=pd.to_datetime(m.exit_ts,utc=True,format='mixed')
    m['context_mult']=1.0; m['unit_net_return']=m.net/m.notional
    m['strategy_id']='LONG1'; m['symbol']='NEARUSDT'; m['side']='long'; m['source_notional']=m.notional
    return m[['open_ts','close_ts','strategy_id','symbol','side','context_mult','unit_net_return','source_notional','reason']].sort_values('open_ts').reset_index(drop=True)

def risk_stop(reason):
    r=str(reason or '').lower(); return any(x in r for x in ['stop','sl','cat'])

def maxdd(vals):
    a=np.asarray(vals,float); p=np.maximum.accumulate(a); return float(np.min(a/p-1.0)*100.0)

def run(seed,name,cfg,use_state=True,budget=.50):
    T=pd.concat([load_long(seed),load_short()],ignore_index=True)
    T=T[(T.open_ts>=max(T[T.strategy_id=='LONG1'].open_ts.min(),T[T.strategy_id=='SHORT1'].open_ts.min()))].copy().reset_index(drop=True)
    T['trade_id']=[f'{r.strategy_id}:{i}' for i,r in T.iterrows()]
    events=[]
    for r in T.itertuples(index=False):
        events.append((r.open_ts,1,'OPEN',r))
        events.append((r.close_ts,0,'CLOSE',r))  # close before open at same timestamp
    events.sort(key=lambda x:(x[0],x[1]))
    rm=CentralRiskMaster(cfg); state=PortfolioRiskState(1000.0,'NORMAL',0); equity=1000.0; openp={}; rows=[]; eqrows=[{'ts':events[0][0],'equity':equity,'mode':state.mode,'event':'START'}]
    cap_limited=0; rejected=0; state_changes=0
    for ts,_,kind,r in events:
        tid=r.trade_id
        if kind=='OPEN':
            positions=[x['exposure'] for x in openp.values()]
            req=EntryRiskRequest(r.strategy_id,r.symbol,r.side,equity*budget,float(r.context_mult))
            # STATIC disables portfolio-state size reduction but keeps all context/caps.
            eval_state=state if use_state else PortfolioRiskState(state.equity_peak,'NORMAL',0)
            d=rm.evaluate_entry(request=req,state=eval_state,portfolio_equity=equity,positions=positions)
            if d.allowed_notional<=0:
                rejected+=1; rows.append({'ts':ts,'kind':'OPEN_REJECT','trade_id':tid,'strategy_id':r.strategy_id,'equity':equity,'mode':state.mode,'allowed_notional':0.0,'unit_net_return':r.unit_net_return,'reasons':'|'.join(d.reason_codes)}); continue
            if d.allowed_notional < d.risk_scaled_notional-1e-9: cap_limited+=1
            opened_mode=eval_state.normalized_mode()
            ex=PositionExposure(r.strategy_id,r.symbol,r.side,d.allowed_notional,opened_mode)
            openp[tid]={'exposure':ex,'unit_net_return':float(r.unit_net_return),'reason':r.reason,'source':r}
            rows.append({'ts':ts,'kind':'OPEN','trade_id':tid,'strategy_id':r.strategy_id,'equity':equity,'mode':state.mode,'allowed_notional':d.allowed_notional,'unit_net_return':r.unit_net_return,'reasons':'|'.join(d.reason_codes)})
        else:
            z=openp.pop(tid,None)
            if z is None: continue
            pnl=float(z['exposure'].notional)*float(z['unit_net_return']); equity+=pnl
            prev=state.mode
            if use_state:
                state,reasons=rm.update_state_on_close(state=state,equity_after=equity,pnl_net=pnl,opened_risk_mode=z['exposure'].opened_risk_mode,is_risk_stop=risk_stop(z['reason']))
            else:
                state=PortfolioRiskState(max(state.equity_peak,equity),'NORMAL',0); reasons=('static_state',)
            if state.mode!=prev: state_changes+=1
            rows.append({'ts':ts,'kind':'CLOSE','trade_id':tid,'strategy_id':r.strategy_id,'equity':equity,'mode':state.mode,'allowed_notional':z['exposure'].notional,'unit_net_return':z['unit_net_return'],'pnl_net':pnl,'reasons':'|'.join(reasons)})
            eqrows.append({'ts':ts,'equity':equity,'mode':state.mode,'event':'CLOSE','strategy_id':r.strategy_id,'pnl_net':pnl})
    R=pd.DataFrame(rows); E=pd.DataFrame(eqrows).sort_values('ts')
    closes=R[R.kind=='CLOSE'].copy(); gp=closes.loc[closes.pnl_net>0,'pnl_net'].sum(); gl=-closes.loc[closes.pnl_net<0,'pnl_net'].sum()
    monthly=closes.assign(month=closes.ts.dt.to_period('M').astype(str)).groupby('month',as_index=False).agg(pnl=('pnl_net','sum'))
    # monthly return on month-start realized equity
    eq0=1000.; mr=[]
    for x in monthly.itertuples(index=False): mr.append((x.month,100*x.pnl/eq0)); eq0+=x.pnl
    M=pd.DataFrame(mr,columns=['month','return_pct'])
    summary={'scenario':name,'seed':seed,'return_pct':100*(equity/1000-1),'pf':gp/max(gl,1e-12),'maxdd_pct':maxdd(E.equity),'closed':len(closes),'cap_limited_opens':cap_limited,'rejected_opens':rejected,'state_changes':state_changes,'negative_months':int((M.return_pct<0).sum()),'worst_month_pct':float(M.return_pct.min()) if len(M) else 0.0,'final_equity':equity}
    R.to_csv(OUT/f'{name}_seed{seed}_events.csv',index=False); E.to_csv(OUT/f'{name}_seed{seed}_equity.csv',index=False); M.to_csv(OUT/f'{name}_seed{seed}_monthly.csv',index=False)
    return summary

def main():
    SCENARIOS=[
     ('EQ50_STATIC',False,CentralRiskConfig(normal_multiplier=1,recovery_multiplier=1,reduced_multiplier=1,max_open_positions=2,max_gross_exposure_ratio=1.0,max_long_exposure_ratio=.5,max_short_exposure_ratio=.5,max_abs_net_exposure_ratio=.5,max_symbol_exposure_ratio=.5)),
     ('CENTRAL_V49_G100',True,CentralRiskConfig(max_open_positions=2,max_gross_exposure_ratio=1.0,max_long_exposure_ratio=.5,max_short_exposure_ratio=.5,max_abs_net_exposure_ratio=.5,max_symbol_exposure_ratio=.5)),
     ('CENTRAL_V49_G075',True,CentralRiskConfig(max_open_positions=2,max_gross_exposure_ratio=.75,max_long_exposure_ratio=.5,max_short_exposure_ratio=.5,max_abs_net_exposure_ratio=.5,max_symbol_exposure_ratio=.5)),
     ('CENTRAL_V49_G060',True,CentralRiskConfig(max_open_positions=2,max_gross_exposure_ratio=.60,max_long_exposure_ratio=.5,max_short_exposure_ratio=.5,max_abs_net_exposure_ratio=.5,max_symbol_exposure_ratio=.5)),
    ]
    rows=[]
    for name,use,cfg in SCENARIOS:
        for seed in range(1,7):
            s=run(seed,name,cfg,use_state=use); rows.append(s); print('RESULT',s,flush=True)
    R=pd.DataFrame(rows); R.to_csv(OUT/'summary_by_seed.csv',index=False)
    A=R.groupby('scenario').agg(return_mean=('return_pct','mean'),return_min=('return_pct','min'),return_max=('return_pct','max'),pf_mean=('pf','mean'),dd_mean=('maxdd_pct','mean'),dd_worst=('maxdd_pct','min'),cap_limited_mean=('cap_limited_opens','mean'),rejected_mean=('rejected_opens','mean'),worst_month_mean=('worst_month_pct','mean'),negative_months_mean=('negative_months','mean')).reset_index()
    A.to_csv(OUT/'summary_aggregate.csv',index=False); print('\nAGG\n'+A.to_string(index=False),flush=True)


if __name__=="__main__":
    main()
