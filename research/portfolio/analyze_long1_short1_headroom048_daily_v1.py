from pathlib import Path
import pandas as pd
import numpy as np

ROOT=Path('/home/kasm920/binance1-pro')
NEW=ROOT/'research/results/LONG1_SHORT1_HEADROOM048_6SEED_20261022'
BASE=ROOT/'research/results/LONG1_SHORT1_CENTRAL_RISK_MTM_V4_MARKED_EXPOSURE_20261022'
OUT=ROOT/'research/results/LONG1_SHORT1_HEADROOM048_DAILY_AUDIT_20261022'
OUT.mkdir(parents=True,exist_ok=True)
SC='MTM_DD12_R06_SHORTV50_MARKED_H048'
BASE_SC='MTM_DD12_R06_SHORTV50_MARKED'

def load_period(root,sc,label):
    parts=[]
    for seed in range(1,7):
        p=root/f'{sc}_seed{seed}_{label}.csv'
        d=pd.read_csv(p); d['seed']=seed; parts.append(d)
    return pd.concat(parts,ignore_index=True)

def agg_period(d):
    return d.groupby('period').agg(
        return_mean=('return_pct','mean'),return_min=('return_pct','min'),return_max=('return_pct','max'),
        dd_mean=('intraperiod_dd_pct','mean'),dd_worst=('intraperiod_dd_pct','min'),
        global_dd_worst=('global_dd_min_pct','min'),realized_pnl_mean=('realized_pnl','mean'),
        closed_mean=('closed','mean'),pf_mean=('pf','mean'),
        positive_seeds=('return_pct',lambda x:int((x>0).sum())),negative_seeds=('return_pct',lambda x:int((x<0).sum()))
    ).reset_index()

def load_closes():
    parts=[]
    for seed in range(1,7):
        p=NEW/f'{SC}_seed{seed}_closes.csv'
        d=pd.read_csv(p); d['seed']=seed; d['ts']=pd.to_datetime(d['ts'],utc=True); d['period']=d.ts.dt.strftime('%Y-%m-%d'); parts.append(d)
    return pd.concat(parts,ignore_index=True)

def main():
    daily=load_period(NEW,SC,'daily'); month=load_period(NEW,SC,'monthly')
    base_daily=load_period(BASE,BASE_SC,'daily')
    da=agg_period(daily); ma=agg_period(month)
    closes=load_closes()
    contrib=closes.groupby(['period','strategy_id']).pnl_net.sum().unstack(fill_value=0)/6.0
    contrib=contrib.rename(columns={'LONG1':'long1_pnl_mean','SHORT1':'short1_pnl_mean'}).reset_index()
    da=da.merge(contrib,on='period',how='left')
    da[['long1_pnl_mean','short1_pnl_mean']]=da[['long1_pnl_mean','short1_pnl_mean']].fillna(0.0)
    neg=da[da.return_mean<0].sort_values('return_mean').copy()
    neg['dominant_loss']=np.where(neg.long1_pnl_mean<neg.short1_pnl_mean,'LONG1','SHORT1')
    neg.to_csv(OUT/'negative_days_all.csv',index=False); da.to_csv(OUT/'daily_aggregate.csv',index=False); ma.to_csv(OUT/'monthly_aggregate.csv',index=False)

    # per-negative-day close reason attribution averaged per seed
    neg_dates=set(neg.period)
    rc=closes[closes.period.isin(neg_dates)].groupby(['period','strategy_id','reason']).agg(
        pnl_total=('pnl_net','sum'),closes=('pnl_net','size'),wins=('pnl_net',lambda x:int((x>0).sum())),losses=('pnl_net',lambda x:int((x<0).sum()))
    ).reset_index(); rc['pnl_mean_per_seed']=rc.pnl_total/6.0; rc['closes_mean_per_seed']=rc.closes/6.0
    rc.to_csv(OUT/'negative_days_reason_attribution.csv',index=False)

    # baseline comparison
    ba=agg_period(base_daily)[['period','return_mean','dd_worst']].rename(columns={'return_mean':'base_return_mean','dd_worst':'base_dd_worst'})
    cmp=da.merge(ba,on='period',how='left'); cmp['return_delta_pp']=cmp.return_mean-cmp.base_return_mean; cmp['dd_delta_pp']=cmp.dd_worst-cmp.base_dd_worst
    cmp.to_csv(OUT/'daily_vs_marked_h050.csv',index=False)

    summary={
      'days':len(da),'positive_days':int((da.return_mean>0).sum()),'negative_days':int((da.return_mean<0).sum()),'flat_days':int((da.return_mean==0).sum()),
      'mean_daily_return_pct':float(da.return_mean.mean()),'median_daily_return_pct':float(da.return_mean.median()),'p05_daily_return_pct':float(da.return_mean.quantile(.05)),
      'worst_day_pct':float(da.return_mean.min()),'best_day_pct':float(da.return_mean.max()),
      'days_le_minus1':int((da.return_mean<=-1).sum()),'days_le_minus2':int((da.return_mean<=-2).sum()),'days_le_minus3':int((da.return_mean<=-3).sum()),'days_le_minus5':int((da.return_mean<=-5).sum()),
      'negative_days_short_dominant':int((neg.dominant_loss=='SHORT1').sum()),'negative_days_long_dominant':int((neg.dominant_loss=='LONG1').sum()),
      'months':len(ma),'positive_months':int((ma.return_mean>0).sum()),'negative_months':int((ma.return_mean<0).sum()),'mean_month_return_pct':float(ma.return_mean.mean()),'median_month_return_pct':float(ma.return_mean.median())
    }
    pd.DataFrame([summary]).to_csv(OUT/'summary.csv',index=False)
    print('SUMMARY',summary)
    print('\nWORST_25\n'+neg.head(25)[['period','return_mean','return_min','return_max','dd_worst','positive_seeds','negative_seeds','long1_pnl_mean','short1_pnl_mean','dominant_loss']].to_string(index=False))
    print('\nMONTHLY\n'+ma[['period','return_mean','return_min','return_max','dd_worst','pf_mean','positive_seeds','negative_seeds']].to_string(index=False))
    print('\nIMPROVEMENT_COUNTS',{'days_better':int((cmp.return_delta_pp>1e-12).sum()),'days_worse':int((cmp.return_delta_pp<-1e-12).sum()),'days_same':int((cmp.return_delta_pp.abs()<=1e-12).sum()),'mean_delta_pp':float(cmp.return_delta_pp.mean())})

if __name__=='__main__': main()
