#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
P=Path('/home/kasm920/binance1-pro'); S=Path('/home/kasm920/binance1')
OUT=P/'research/results/STOP_REVALIDATION_V1_20261022'; OUT.mkdir(parents=True,exist_ok=True)

def load_1m(paths):
    ds=[]
    for fp in paths:
        d=pd.read_csv(fp)
        d['ts']=pd.to_datetime(d.open_time,unit='ms',utc=True)
        ren={'quote_asset_volume':'quote_volume','taker_buy_quote_volume':'taker_buy_quote_volume'}
        d=d.rename(columns=ren)
        for c in ['open','high','low','close','quote_volume','taker_buy_quote_volume']:
            d[c]=pd.to_numeric(d[c],errors='coerce')
        ds.append(d[['ts','open','high','low','close','quote_volume','taker_buy_quote_volume']])
    d=pd.concat(ds).sort_values('ts').drop_duplicates('ts').reset_index(drop=True)
    sell=d.quote_volume-d.taker_buy_quote_volume; net=d.taker_buy_quote_volume-sell
    d['flow15']=net.rolling(15,min_periods=15).sum()/d.quote_volume.rolling(15,min_periods=15).sum()
    d['flow60']=net.rolling(60,min_periods=60).sum()/d.quote_volume.rolling(60,min_periods=60).sum()
    d['ret5']=d.close.pct_change(5); d['ret15']=d.close.pct_change(15)
    d['prev_red']=(d.close<d.open).astype(int); d['prev_green']=(d.close>d.open).astype(int)
    for c in ['flow15','flow60','ret5','ret15','prev_red','prev_green']:
        d[c+'_c']=d[c].shift(1)
    return d

def add_short_oi(d):
    fp=S/'research/short/data/INJUSDT_metrics_5m_20251012_20261013.csv'
    m=pd.read_csv(fp); m['oi_ts']=pd.to_datetime(m.create_time,utc=True,format='mixed')
    m=m.sort_values('oi_ts'); m['oi15']=pd.to_numeric(m.sum_open_interest,errors='coerce').pct_change(3)
    x=d.copy(); x['lookup']=x.ts-pd.Timedelta(nanoseconds=1)
    x=pd.merge_asof(x.sort_values('lookup'),m[['oi_ts','oi15']],left_on='lookup',right_on='oi_ts',direction='backward',tolerance=pd.Timedelta('5m'))
    return x.sort_values('ts').reset_index(drop=True)

def label_path(d, close_ts, entry, side, catastrophic, horizon_min=480):
    w=d[(d.ts>close_ts)&(d.ts<=close_ts+pd.Timedelta(minutes=horizon_min))]
    if len(w)==0:return (0,np.nan,np.nan,'none')
    for r in w.itertuples(index=False):
        if side=='long':
            recovery=float(r.high)>=entry; catastrophe=float(r.low)<=entry*(1-catastrophic)
        else:
            recovery=float(r.low)<=entry; catastrophe=float(r.high)>=entry*(1+catastrophic)
        if recovery and catastrophe: return (0,np.nan,(r.ts-close_ts).total_seconds()/60,'ambiguous_same_bar')
        if recovery: return (1,(r.ts-close_ts).total_seconds()/60,np.nan,'recover')
        if catastrophe: return (0,np.nan,(r.ts-close_ts).total_seconds()/60,'catastrophe')
    return (0,np.nan,np.nan,'timeout')

def build_long(d):
    t=pd.read_csv(P/'research/results/LONG1_SINGLE_F60_020_POSITIONS_20261021/seed1.csv')
    t['open_ts']=pd.to_datetime(t.entry_ts,utc=True,format='mixed'); t['close_ts']=pd.to_datetime(t.exit_ts,utc=True,format='mixed')
    t=t[t.reason.eq('sl')].copy(); rows=[]
    dm=d.set_index('ts')
    for r in t.itertuples(index=False):
        k=r.close_ts.floor('min'); hist=d[d.ts<=k].tail(2)
        if len(hist)<2:continue
        q=hist.iloc[-1]; rec,rt,ct,out=label_path(d,k,float(r.entry_price),'long',.035)
        rows.append(dict(strategy='LONG1',open_ts=r.open_ts,stop_ts=k,entry=float(r.entry_price),age_min=(k-r.open_ts).total_seconds()/60,label=rec,recovery_min=rt,cat_min=ct,outcome=out,flow15=q.flow15_c,flow60=q.flow60_c,ret5=q.ret5_c,ret15=q.ret15_c,prev_red=q.prev_red_c,prev_green=q.prev_green_c,oi15=np.nan))
    return pd.DataFrame(rows)

def build_short(d):
    ent=pd.read_csv(S/'research/short/results/SHORT1_V49B_TRADE_CONFIRM/V49B_R70_W2/entries.csv'); ent['open_ts']=pd.to_datetime(ent.ts,utc=True,format='mixed')
    c=pd.read_csv(S/'research/short/results/SHORT1_V49B_TRADE_CONFIRM/V49B_R70_W2/closed_positions.csv'); c['open_ts']=pd.to_datetime(c.open_ts,utc=True,format='mixed'); c['stop_ts']=pd.to_datetime(c.close_ts,utc=True,format='mixed')
    c=c[c.reason.eq('soft_stop_1m_confirm')].copy(); e=ent.set_index('open_ts'); rows=[]
    for r in c.itertuples(index=False):
        if r.open_ts not in e.index: continue
        er=e.loc[r.open_ts]; er=er.iloc[0] if isinstance(er,pd.DataFrame) else er; entry=float(er.price)
        k=r.stop_ts.floor('min'); hist=d[d.ts<=k].tail(2)
        if len(hist)<2:continue
        q=hist.iloc[-1]; rec,rt,ct,out=label_path(d,k,entry,'short',.06)
        rows.append(dict(strategy='SHORT1',open_ts=r.open_ts,stop_ts=k,entry=entry,age_min=(k-r.open_ts).total_seconds()/60,label=rec,recovery_min=rt,cat_min=ct,outcome=out,flow15=q.flow15_c,flow60=q.flow60_c,ret5=q.ret5_c,ret15=q.ret15_c,prev_red=q.prev_red_c,prev_green=q.prev_green_c,oi15=q.oi15))
    return pd.DataFrame(rows)

def audit(x):
    print('\n',x.strategy.iloc[0],'N',len(x),'RECOVER_BEFORE_CATA',round(100*x.label.mean(),2),'outcomes',x.outcome.value_counts().to_dict())
    cols=['age_min','flow15','flow60','ret5','ret15','oi15']
    print(x.groupby('label')[cols].median(numeric_only=True).T.to_string())
    # predeclared interpretable rules; no threshold grid
    if x.strategy.iloc[0]=='SHORT1':
        rules={
          'AGE<=120':x.age_min<=120,
          'FLOW15<=0':x.flow15<=0,
          'RET5<=0':x.ret5<=0,
          'RED_CANDLE':x.prev_red==1,
          'AGE120_AND_FLOW15_NEG':(x.age_min<=120)&(x.flow15<=0),
          'AGE120_AND_RET5_NEG':(x.age_min<=120)&(x.ret5<=0),
          '2OF3':((x.age_min<=120).astype(int)+(x.flow15<=0).astype(int)+(x.ret5<=0).astype(int))>=2,
        }
    else:
        rules={
          'AGE<=120':x.age_min<=120,
          'FLOW15>=0':x.flow15>=0,
          'RET5>=0':x.ret5>=0,
          'GREEN_CANDLE':x.prev_green==1,
          'AGE120_AND_FLOW15_POS':(x.age_min<=120)&(x.flow15>=0),
          'AGE120_AND_RET5_POS':(x.age_min<=120)&(x.ret5>=0),
          '2OF3':((x.age_min<=120).astype(int)+(x.flow15>=0).astype(int)+(x.ret5>=0).astype(int))>=2,
        }
    rows=[]
    split=x.stop_ts.quantile(.65)
    for name,m in rules.items():
        for seg,mask in [('ALL',pd.Series(True,index=x.index)),('EARLY',x.stop_ts<=split),('LATE',x.stop_ts>split)]:
            z=x[m&mask]; base=x[mask]
            rows.append(dict(strategy=x.strategy.iloc[0],rule=name,segment=seg,n=len(z),coverage=len(z)/max(len(base),1),precision=z.label.mean() if len(z) else np.nan,base_rate=base.label.mean() if len(base) else np.nan,lift=(z.label.mean()/base.label.mean()) if len(z) and base.label.mean()>0 else np.nan))
    R=pd.DataFrame(rows); print(R.to_string(index=False)); return R

def main():
    near=load_1m([P/'data/offline_cache/NEARUSDT_1m_360d.csv',P/'research/data/NEARUSDT_1m_1month.csv'])
    inj=load_1m(sorted((S/'research/short/data/inj_1m').glob('*.csv'))); inj=add_short_oi(inj)
    L=build_long(near); H=build_short(inj); X=pd.concat([L,H],ignore_index=True); X.to_csv(OUT/'stop_events_features.csv',index=False)
    R=pd.concat([audit(L),audit(H)],ignore_index=True); R.to_csv(OUT/'rule_audit.csv',index=False)
if __name__=='__main__': main()
