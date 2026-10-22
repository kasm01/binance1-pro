from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path('/home/kasm920/binance1-pro')
D=ROOT/'research/results/LONG1_SHORT1_CENTRAL_RISK_MTM_V4_MARKED_EXPOSURE_20261022'
OUT=ROOT/'research/results/LONG1_SHORT1_DAILY_MONTHLY_DEEP_V5_MARKED_20261022'
OUT.mkdir(parents=True,exist_ok=True)
SC='MTM_DD12_R06_SHORTV50_MARKED'
BASE='MTM_DD12_R06_BASESHORT_MARKED'
SEEDS=range(1,7)

def load_period(scenario,freq):
    return pd.read_csv(D/f'{scenario}_{freq}_aggregate.csv')

def strategy_contrib(freq):
    rows=[]
    fmt='%Y-%m-%d' if freq=='daily' else '%Y-%m'
    for seed in SEEDS:
        c=pd.read_csv(D/f'{SC}_seed{seed}_closes.csv')
        c['ts']=pd.to_datetime(c.ts,utc=True)
        c['period']=c.ts.dt.strftime(fmt)
        for (p,sid),g in c.groupby(['period','strategy_id']):
            pnl=pd.to_numeric(g.pnl_net,errors='coerce').sum()
            wins=int((pd.to_numeric(g.pnl_net,errors='coerce')>0).sum())
            losses=int((pd.to_numeric(g.pnl_net,errors='coerce')<0).sum())
            stops=int(g.reason.astype(str).str.contains('stop|catastrophic',case=False,regex=True).sum())
            tps=int(g.reason.astype(str).str.contains('tp|giveback|stall',case=False,regex=True).sum())
            rows.append({'seed':seed,'period':p,'strategy_id':sid,'pnl_net':pnl,'closed':len(g),'wins':wins,'losses':losses,'stops':stops,'tp_like':tps})
    x=pd.DataFrame(rows)
    if x.empty:return x
    agg=x.groupby(['period','strategy_id']).agg(pnl_mean=('pnl_net','mean'),pnl_min=('pnl_net','min'),pnl_max=('pnl_net','max'),closed_mean=('closed','mean'),wins_mean=('wins','mean'),losses_mean=('losses','mean'),stops_mean=('stops','mean'),tp_like_mean=('tp_like','mean')).reset_index()
    return agg

def loss_streaks():
    ds=[]
    for seed in SEEDS:
        x=pd.read_csv(D/f'{SC}_seed{seed}_daily.csv')
        x['seed']=seed; ds.append(x[['seed','period','return_pct']])
    x=pd.concat(ds,ignore_index=True)
    rows=[]
    for seed,g in x.groupby('seed'):
        g=g.sort_values('period'); cur=[]; best=[]
        for r in g.itertuples(index=False):
            if float(r.return_pct)<0: cur.append((r.period,float(r.return_pct)))
            else:
                if len(cur)>len(best):best=cur[:]
                cur=[]
        if len(cur)>len(best):best=cur[:]
        rows.append({'seed':seed,'max_consecutive_losing_days':len(best),'streak_start':best[0][0] if best else None,'streak_end':best[-1][0] if best else None,'streak_compound_pct':(np.prod([1+r/100 for _,r in best])-1)*100 if best else 0.0})
    return pd.DataFrame(rows)

def drawdown_events():
    rows=[]
    for seed in SEEDS:
        q=pd.read_csv(D/f'{SC}_seed{seed}_curve.csv')
        q['ts']=pd.to_datetime(q.ts,utc=True)
        col='mtm_equity' if 'mtm_equity' in q.columns else ('mtm' if 'mtm' in q.columns else 'equity')
        a=pd.to_numeric(q[col],errors='coerce').to_numpy(float)
        pk=np.maximum.accumulate(a); dd=a/pk-1
        j=int(np.nanargmin(dd)); pidx=int(np.argmax(a[:j+1])); trough=a[j]
        rec=np.where(a[j:]>=a[pidx])[0]
        ridx=(j+int(rec[0])) if len(rec) else None
        rows.append({'seed':seed,'peak_ts':q.ts.iloc[pidx],'trough_ts':q.ts.iloc[j],'recovery_ts':q.ts.iloc[ridx] if ridx is not None else None,'max_dd_pct':float(dd[j]*100),'peak_equity':float(a[pidx]),'trough_equity':float(trough),'recovered':bool(ridx is not None),'recovery_days':float((q.ts.iloc[ridx]-q.ts.iloc[j]).total_seconds()/86400) if ridx is not None else np.nan})
    return pd.DataFrame(rows)

def period_seed_consistency(freq):
    frames=[]
    for seed in SEEDS:
        x=pd.read_csv(D/f'{SC}_seed{seed}_{freq}.csv'); x['seed']=seed; frames.append(x)
    x=pd.concat(frames,ignore_index=True)
    rows=[]
    for p,g in x.groupby('period'):
        r=pd.to_numeric(g.return_pct,errors='coerce')
        rows.append({'period':p,'positive_seeds':int((r>0).sum()),'negative_seeds':int((r<0).sum()),'flat_seeds':int((r==0).sum()),'return_mean':float(r.mean()),'return_min':float(r.min()),'return_max':float(r.max()),'return_std':float(r.std(ddof=0))})
    return pd.DataFrame(rows)

def main():
    daily=load_period(SC,'daily'); monthly=load_period(SC,'monthly')
    base_daily=load_period(BASE,'daily'); base_monthly=load_period(BASE,'monthly')
    dcon=strategy_contrib('daily'); mcon=strategy_contrib('monthly')
    dc=period_seed_consistency('daily'); mc=period_seed_consistency('monthly')
    # merge daily strategy contributions wide
    if len(dcon):
        dp=dcon.pivot(index='period',columns='strategy_id',values='pnl_mean').reset_index().rename_axis(None,axis=1)
        dp=dp.rename(columns={c:f'{c.lower()}_pnl_mean' for c in dp.columns if c!='period'})
        daily_detail=daily.merge(dc,on='period',suffixes=('','_seed')).merge(dp,on='period',how='left')
    else: daily_detail=daily.merge(dc,on='period',suffixes=('','_seed'))
    if len(mcon):
        mp=mcon.pivot(index='period',columns='strategy_id',values='pnl_mean').reset_index().rename_axis(None,axis=1)
        mp=mp.rename(columns={c:f'{c.lower()}_pnl_mean' for c in mp.columns if c!='period'})
        monthly_detail=monthly.merge(mc,on='period',suffixes=('','_seed')).merge(mp,on='period',how='left')
    else: monthly_detail=monthly.merge(mc,on='period',suffixes=('','_seed'))
    # base delta
    daily_delta=daily[['period','return_mean','dd_worst']].merge(base_daily[['period','return_mean','dd_worst']],on='period',suffixes=('_v50','_base'))
    daily_delta['return_delta_pp']=daily_delta.return_mean_v50-daily_delta.return_mean_base
    monthly_delta=monthly[['period','return_mean','dd_worst','pf_mean']].merge(base_monthly[['period','return_mean','dd_worst','pf_mean']],on='period',suffixes=('_v50','_base'))
    monthly_delta['return_delta_pp']=monthly_delta.return_mean_v50-monthly_delta.return_mean_base
    monthly_delta['dd_delta_pp']=monthly_delta.dd_worst_v50-monthly_delta.dd_worst_base
    # distributions
    r=daily.return_mean.astype(float)
    dist={'days':int(len(daily)),'positive_days':int((r>0).sum()),'negative_days':int((r<0).sum()),'flat_days':int((r==0).sum()),'positive_day_pct':float((r>0).mean()*100),'mean_daily_return_pct':float(r.mean()),'median_daily_return_pct':float(r.median()),'p05_daily_return_pct':float(r.quantile(.05)),'p01_daily_return_pct':float(r.quantile(.01)),'worst_day_pct':float(r.min()),'best_day_pct':float(r.max()),'days_le_minus1':int((r<=-1).sum()),'days_le_minus2':int((r<=-2).sum()),'days_le_minus3':int((r<=-3).sum()),'days_le_minus5':int((r<=-5).sum()),'days_dd_le_minus5':int((daily.dd_worst<=-5).sum()),'days_dd_le_minus8':int((daily.dd_worst<=-8).sum()),'days_dd_le_minus10':int((daily.dd_worst<=-10).sum())}
    mr=monthly.return_mean.astype(float)
    mdist={'months':int(len(monthly)),'positive_months':int((mr>0).sum()),'negative_months':int((mr<0).sum()),'mean_month_return_pct':float(mr.mean()),'median_month_return_pct':float(mr.median()),'worst_month_pct':float(mr.min()),'best_month_pct':float(mr.max()),'months_all_seeds_positive':int((mc.positive_seeds==6).sum()),'months_any_seed_negative':int((mc.negative_seeds>0).sum())}
    streak=loss_streaks(); dde=drawdown_events()
    worst=daily_detail.nsmallest(25,'return_mean'); best=daily_detail.nlargest(15,'return_mean')
    # save
    daily_detail.to_csv(OUT/'daily_detail.csv',index=False); monthly_detail.to_csv(OUT/'monthly_detail.csv',index=False); dcon.to_csv(OUT/'daily_strategy_contribution.csv',index=False); mcon.to_csv(OUT/'monthly_strategy_contribution.csv',index=False); daily_delta.to_csv(OUT/'daily_v50_vs_base_delta.csv',index=False); monthly_delta.to_csv(OUT/'monthly_v50_vs_base_delta.csv',index=False); worst.to_csv(OUT/'worst_25_days.csv',index=False); best.to_csv(OUT/'best_15_days.csv',index=False); streak.to_csv(OUT/'loss_streaks.csv',index=False); dde.to_csv(OUT/'drawdown_events.csv',index=False)
    summary={'daily_distribution':dist,'monthly_distribution':mdist,'loss_streak_mean':float(streak.max_consecutive_losing_days.mean()),'loss_streak_max':int(streak.max_consecutive_losing_days.max()),'drawdown_mean_pct':float(dde.max_dd_pct.mean()),'drawdown_worst_pct':float(dde.max_dd_pct.min())}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2,default=str))
    print('SUMMARY',json.dumps(summary,indent=2),flush=True)
    print('\nWORST_DAYS\n',worst[['period','return_mean','return_min','return_max','dd_worst','global_dd_worst','closed_mean','pf_mean','positive_seeds','negative_seeds','long1_pnl_mean','short1_pnl_mean']].head(15).to_string(index=False),flush=True)
    print('\nMONTHLY\n',monthly_detail[['period','return_mean','return_min','return_max','dd_worst','global_dd_worst','pf_mean','positive_seeds','negative_seeds','long1_pnl_mean','short1_pnl_mean']].to_string(index=False),flush=True)
    print('\nMONTHLY_DELTA_V50_BASE\n',monthly_delta.to_string(index=False),flush=True)
    print('\nDRAWDOWN_EVENTS\n',dde.to_string(index=False),flush=True)
    print('\nLOSS_STREAKS\n',streak.to_string(index=False),flush=True)
if __name__=='__main__':main()
