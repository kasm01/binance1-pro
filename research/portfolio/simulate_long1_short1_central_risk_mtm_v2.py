from pathlib import Path
import sys, json
import pandas as pd
import numpy as np

ROOT=Path('/home/kasm920/binance1-pro')
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from orchestration.risk.central_risk_master import CentralRiskConfig, CentralRiskMaster, PortfolioRiskState, PositionExposure, EntryRiskRequest

LONG_DIR=ROOT/'research/results/LONG1_SINGLE_F60_020_POSITIONS_20261021'
SHORT_DIR=Path('/home/kasm920/binance1/research/short/results/SHORT1_V49B_TRADE_CONFIRM/V49B_R70_W2')
SHORT_1M=Path('/home/kasm920/binance1/research/short/data/inj_1m')
OUT=ROOT/'research/results/LONG1_SHORT1_CENTRAL_RISK_MTM_V2_20261021'
OUT.mkdir(parents=True,exist_ok=True)
FEE=0.0004
BUDGET=0.50

def _dt(s): return pd.to_datetime(s,utc=True,format='mixed')
def risk_stop(reason):
    r=str(reason or '').lower()
    return any(x in r for x in ('stop','sl','cat'))

def load_prices():
    parts=[]
    for fp in [ROOT/'data/offline_cache/NEARUSDT_1m_360d.csv', ROOT/'research/data/NEARUSDT_1m_1month.csv']:
        d=pd.read_csv(fp,usecols=lambda c:c in ('open_time','close'))
        parts.append(d)
    n=pd.concat(parts,ignore_index=True).drop_duplicates('open_time').sort_values('open_time')
    n['mark_ts']=pd.to_datetime(n.open_time,unit='ms',utc=True)+pd.Timedelta(minutes=1)
    n['close']=pd.to_numeric(n.close,errors='coerce')
    n=n[['mark_ts','close']].dropna().rename(columns={'close':'near_close'})
    parts=[]
    for fp in sorted(SHORT_1M.glob('*.csv')):
        d=pd.read_csv(fp,usecols=lambda c:c in ('open_time','close'))
        parts.append(d)
    x=pd.concat(parts,ignore_index=True).drop_duplicates('open_time').sort_values('open_time')
    x['mark_ts']=pd.to_datetime(x.open_time,unit='ms',utc=True)+pd.Timedelta(minutes=1)
    x['close']=pd.to_numeric(x.close,errors='coerce')
    x=x[['mark_ts','close']].dropna().rename(columns={'close':'inj_close'})
    p=n.merge(x,on='mark_ts',how='inner').sort_values('mark_ts').reset_index(drop=True)
    return p

def load_short():
    e=pd.read_csv(SHORT_DIR/'entries.csv'); c=pd.read_csv(SHORT_DIR/'closed_positions.csv'); q=pd.read_csv(SHORT_DIR/'equity_curve.csv')
    e['ts']=_dt(e.ts); c['open_ts']=_dt(c.open_ts); c['close_ts']=_dt(c.close_ts); q['ts']=_dt(q.ts)
    e=e[e.layer==1].copy()
    m=c.merge(e[['ts','notional','price']],left_on='open_ts',right_on='ts',how='left',validate='one_to_one')
    m=m.merge(q[['ts','equity','sizing_mode']],left_on='open_ts',right_on='ts',how='left',validate='one_to_one')
    sm=m.sizing_mode.map({'NORMAL':1.0,'RECOVERY':0.7,'REDUCED':0.5})
    implied=m.notional/(m.equity*sm)
    m['context_mult']=np.where(implied<0.75,0.5,1.0)
    m['source_notional']=pd.to_numeric(m.notional,errors='coerce')
    m['entry_price']=pd.to_numeric(m.price,errors='coerce')
    m['unit_net_return']=pd.to_numeric(m.pnl_net,errors='coerce')/m.source_notional
    m['strategy_id']='SHORT1'; m['symbol']='INJUSDT'; m['side']='short'
    return m[['open_ts','close_ts','strategy_id','symbol','side','context_mult','source_notional','entry_price','unit_net_return','reason']].sort_values('open_ts').reset_index(drop=True)

def load_long(seed):
    m=pd.read_csv(LONG_DIR/f'seed{seed}.csv')
    m['open_ts']=_dt(m.entry_ts); m['close_ts']=_dt(m.exit_ts)
    m['source_notional']=pd.to_numeric(m.notional,errors='coerce')
    m['entry_price']=pd.to_numeric(m.entry_price,errors='coerce')
    m['unit_net_return']=pd.to_numeric(m.net,errors='coerce')/m.source_notional
    m['context_mult']=1.0; m['strategy_id']='LONG1'; m['symbol']='NEARUSDT'; m['side']='long'
    return m[['open_ts','close_ts','strategy_id','symbol','side','context_mult','source_notional','entry_price','unit_net_return','reason']].sort_values('open_ts').reset_index(drop=True)

def local_dd_pct(vals):
    a=np.asarray(vals,float)
    if len(a)==0: return np.nan
    p=np.maximum.accumulate(a)
    return float(np.min(a/p-1.0)*100.0)

def aggregate_period(curve, closes, freq):
    c=curve.copy()
    if freq=='D': c['period']=c.ts.dt.strftime('%Y-%m-%d')
    elif freq=='W':
        iso=c.ts.dt.isocalendar(); c['period']=iso.year.astype(str)+'-W'+iso.week.astype(str).str.zfill(2)
    else: c['period']=c.ts.dt.strftime('%Y-%m')
    z=closes.copy()
    if len(z):
        if freq=='D': z['period']=z.ts.dt.strftime('%Y-%m-%d')
        elif freq=='W':
            iso=z.ts.dt.isocalendar(); z['period']=iso.year.astype(str)+'-W'+iso.week.astype(str).str.zfill(2)
        else: z['period']=z.ts.dt.strftime('%Y-%m')
    rows=[]; prev_end=None
    for period,g in c.groupby('period',sort=True):
        g=g.sort_values('ts'); start=float(g.mtm.iloc[0] if prev_end is None else prev_end); end=float(g.mtm.iloc[-1]); prev_end=end
        x=z[z.period==period] if len(z) else z
        pnl=x.pnl_net.sum() if len(x) else 0.0
        gp=x.loc[x.pnl_net>0,'pnl_net'].sum() if len(x) else 0.0
        gl=-x.loc[x.pnl_net<0,'pnl_net'].sum() if len(x) else 0.0
        rows.append({
            'period':period,'start_equity':start,'end_equity':end,'return_pct':100*(end/start-1) if start>0 else np.nan,
            'intraperiod_dd_pct':local_dd_pct(g.mtm),'global_dd_min_pct':float(g.global_dd_pct.min()),
            'mtm_min':float(g.mtm.min()),'mtm_max':float(g.mtm.max()),
            'gross_avg_ratio':float(g.gross_ratio.mean()),'gross_max_ratio':float(g.gross_ratio.max()),
            'abs_net_avg_ratio':float(g.abs_net_ratio.mean()),'abs_net_max_ratio':float(g.abs_net_ratio.max()),
            'open_pos_avg':float(g.open_positions.mean()),'open_pos_max':int(g.open_positions.max()),
            'normal_minutes':int((g['mode']=='NORMAL').sum()),'recovery_minutes':int((g['mode']=='RECOVERY').sum()),'reduced_minutes':int((g['mode']=='REDUCED').sum()),
            'closed':int(len(x)),'wins':int((x.pnl_net>0).sum()) if len(x) else 0,'losses':int((x.pnl_net<0).sum()) if len(x) else 0,
            'realized_pnl':float(pnl),'pf':float(gp/gl) if gl>0 else np.nan,
        })
    return pd.DataFrame(rows)

def mark_state(state, mtm, cfg):
    peak=max(float(state.equity_peak),float(mtm)); mode=state.normalized_mode(); wins=int(state.recovery_successes); changed=False; reason='state_unchanged'
    dd=(float(mtm)/peak-1.0) if peak>0 else 0.0
    if mode=='NORMAL' and dd<=-abs(cfg.dd_reduce_trigger): mode='REDUCED'; wins=0; changed=True; reason='mtm_dd_enter_reduced'
    elif mode=='REDUCED' and dd>=-abs(cfg.dd_recover_trigger): mode='RECOVERY'; wins=0; changed=True; reason='mtm_dd_enter_recovery'
    elif mode=='RECOVERY' and dd<=-abs(cfg.dd_reduce_trigger): mode='REDUCED'; wins=0; changed=True; reason='mtm_recovery_relapse'
    return PortfolioRiskState(peak,mode,wins),changed,reason

def run(seed,name,cfg,use_state=True,prices=None):
    L=load_long(seed); S=load_short(); T=pd.concat([L,S],ignore_index=True).sort_values('open_ts').reset_index(drop=True)
    start=max(L.open_ts.min(),S.open_ts.min()); end=min(L.close_ts.max(),S.close_ts.max())
    T=T[(T.open_ts>=start)&(T.open_ts<=end)].copy().reset_index(drop=True)
    T['trade_id']=[f'{r.strategy_id}:{i}' for i,r in T.iterrows()]
    ev=[]
    for r in T.itertuples(index=False):
        ev.append((r.open_ts,1,'OPEN',r)); ev.append((r.close_ts,0,'CLOSE',r))
    ev.sort(key=lambda x:(x[0],x[1])); ep=0
    P=prices[(prices.mark_ts>=start.floor('min'))&(prices.mark_ts<=end.ceil('min'))].copy().reset_index(drop=True)
    rm=CentralRiskMaster(cfg); state=PortfolioRiskState(1000.0,'NORMAL',0)
    realized=1000.0; mtm=1000.0; peak_mtm=1000.0; openp={}; curves=[]; closes=[]; cap_limited=rejected=state_changes=0
    near_px=inj_px=np.nan
    def current_mtm():
        u=0.0
        for z in openp.values():
            px=near_px if z['side']=='long' else inj_px
            if not np.isfinite(px): continue
            er=(px/z['entry_price']-1.0) if z['side']=='long' else (1.0-px/z['entry_price'])
            u += z['notional']*er
        return realized+u
    for mr in P.itertuples(index=False):
        mark_ts=mr.mark_ts
        while ep<len(ev) and ev[ep][0] <= mark_ts:
            ts,_,kind,r=ev[ep]; ep+=1; tid=r.trade_id
            if kind=='CLOSE':
                z=openp.pop(tid,None)
                if z is None: continue
                open_fee_src=float(r.source_notional)*FEE
                close_increment_unit=float(r.unit_net_return)+FEE
                inc=z['notional']*close_increment_unit
                realized += inc
                pnl_total=z['notional']*float(r.unit_net_return)
                prev_mode=state.mode
                if use_state and state.mode=='RECOVERY':
                    if risk_stop(r.reason): state=PortfolioRiskState(state.equity_peak,'REDUCED',0)
                    elif z['opened_mode']=='RECOVERY' and pnl_total>0:
                        wins=state.recovery_successes+1
                        state=PortfolioRiskState(state.equity_peak,'NORMAL' if wins>=cfg.recovery_successes_required else 'RECOVERY',0 if wins>=cfg.recovery_successes_required else wins)
                if state.mode!=prev_mode: state_changes+=1
                closes.append({'ts':ts,'trade_id':tid,'strategy_id':r.strategy_id,'pnl_net':pnl_total,'reason':r.reason,'opened_mode':z['opened_mode']})
            else:
                eq_for_risk=max(1e-9,float(current_mtm()))
                positions=[z['exposure'] for z in openp.values()]
                req=EntryRiskRequest(r.strategy_id,r.symbol,r.side,eq_for_risk*BUDGET,float(r.context_mult))
                eval_state=state if use_state else PortfolioRiskState(state.equity_peak,'NORMAL',0)
                d=rm.evaluate_entry(request=req,state=eval_state,portfolio_equity=eq_for_risk,positions=positions)
                if d.allowed_notional<=0: rejected+=1; continue
                if d.allowed_notional < d.risk_scaled_notional-1e-9: cap_limited+=1
                realized -= d.allowed_notional*FEE
                ex=PositionExposure(r.strategy_id,r.symbol,r.side,d.allowed_notional,eval_state.normalized_mode())
                openp[tid]={'exposure':ex,'notional':float(d.allowed_notional),'side':r.side,'entry_price':float(r.entry_price),'opened_mode':eval_state.normalized_mode()}
        near_px=float(mr.near_close); inj_px=float(mr.inj_close); mtm=float(current_mtm()); peak_mtm=max(peak_mtm,mtm)
        if use_state:
            prev=state.mode; state,changed,_=mark_state(state,mtm,cfg)
            if changed and state.mode!=prev: state_changes+=1
        else: state=PortfolioRiskState(max(state.equity_peak,mtm),'NORMAL',0)
        gross=sum(z['notional'] for z in openp.values()); lng=sum(z['notional'] for z in openp.values() if z['side']=='long'); sht=sum(z['notional'] for z in openp.values() if z['side']=='short')
        curves.append({'ts':mark_ts,'realized':realized,'mtm':mtm,'mode':state.mode,'gross_notional':gross,'net_notional':lng-sht,'gross_ratio':gross/max(mtm,1e-9),'abs_net_ratio':abs(lng-sht)/max(mtm,1e-9),'open_positions':len(openp),'global_dd_pct':100*(mtm/peak_mtm-1.0)})
    C=pd.DataFrame(curves); X=pd.DataFrame(closes)
    gp=X.loc[X.pnl_net>0,'pnl_net'].sum() if len(X) else 0.; gl=-X.loc[X.pnl_net<0,'pnl_net'].sum() if len(X) else 0.
    summary={'scenario':name,'seed':seed,'return_pct':100*(C.mtm.iloc[-1]/1000-1),'pf':gp/max(gl,1e-12),'mtm_dd_pct':float(C.global_dd_pct.min()),'realized_dd_pct':local_dd_pct(C.realized),'cap_limited_opens':cap_limited,'rejected_opens':rejected,'state_changes':state_changes,'closed':len(X),'gross_max_ratio':float(C.gross_ratio.max()),'abs_net_max_ratio':float(C.abs_net_ratio.max()),'reduced_minutes':int((C['mode']=='REDUCED').sum()),'recovery_minutes':int((C['mode']=='RECOVERY').sum())}
    base=OUT/f'{name}_seed{seed}'; C.to_csv(str(base)+'_curve.csv',index=False); X.to_csv(str(base)+'_closes.csv',index=False)
    for freq,label in [('D','daily'),('W','weekly'),('M','monthly')]: aggregate_period(C,X,freq).to_csv(str(base)+f'_{label}.csv',index=False)
    return summary

def aggregate_across_seeds(name,label):
    fs=sorted(OUT.glob(f'{name}_seed*_{label}.csv'))
    parts=[]
    for fp in fs:
        seed=int(fp.stem.split('_seed')[1].split('_')[0]); d=pd.read_csv(fp); d['seed']=seed; parts.append(d)
    d=pd.concat(parts,ignore_index=True)
    a=d.groupby('period').agg(
        return_mean=('return_pct','mean'),return_min=('return_pct','min'),return_max=('return_pct','max'),
        dd_mean=('intraperiod_dd_pct','mean'),dd_worst=('intraperiod_dd_pct','min'),global_dd_worst=('global_dd_min_pct','min'),
        realized_pnl_mean=('realized_pnl','mean'),closed_mean=('closed','mean'),pf_mean=('pf','mean'),
        gross_avg_ratio_mean=('gross_avg_ratio','mean'),gross_max_ratio_max=('gross_max_ratio','max'),
        abs_net_avg_ratio_mean=('abs_net_avg_ratio','mean'),abs_net_max_ratio_max=('abs_net_max_ratio','max'),
        reduced_minutes_mean=('reduced_minutes','mean'),recovery_minutes_mean=('recovery_minutes','mean')
    ).reset_index()
    a.to_csv(OUT/f'{name}_{label}_aggregate.csv',index=False)
    return a

def main():
    prices=load_prices(); print('PRICE_ROWS',len(prices),prices.mark_ts.min(),prices.mark_ts.max(),flush=True)
    scenarios=[
        ('STATIC_MTM',False,CentralRiskConfig(normal_multiplier=1,recovery_multiplier=1,reduced_multiplier=1,max_open_positions=2,max_gross_exposure_ratio=1.0,max_long_exposure_ratio=.5,max_short_exposure_ratio=.5,max_abs_net_exposure_ratio=.5,max_symbol_exposure_ratio=.5)),
        ('MTM_DD08_R04',True,CentralRiskConfig(dd_reduce_trigger=.08,dd_recover_trigger=.04,max_open_positions=2,max_gross_exposure_ratio=1.0,max_long_exposure_ratio=.5,max_short_exposure_ratio=.5,max_abs_net_exposure_ratio=.5,max_symbol_exposure_ratio=.5)),
        ('MTM_DD10_R05',True,CentralRiskConfig(dd_reduce_trigger=.10,dd_recover_trigger=.05,max_open_positions=2,max_gross_exposure_ratio=1.0,max_long_exposure_ratio=.5,max_short_exposure_ratio=.5,max_abs_net_exposure_ratio=.5,max_symbol_exposure_ratio=.5)),
        ('MTM_DD12_R06',True,CentralRiskConfig(dd_reduce_trigger=.12,dd_recover_trigger=.06,max_open_positions=2,max_gross_exposure_ratio=1.0,max_long_exposure_ratio=.5,max_short_exposure_ratio=.5,max_abs_net_exposure_ratio=.5,max_symbol_exposure_ratio=.5)),
        ('MTM_DD14_R07',True,CentralRiskConfig(dd_reduce_trigger=.14,dd_recover_trigger=.07,max_open_positions=2,max_gross_exposure_ratio=1.0,max_long_exposure_ratio=.5,max_short_exposure_ratio=.5,max_abs_net_exposure_ratio=.5,max_symbol_exposure_ratio=.5)),
    ]
    rows=[]
    for name,use,cfg in scenarios:
        for seed in range(1,7):
            s=run(seed,name,cfg,use_state=use,prices=prices); rows.append(s); print('RESULT',s,flush=True)
        for label in ('daily','weekly','monthly'): aggregate_across_seeds(name,label)
    R=pd.DataFrame(rows); R.to_csv(OUT/'summary_by_seed.csv',index=False)
    A=R.groupby('scenario').agg(return_mean=('return_pct','mean'),return_min=('return_pct','min'),return_max=('return_pct','max'),pf_mean=('pf','mean'),mtm_dd_mean=('mtm_dd_pct','mean'),mtm_dd_worst=('mtm_dd_pct','min'),realized_dd_mean=('realized_dd_pct','mean'),cap_limited_mean=('cap_limited_opens','mean'),rejected_mean=('rejected_opens','mean'),state_changes_mean=('state_changes','mean'),gross_max=('gross_max_ratio','max'),abs_net_max=('abs_net_max_ratio','max'),reduced_minutes_mean=('reduced_minutes','mean'),recovery_minutes_mean=('recovery_minutes','mean')).reset_index()
    A.to_csv(OUT/'summary_aggregate.csv',index=False); print('\nAGG\n'+A.to_string(index=False),flush=True)
    # compact critical-month extraction for the user-requested review
    crit=[]
    for name,_,_ in scenarios:
        m=pd.read_csv(OUT/f'{name}_monthly_aggregate.csv')
        for month in ('2026-04','2026-05','2026-07','2026-09'):
            x=m[m.period==month]
            if len(x): crit.append({'scenario':name,**x.iloc[0].to_dict()})
    pd.DataFrame(crit).to_csv(OUT/'critical_months_apr_may_jul_sep.csv',index=False)

if __name__=='__main__': main()
