"""Read-only as-of 11-15 Nov research regime evaluation; no production influence.

Historical Binance 3m/5m/15m fully CLOSED klines, joined with the archived
Redis shadow flow per close_id and logged 3m score. No trade PnL claims.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from collections import defaultdict,Counter
from pathlib import Path
import requests,redis,json,re,bisect,hashlib,statistics
from research.regime.long1_market_regime_shadow_v1 import classify,PROFILE
from research.shared_reference.window_reference_reader_v1 import load_reference,lookup
TR=timezone(timedelta(hours=3));UTC=timezone.utc
root=Path('/home/kasm920/binance1-pro')
ref=load_reference()
start=int(datetime(2026,11,10,20,0,tzinfo=UTC).timestamp()*1000)
end=int(datetime(2026,11,15,21,0,tzinfo=UTC).timestamp()*1000)
def price_bars(tf,step):
    out=[];t=start
    while t<end:
        z=requests.get('https://fapi.binance.com/fapi/v1/klines',
          params=dict(symbol='NEARUSDT',interval=tf,startTime=t,endTime=end-1,limit=1000),timeout=15)
        z.raise_for_status();page=z.json()
        if not isinstance(page,list):
            raise ValueError('unexpected Binance klines error response')
        if not page:
            break  # historical end bound can extend beyond the current UTC time
        if not isinstance(page[0],list):
            raise ValueError('unexpected Binance candle schema')
        out+=page
        next_t=int(page[-1][0])+step
        if next_t<=t:raise ValueError('nonmonotonic pagination')
        t=next_t
    v={int(z[6]):dict(t=int(z[6]),h=float(z[2]),l=float(z[3]),o=float(z[1]),c=float(z[4])) for z in out}
    return sorted(v.values(),key=lambda a:a['t'])
bars={tf:price_bars(tf,step) for tf,step in [('3m',180000),('5m',300000),('15m',900000)]}
tmap={tf:[x['t'] for x in v] for tf,v in bars.items()}
def last(tf,ms,n):
    ix=bisect.bisect_left(tmap[tf],ms)
    return bars[tf][max(0,ix-n):ix]
def features(ms,flow):
    b3=last('3m',ms,2);b5=last('5m',ms,2);b15=last('15m',ms,3)
    if len(b3)<2 or len(b5)<2 or len(b15)<3:return None
    if ms-b3[-1]['t']>183000 or ms-b5[-1]['t']>303000 or ms-b15[-1]['t']>903000:return None
    return dict(return_3m=b3[-1]['c']/b3[-2]['c']-1,
       return_5m=b5[-1]['c']/b5[-2]['c']-1,
       return_15m=b15[-1]['c']/b15[-2]['c']-1,
       return_30m=b15[-1]['c']/b15[-3]['c']-1,
       flow15=flow,asof_complete=True)
models={}
pat=re.compile(r'close_id=(\d+) p_used=([\d.]+) long_thr=([\d.]+) side=(\w+)')
for file in ('logs/main.log.3','logs/main.log.2','logs/main.log.1','logs/main.log'):
 p=root/file
 if not p.exists():continue
 for line in p.open(errors='replace'):
    if '[MODEL-SCORE]' not in line:continue
    m=pat.search(line)
    if not m:continue
    try:ts=datetime.strptime(line[:19],'%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
    except ValueError:continue
    ms=int(ts.timestamp()*1000)
    if start<=ms<end:
        models[int(m[1])]=dict(score=float(m[2]),rolling=float(m[3]),model_long=m[4]=='long',log_ms=ms)
r=redis.Redis(decode_responses=True,socket_timeout=5)
events=r.xrange('telemetry:long1:context_adaptive_gate:v1',f'{start}-0',f'{end-1}-99999')
rows=[]
for sid,p in events:
    try:
        o=json.loads(p['json']); cid=int(o['close_id']);ts=int(sid.split('-')[0])
        local=datetime.fromtimestamp(ts/1000,TR)
        if local.date().isoformat() not in ('2026-11-11','2026-11-12','2026-11-13','2026-11-14','2026-11-15'):continue
        label=lookup(local,dataset=ref)['long']
        model=models.get(cid)
        flow=o.get('t15_signed_ratio')
        age=o.get('micro_age_sec')
        flow_available=isinstance(flow,(float,int)) and isinstance(age,(int,float)) and 0<=age<=30
        f=features(ts,float(flow)) if flow_available else None
        decision=classify(f)
        rows.append(dict(close_id=cid,time_tr=local.isoformat(),
             label=label,model_present=bool(model),
             live_model_long=model['model_long'] if model else None,
             score=model['score'] if model else o.get('score'),
             rolling=model['rolling'] if model else o.get('normal_threshold'),
             flow_age_sec=age,flow_asof_valid=flow_available,
             asof_market_available=f is not None,
             regime=decision['regime'],reason=decision['reason'],
             advice=decision['advisory'],context_shadow_pass=o.get('pass'),
             order_authorized=False))
    except (ValueError,TypeError,KeyError,OverflowError) as ex:print('ROW_SKIPPED',type(ex).__name__)
groups=defaultdict(list)
for z in rows:groups[(z['time_tr'][:10],z['label'])].append(z)
daily=[]
for day in ('2026-11-11','2026-11-12','2026-11-13','2026-11-14','2026-11-15'):
 for label in ('LONG_TARGET','LONG_AVOID','CONFLICT_NO_TRADE','UNLABELLED'):
    ss=groups[(day,label)];model_long=[x for x in ss if x['live_model_long'] is True]
    daily.append(dict(date_tr=day,label=label,
       recorded_shadow_events=len(ss),
       known_mtf_and_flow=sum(x['asof_market_available'] for x in ss),
       model_long_events=len(model_long),
       model_long_with_market=sum(x['asof_market_available'] for x in model_long),
       model_long_veto=sum(x['advice']=='VETO_LONG' for x in model_long),
       model_long_research_candidate=sum(x['advice']=='RESEARCH_CANDIDATE' for x in model_long),
       model_long_uncertain_or_unknown=sum(x['advice']=='PENDING' for x in model_long),
       bearish=sum(x['regime']=='BEARISH' for x in ss),
       bullish=sum(x['regime']=='BULLISH' for x in ss),
       recovery=sum(x['regime']=='RECOVERY' for x in ss),
       uncertain=sum(x['regime']=='UNCERTAIN' for x in ss),
       unknown=sum(x['regime']=='UNKNOWN' for x in ss)))
out=root/'research/results/LONG1_REGIME_SHADOW_V1_20261111_15.json'
out.write_text(json.dumps(dict(schema='long1_regime_shadow_replay_v1',
   trained_dates='2026-11-11 to 2026-11-15 (user-labelled development, not independent test)',
   research_only=True,orders_authorized=False,
   no_future_bar_used_in_setup=True,flow_asof_bound_sec=30,
   labels_not_used_for_decisions=True,model_score_does_not_imply_order=True,
   reference_sha256=hashlib.sha256((root/'research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json').read_bytes()).hexdigest(),
   classifier_sha256=hashlib.sha256((root/'research/regime/long1_market_regime_shadow_v1.py').read_bytes()).hexdigest(),
   candle_counts={tf:len(a) for tf,a in bars.items()},
   counts=daily,events=rows),ensure_ascii=False,indent=2)+'\n')
for a in daily:
 if a['label']=='UNLABELLED':continue
 print(a['date_tr'],a['label'],'events',a['recorded_shadow_events'],
   'market_ok',a['known_mtf_and_flow'],'mlong',a['model_long_events'],
   'mlong_veto',a['model_long_veto'],
   'mlong_candidate',a['model_long_research_candidate'],
   'bearish',a['bearish'],'recovery',a['recovery'],'unknown',a['unknown'])
print('TOTAL',len(rows),'MODEL_MATCH',sum(x['model_present'] for x in rows),
 'CANDLES',{tf:len(a) for tf,a in bars.items()},'FILE',out)
