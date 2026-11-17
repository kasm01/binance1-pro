"""RESEARCH-only hybrid: 0.65 ROI arm/0.15 pp giveback, keep direct fixed 1.25 TP.
Pair same 35 logged-model entry references as precomputed fixed-vs-trail replay.
Stop-first intrabar 1m LOW; direct fixed TP intrabar HIGH; 1m CLOSE exit
on retrace after arm. No live execution authority.
"""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from statistics import mean,median
from collections import Counter
from bisect import bisect_left
import requests,json
ROOT=Path('/home/kasm920/binance1-pro')
paired=json.load(open(ROOT/'research/results/LONG1_PAIRED_35_FIXED_VS_TRAIL_065_015_20261115.json'))
refs=paired['pairs'];assert len(refs)==35
TZ=timezone(timedelta(hours=3)); UTC=timezone.utc
start=int(datetime(2026,11,11,8,tzinfo=UTC).timestamp()*1000)
end=int(datetime(2026,11,16,0,tzinfo=UTC).timestamp()*1000)
bars=[];cursor=start
while cursor<end:
 res=requests.get('https://fapi.binance.com/fapi/v1/klines',
   params={'symbol':'NEARUSDT','interval':'1m','startTime':cursor,'endTime':end-1,'limit':1000},timeout=12)
 res.raise_for_status();page=res.json()
 if not isinstance(page,list):raise ValueError('invalid candles')
 if not page:break
 bars.extend(page);cur=int(page[-1][0])+60000
 if cur<=cursor:raise RuntimeError('pagination stalled')
 cursor=cur
v=sorted({int(r[6]):dict(t=int(r[6]),o=float(r[1]),c=float(r[4]),h=float(r[2]),l=float(r[3])) for r in bars}.values(),key=lambda x:x['t'])
ts=[x['t'] for x in v]
def roi(p,e):return (p/e-1)*300
out=[]
for z in refs:
 ms=int(datetime.fromisoformat(z['signal_time_tr']).timestamp()*1000)
 i=bisect_left(ts,ms)
 assert 0<ts[i]-ms<=60000
 entry=v[i]['c'];peak=0;arm=False;arm_ms=None
 exit_code=None;exit_net=None;close_ms=None
 prior=v[i]
 for b in v[i+1:]:
  if b['t']-prior['t']!=60000:exit_code='CENSORED_GAP';break
  prior=b
  if roi(b['l'],entry)<=-8.97:
   exit_code='SL';exit_net=-8.97-0.24;close_ms=b['t'];break
  if roi(b['h'],entry)>=1.25:
   exit_code='DIRECT_TP';exit_net=1.25-0.24;close_ms=b['t'];break
  close=roi(b['c'],entry)
  if close>=.65 and not arm:arm=True;arm_ms=b['t']
  if arm:
   peak=max(peak,close)
   if b['t']>arm_ms and close<=peak-.15:
    exit_code='EARLY_TRAIL';exit_net=close-.24;close_ms=b['t'];break
 if exit_code is None:exit_code='OPEN_DATA_END'
 out.append(dict(signal_time_tr=z['signal_time_tr'],fixed_status=z['fixed']['status'],
 fixed_net_roi=z['fixed'].get('roi_net'),hybrid_status=exit_code,
 hybrid_net_roi=round(exit_net,4) if exit_net is not None else None,
 exit_time_tr=datetime.fromtimestamp(close_ms/1000,TZ).isoformat() if close_ms else None,
 minutes_held=round((close_ms-v[i]['t'])/60000,2) if close_ms else None))
closed=[r['hybrid_net_roi'] for r in out if r['hybrid_net_roi'] is not None]
stat=dict(n=len(closed),wins=sum(x>0 for x in closed),losses=sum(x<=0 for x in closed),
 mean_net_roi=round(mean(closed),4),sum_net_roi_not_account_return=round(sum(closed),4),
 states=dict(Counter(z['hybrid_status'] for z in out)))
print('HYBRID_STATS',stat)
print('FIXED_TO_HYBRID_NEGATIVE',sum(z['fixed_net_roi']>0 and z['hybrid_net_roi']<=0 for z in out))
print('STOP_TO_EARLY_EXIT',[(z['signal_time_tr'],z['hybrid_net_roi']) for z in out if z['fixed_status']=='SL_FIRST' and z['hybrid_status']=='EARLY_TRAIL'])
for z in out:
 if z['fixed_status']=='FIXED_TP' and z['hybrid_net_roi']<0:print('WON_FIXED_LOST_HYBRID',z)
file=ROOT/'research/results/LONG1_PAIRED_35_HYBRID_065_015_CAP125_20261115.json'
file.write_text(json.dumps(dict(schema='long1_paired_hybrid_v1',production_change=False,
 assumptions='same fixed entry, stop first, fixed TP barrier 1.25, 0.65 close arm, 0.15 giveback close. No funding/slippage/actual entry gating.',stats=stat,results=out),ensure_ascii=False,indent=2)+'\n')
print('SAVED',file)
