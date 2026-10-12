#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
from typing import Any, Dict, List
import requests
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig

URL='https://fapi.binance.com/fapi/v1/klines'

def closed_klines(session: requests.Session, symbol: str, interval: str, limit: int) -> List[List[Any]]:
    r=session.get(URL,params={'symbol':symbol,'interval':interval,'limit':limit},timeout=5)
    r.raise_for_status(); rows=r.json(); now_ms=int(time.time()*1000)
    return [x for x in rows if int(x[6]) < now_ms]

def _ret(a: float,b: float)->float:
    return (b/a-1.0) if a>0 else 0.0

def _ema(values: List[float], period: int) -> float:
    if len(values) < period:
        raise RuntimeError(f'not_enough_ema_{period}')
    alpha=2.0/(float(period)+1.0)
    ema=sum(values[:period])/float(period)
    for v in values[period:]:
        ema=alpha*float(v)+(1.0-alpha)*ema
    return float(ema)

def build_1m(one: List[List[Any]]) -> Dict[str,Any]:
    if len(one)<100: raise RuntimeError('not_enough_closed_1m')
    c_all=[float(x[4]) for x in one]
    one4=one[-4:]; c=[float(x[4]) for x in one4]; l=[float(x[3]) for x in one4]
    r1=_ret(c[-2],c[-1]); r3=_ret(c[-4],c[-1]); recovery=c[-1]/l[-1]-1.0 if l[-1]>0 else None
    ema7=_ema(c_all,7); ema25=_ema(c_all,25); ema99=_ema(c_all,99); px=c[-1]
    return {'source_close_time_ms':int(one4[-1][6]),'m1_ret1':r1,'m3_ret1':r3,
            'last_close':px,'last_low':l[-1],'recovery_from_low':recovery,
            'deep_pullback':bool((r3<=-0.0030) or (r1<=-0.0020)),
            'low_recovery':bool(recovery is not None and recovery<0.0010),'price_down_3m':bool(r3<0),
            'ema7':ema7,'ema25':ema25,'ema99':ema99,
            'price_above_ema99':bool(px>ema99),'ema7_above_ema25':bool(ema7>ema25),
            'price_vs_ema99_bps':((px/ema99)-1.0)*1e4 if ema99>0 else None,
            'ema7_vs_ema25_bps':((ema7/ema25)-1.0)*1e4 if ema25>0 else None}

def build_3m(three: List[List[Any]]) -> Dict[str,Any]:
    if len(three)<5: raise RuntimeError('not_enough_closed_3m')
    three=three[-5:]; c=[float(x[4]) for x in three]; o=[float(x[1]) for x in three]
    h=[float(x[2]) for x in three]; l=[float(x[3]) for x in three]; v=[float(x[5]) for x in three]; tb=[float(x[9]) for x in three]
    rs=[_ret(c[i-1],c[i]) for i in range(1,len(c))]; br=[(tb[i]/v[i]) if v[i]>0 else 0.5 for i in range(len(v))]; im=[2*x-1 for x in br]
    return {'research_3m_close_time_ms':int(three[-1][6]),'research_m3_ret1':rs[-1],
            'research_m3_ret2':_ret(c[-3],c[-1]),'research_m3_ret3':_ret(c[-4],c[-1]),
            'research_m3_up_frac3':sum(1.0 for x in rs[-3:] if x>0)/3.0,
            'research_m3_ret1_mean3':sum(rs[-3:])/3.0,'research_m3_ret1_accel':rs[-1]-rs[-2],
            'research_m3_buy_ratio':br[-1],'research_m3_imbalance':im[-1],'research_m3_imb_mean3':sum(im[-3:])/3.0,
            'research_m3_body':(c[-1]-o[-1])/o[-1] if o[-1]>0 else 0.0,
            'research_m3_range':(h[-1]-l[-1])/c[-1] if c[-1]>0 else 0.0,
            'research_m3_close_loc':((c[-1]-l[-1])/(h[-1]-l[-1])) if h[-1]>l[-1] else 0.5}

def next_close_sleep(grace_sec: float)->float:
    now=time.time(); nxt=(int(now//60)+1)*60+grace_sec
    return max(0.5,nxt-now)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--symbols',default='NEARUSDT'); ap.add_argument('--ttl-sec',type=int,default=180)
    ap.add_argument('--grace-sec',type=float,default=1.5); ap.add_argument('--poll-sec',type=float,default=None,help='deprecated; close-aligned polling is automatic')
    a=ap.parse_args(); syms=[s.strip().upper() for s in a.symbols.split(',') if s.strip()]
    r=RedisConfig().client
    if r is None: raise SystemExit('redis_unavailable')
    session=requests.Session(); session.headers.update({'User-Agent':'binance1-structure-shadow/2.0'})
    cache3: Dict[str,Dict[str,Any]]={}; calls_1m=0; calls_3m=0
    print(f'START shadow-only smart-poll symbols={",".join(syms)} grace_sec={a.grace_sec} ttl_sec={a.ttl_sec}',flush=True)
    while True:
      cycle_ms=int(time.time()*1000); minute=int(time.time()//60)
      refresh3=(minute%3)==0
      for s in syms:
        try:
          t0=time.time(); one=closed_klines(session,s,'1m',120); calls_1m+=1; p1=build_1m(one)
          if s not in cache3 or refresh3:
              cache3[s]=build_3m(closed_klines(session,s,'3m',8)); calls_3m+=1
          now_ms=int(time.time()*1000); p={'schema_version':3,'shadow_only':True,'source':'binance_public','symbol':s,
             'interval':'1m','observed_at_ms':now_ms,'source_age_sec':round(max(0,(now_ms-p1['source_close_time_ms'])/1000),3),
             'latency_ms':round((time.time()-t0)*1000,2),'status':'OK','network_calls_1m':calls_1m,'network_calls_3m':calls_3m,
             'smart_poll':True}; p.update(p1); p.update(cache3[s])
          raw=json.dumps(p,separators=(',',':')); r.set(f'shadow:market_context:binance_structure:{s}',raw,ex=a.ttl_sec)
          print(f"OK symbol={s} close1={p['source_close_time_ms']} close3={p['research_3m_close_time_ms']} refresh3={refresh3} calls={calls_1m}/{calls_3m} r1={p['m1_ret1']:.6f} m3accel={p['research_m3_ret1_accel']:.6f}",flush=True)
        except Exception as e:
          print(f'ERR symbol={s} type={type(e).__name__} msg={str(e)[:140]}',flush=True)
      time.sleep(next_close_sleep(a.grace_sec))
if __name__=='__main__': main()
