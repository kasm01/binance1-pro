"""Pre-registered LONG1 recovery research gate, strictly no live order authority.

Training window 14–15 Nov 2026. Causal features from completed Binance USD-M
candles (historical public GET), archived model scores and existing shadow
microstructure. Candidate rules are NOT approved or predictive validation.
"""
import json,bisect,requests,math
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
ROOT=Path(__file__).parent
PATH=ROOT/'results/LONG1_0495_DUAL_WINDOWS_SCORE_SHADOW_20261115.json'
data=json.loads(PATH.read_text())
start=int(datetime(2026,11,14,19,45,tzinfo=timezone.utc).timestamp()*1000)
end=int(datetime(2026,11,15,15,tzinfo=timezone.utc).timestamp()*1000)
bars={}
for tf in ('3m','5m','15m'):
 resp=requests.get('https://fapi.binance.com/fapi/v1/klines',
 params=dict(symbol='NEARUSDT',interval=tf,startTime=start,endTime=end,limit=600),timeout=10)
 resp.raise_for_status()
 js=resp.json()
 if not isinstance(js,list) or not js or not isinstance(js[0],list):
  raise ValueError('invalid kline response')
 bars[tf]=[dict(close_ms=int(z[6]),open=float(z[1]),close=float(z[4]),
   high=float(z[2]),low=float(z[3])) for z in js]
 if any(a['close_ms']>=b['close_ms'] for a,b in zip(bars[tf],bars[tf][1:])):
  raise ValueError('non_monotonic_bars')
def prior(tf,ts):
 v=bars[tf];idx=bisect.bisect_left([z['close_ms'] for z in v],ts)
 return v[:idx]
def features(ts):
 b3=prior('3m',ts);b5=prior('5m',ts);b15=prior('15m',ts)
 if len(b3)<4 or len(b5)<3 or len(b15)<3:return None
 if ts-b3[-1]['close_ms']>180000+3000 or ts-b5[-1]['close_ms']>300000+3000:
  return None
 c3=b3[-1]['close'];c5=b5[-1]['close'];c15=b15[-1]['close']
 return {
  'return_3m':c3/b3[-2]['close']-1,
  'return_9m':c3/b3[-4]['close']-1,
  'return_5m':c5/b5[-2]['close']-1,
  'return_10m':c5/b5[-3]['close']-1,
  'return_15m':c15/b15[-2]['close']-1,
  'return_30m':c15/b15[-3]['close']-1,
  'latest_3m_green':b3[-1]['close']>b3[-1]['open'],
  'latest_5m_green':b5[-1]['close']>b5[-1]['open'],
  'three_m_higher_low':b3[-1]['low']>b3[-2]['low'],
  'five_m_higher_low':b5[-1]['low']>b5[-2]['low'],
  'known_3m_close_ms':b3[-1]['close_ms'],
  'known_5m_close_ms':b5[-1]['close_ms'],
  'known_15m_close_ms':b15[-1]['close_ms'],
 }
rows=[]
for x in data:
 ts=int(datetime.fromisoformat(x['local_ts']).timestamp()*1000)
 f=features(ts)
 y=dict(x)
 y['price_features']=f
 y['market_data_eligible']=f is not None
 rows.append(y)
# Three transparent, conservative candidate gates — not trained to memorize timestamps.
rules={
 'recovery_A':{'floor':.493,'flow':.20,'price3m':True,'price5m':True,'price9m':False,'nonneg_15m':False,'higher_low':False},
 'recovery_B':{'floor':.493,'flow':.20,'price3m':True,'price5m':True,'price9m':True,'nonneg_15m':False,'higher_low':False},
 'recovery_C':{'floor':.495,'flow':.20,'price3m':True,'price5m':True,'price9m':True,'nonneg_15m':True,'higher_low':True},
}
def run_gate(x,p):
 f=x['price_features'];checks=x.get('all_shadow_checks') or {}
 if f is None or not x['shadow_record_present'] or x.get('flow15') is None:
  return 'REJECT_MISSING_EVIDENCE'
 if not math.isfinite(x['score']) or x['score']<p['floor']:
  return 'REJECT_SCORE'
 if x['flow15']<p['flow'] or not x['one_min_support'] or not checks.get('whale_ok'):
  return 'PENDING_FLOW_OR_1M_WHALE'
 if f['return_3m']<=0 or f['return_5m']<=0:
  return 'PENDING_NO_3M_5M_RECOVERY'
 if p['price9m'] and f['return_9m']<=0:
  return 'PENDING_9M_DECLINE'
 if p['nonneg_15m'] and f['return_15m']<=0:
  return 'PENDING_15M_DECLINE'
 if p['higher_low'] and not (f['three_m_higher_low'] and f['five_m_higher_low']):
  return 'PENDING_STRUCTURE'
 return 'SHADOW_READY_CANDIDATE'
result={}
for k,p in rules.items():
 sub=[]
 for row in rows:
  x=dict(row)
  x['result']=run_gate(row,p)
  sub.append(x)
 group={}
 for groupname,where in [
  ('wanted_only',lambda x:bool(x['wanted']) and not x['avoid']),
  ('avoid_only',lambda x:bool(x['avoid']) and not x['wanted']),
  ('overlap',lambda x:bool(x['avoid']) and bool(x['wanted']))]:
  selection=[x for x in sub if where(x)]
  ready=[x for x in selection if x['result']=='SHADOW_READY_CANDIDATE']
  group[groupname]=dict(bars=len(selection),eligible_bars=sum(x['market_data_eligible'] for x in selection),
      shadow_ready=len(ready),ready_times=[x['local_ts'][11:16] for x in ready],
      decisions=dict(Counter(x['result'] for x in selection)))
 result[k]=group
 print('PROFILE',k,group)
result_payload=dict(schema='long1_recovery_regime_calibration_v1',
 stage='RESEARCH_ONLY',production_authorized=False,orders_authorized=False,
 threshold_profiles=rules,report=result,candles={k:len(v) for k,v in bars.items()},
 no_time_blacklist=True,independent_validation_required=True)
out=ROOT/'results/LONG1_RECOVERY_REGIME_FIRST_CALIBRATION_20261115.json'
out.write_text(json.dumps(result_payload,indent=2))
print('OUTPUT',out)
from research.long1_recovery_regime_frozen_v1 import assess
actual={}
for groupname,where in [
 ('wanted_only',lambda x:bool(x['wanted']) and not x['avoid']),
 ('avoid_only',lambda x:bool(x['avoid']) and not x['wanted']),
 ('overlap',lambda x:bool(x['avoid']) and bool(x['wanted']))]:
 a=[x for x in rows if where(x)]
 hits=[x for x in a if assess(x)['status']=='SHADOW_READY_CANDIDATE']
 actual[groupname]={'count':len(hits),'times':[x['local_ts'][11:16] for x in hits]}
 assert actual[groupname]['count']==result['recovery_C'][groupname]['shadow_ready'],(groupname,actual)
print('FROZEN_MODULE_PARITY',actual)
