"""Read-only historical analysis of four user-selected MODEL LONG signals.
No execution; uses previously saved source snapshots + public closed 1m/3m/5m bars.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,requests,bisect
p=Path('research/results')
positions=json.loads((p/'LONG1_MODEL_LONG_NO_TIME_EXIT_FIRST_HIT_20261111_15.json').read_text())['result']['ALL_MODEL_LONGS']['hypothetical_trades']
peak=json.loads((p/'LONG1_NO_TIME_STOP_PREPEAK_8_TRADES_20261115.json').read_text())['results']
models=json.loads((p/'LONG1_TRUE_MODEL_LONG_REGIME_SHADOW_V1_20261111_15.json').read_text())['full_results']
selected=['2026-11-12T01:36','2026-11-14T17:06','2026-11-14T19:06','2026-11-14T23:57']
tr=timezone(timedelta(hours=3));utc=timezone.utc
begin=int(datetime(2026,11,11,22,tzinfo=utc).timestamp()*1000)
end=int(datetime(2026,11,15,1,tzinfo=utc).timestamp()*1000)
def download(tf,step):
    result=[];cursor=begin
    while cursor<end:
        r=requests.get('https://fapi.binance.com/fapi/v1/klines',
            params=dict(symbol='NEARUSDT',interval=tf,startTime=cursor,endTime=end-1,limit=1000),timeout=12)
        r.raise_for_status();v=r.json()
        if not isinstance(v,list):raise ValueError(str(v)[:80])
        if not v:break
        result.extend(v);n=int(v[-1][0])+step
        if n<=cursor:raise RuntimeError('cursor')
        cursor=n
    z={int(a[6]):dict(close_ms=int(a[6]),o=float(a[1]),h=float(a[2]),l=float(a[3]),c=float(a[4]),vol=float(a[5])) for a in result}
    return sorted(z.values(),key=lambda a:a['close_ms'])
bars={k:download(k,s) for k,s in [('1m',60000),('3m',180000),('5m',300000)]}
tmap={tf:[z['close_ms'] for z in rows] for tf,rows in bars.items()}
def prior(tf,ms,n):
 i=bisect.bisect_left(tmap[tf],ms)
 return bars[tf][max(0,i-n):i]
def pct(price,base):return round((price/base-1)*300,4)
rows=[]
for start in selected:
 trade=next(z for z in positions if z['signal_time_tr'].startswith(start))
 pk=next(z for z in peak if z['signal_time_tr'].startswith(start))
 model=next(z for z in models if z['ts_tr'].startswith(start))
 observed=int(datetime.fromisoformat(trade['signal_time_tr']).timestamp()*1000)
 refms=int(datetime.fromisoformat(trade['ref_entry_time_tr']).timestamp()*1000)
 entry=float(trade['ref_entry_price'])
 before=prior('1m',observed,5)
 ix=bisect.bisect_left(tmap['1m'],refms)
 following=bars['1m'][ix+1:ix+1+15]
 summaries={}
 for h in (1,3,5,10,15):
  ss=following[:h]
  if len(ss)!=h:continue
  summaries[str(h)]=dict(close_roi=pct(ss[-1]['c'],entry),
   max_intrabar_high_roi=pct(max(x['h'] for x in ss),entry),
   min_intrabar_low_roi=pct(min(x['l'] for x in ss),entry))
 f=model['asof_price_flow']
 row=dict(signal=trade['signal_time_tr'],close_id=model['cid'],
 score=trade['score'],rolling_threshold=model['rolling'],
 score_margin=round(trade['score']-model['rolling'],6),
 signal_model_side='LONG',actual_order_not_confirmed=True,
 entry_reference=trade['ref_entry_time_tr'],
 ref_entry_price=entry,asof_price_flow=f,
 price_asof_complete=model['price_asof_available'],
 flow_source=model['flow_source'],regime=model['decision']['regime'],
 before_1m_returns_pct=[round((z['c']/z['o']-1)*100,4) for z in before],
 hypothetical_peak_roi=pk['highest_before_stop_roi_pct'],
 peak_after_minutes=pk['minutes_from_entry_to_peak'],
 highest_1m_close_roi=pk['highest_close_roi_pct'],
 to_stop_minutes=trade['holding_minutes'],
 within_first_minutes=summaries)
 rows.append(row)
 print('\nCASE',start,'score',row['score'],'threshold',row['rolling_threshold'],
       'margin',row['score_margin'],'FLOW',f,'FLOW_SOURCE',row['flow_source'],
       'regime',row['regime'],'PRE1M',row['before_1m_returns_pct'])
 print('EARLY_1m',summaries)
out=p/'LONG1_FOUR_FAST_REVERSAL_SIGNALS_AUDIT_20261115.json'
out.write_text(json.dumps(dict(research_only=True,no_trade_authority=True,
 historical_model_not_order=True,
 entry_assumed_next_completed_1m_close=True,
 asof_context_from_previous_model_join=True,
 after_reference_1m_close_and_extremes_not_actual_roi=True,
 rows=rows),ensure_ascii=False,indent=2)+'\n')
print('SAVED',out)
