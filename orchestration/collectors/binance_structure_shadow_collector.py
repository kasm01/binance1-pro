#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path
from typing import Any, Dict, List
import joblib
import numpy as np
import pandas as pd
import requests
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig
from features.fe_labels import build_features
from orchestration.context.entry_context_snapshot import strictly_prior_oi_snapshot
from orchestration.context.market_context_contract import classify_confirmed_position_build

URL='https://fapi.binance.com/fapi/v1/klines'
KLINE_COLUMNS=['open_time','open','high','low','close','volume','close_time','quote_asset_volume','number_of_trades','taker_buy_base_volume','taker_buy_quote_volume','ignore']


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
    if len(three)<80: raise RuntimeError('not_enough_closed_3m')
    rows=three[-260:]
    c=[float(x[4]) for x in rows]; o=[float(x[1]) for x in rows]
    h=[float(x[2]) for x in rows]; l=[float(x[3]) for x in rows]
    v=[float(x[5]) for x in rows]; tb=[float(x[9]) for x in rows]
    q=[float(x[7]) for x in rows]; tbq=[float(x[10]) for x in rows]
    rs=[_ret(c[i-1],c[i]) for i in range(1,len(c))]
    br=[(tb[i]/v[i]) if v[i]>0 else 0.5 for i in range(len(v))]; im=[2*x-1 for x in br]

    # Causal taker money-flow ratio from COMPLETED 3m bars only.
    # Binance kline quote-volume identity:
    #   aggressive_sell_quote = quote_volume - taker_buy_quote_volume
    #   net_taker_quote = buy_quote - sell_quote = 2*buy_quote - quote_volume
    # 5 x 3m = 15m, 20 x 3m = 60m. This reuses the existing 3m request.
    def quote_flow(window: int) -> float:
        qq=q[-window:]; bb=tbq[-window:]
        den=sum(qq)
        return (2.0*sum(bb)-den)/den if den>0 else 0.0
    flow15=quote_flow(5)
    flow60=quote_flow(20)
    tr=[]
    for i in range(len(c)):
        if i==0: tr.append(abs(h[i]-l[i]))
        else: tr.append(max(abs(h[i]-l[i]),abs(h[i]-c[i-1]),abs(l[i]-c[i-1])))
    alpha=1.0/14.0
    atr=tr[0]
    atr_pct=[]
    for i,t in enumerate(tr):
        if i>0: atr=alpha*t+(1.0-alpha)*atr
        atr_pct.append((atr/c[i]) if c[i]>0 else 0.0)
    look=atr_pct[-240:] if len(atr_pct)>=240 else atr_pct
    current=look[-1]
    atr_rank=(sum(1 for x in look[:-1] if x<=current)/float(max(1,len(look)-1))) if len(look)>1 else 0.5
    rng=max(0.0,h[-1]-l[-1])
    close_loc=((c[-1]-l[-1])/rng) if rng>0 else 0.5
    lower_wick=(min(o[-1],c[-1])-l[-1]) if rng>0 else 0.0
    lower_wick_frac=(lower_wick/rng) if rng>0 else 0.0
    return {'research_3m_close_time_ms':int(rows[-1][6]),'research_m3_ret1':rs[-1],
            'research_m3_ret2':_ret(c[-3],c[-1]),'research_m3_ret3':_ret(c[-4],c[-1]),
            'research_m3_up_frac3':sum(1.0 for x in rs[-3:] if x>0)/3.0,
            'research_m3_ret1_mean3':sum(rs[-3:])/3.0,'research_m3_ret1_accel':rs[-1]-rs[-2],
            'research_m3_buy_ratio':br[-1],'research_m3_imbalance':im[-1],'research_m3_imb_mean3':sum(im[-3:])/3.0,
            'research_m3_flow15_completed':flow15,'research_m3_flow60_completed':flow60,
            'research_m3_body':(c[-1]-o[-1])/o[-1] if o[-1]>0 else 0.0,
            'research_m3_range':(rng/c[-1]) if c[-1]>0 else 0.0,
            'research_m3_close_loc':close_loc,'research_m3_lower_wick_frac':lower_wick_frac,
            'research_m3_atr14_pct':current,'research_m3_atr_rank_240':atr_rank,
            'research_m3_atr_rank_history':len(look)}

def _load_long_model(symbol: str):
    model_path=ROOT/'models'/f'online_model_{symbol}_3m_best.joblib'
    meta_path=ROOT/'models'/f'model_meta_{symbol}_3m.json'
    if not model_path.exists() or not meta_path.exists(): return None,[]
    model=joblib.load(model_path); meta=json.loads(meta_path.read_text()); schema=list(meta.get('feature_schema') or [])
    return model,schema

def _long_model_score(rows: List[List[Any]], model: Any, schema: List[str]) -> float:
    if model is None or not schema or not rows: return float('nan')
    df=pd.DataFrame(rows,columns=KLINE_COLUMNS)
    feat=build_features(df,interval='3m')
    X=feat.reindex(columns=schema).apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan).fillna(0.0).to_numpy(float)
    proba=np.asarray(model.predict_proba(X),dtype=float)
    if proba.ndim==2 and proba.shape[1]>=2: return float(proba[-1,1])
    return float(proba.reshape(-1)[-1])

def _one_min_entry_metrics(one: List[List[Any]], confirmation_open_ms: int) -> Dict[str,Any]:
    rows=[x for x in one if int(x[0])<int(confirmation_open_ms)]
    if len(rows)<16: return {'available':False,'reason':'insufficient_completed_1m'}
    last=float(rows[-1][4]); prior=float(rows[-16][4]); q=sum(float(x[7]) for x in rows[-15:]); b=sum(float(x[10]) for x in rows[-15:])
    if last<=0 or prior<=0 or q<=0: return {'available':False,'reason':'invalid_1m_metrics'}
    return {'available':True,'confirmation_open_ms':int(confirmation_open_ms),'price_return_15m':last/prior-1.0,'money_flow_15m':(2.0*b-q)/q}

def _central_entry_context(r: Any, symbol: str, one_metrics: Dict[str,Any]) -> Dict[str,Any]:
    if not one_metrics.get('available'): return {'available':False,'reason':one_metrics.get('reason'),'schema_version':'entry_market_context.v1'}
    try:
        raw=r.get(f'context:oi:{symbol}'); oi=json.loads(raw) if isinstance(raw,str) else (raw if isinstance(raw,dict) else {})
        sel=strictly_prior_oi_snapshot(oi,cutoff_open_ms=int(one_metrics['confirmation_open_ms']))
        if not sel.get('available'): return {'available':False,'reason':'missing_causal_oi','schema_version':'entry_market_context.v1','open_interest':sel}
        reg=classify_confirmed_position_build(oi_delta_15m=sel.get('oi_delta_15m'),price_return_15m=one_metrics['price_return_15m'],money_flow_15m=one_metrics['money_flow_15m'])
        return {'available':True,'schema_version':'entry_market_context.v1','snapshot_stage':'preorder_completed_1m',
                'confirmation_open_ms':int(one_metrics['confirmation_open_ms']),
                'price_response':{'return_15m':float(one_metrics['price_return_15m'])},
                'money_flow':{'flow_15m':float(one_metrics['money_flow_15m'])},'open_interest':sel,
                'regime':{'name':reg.get('name'),'build_direction':reg.get('build_direction')},'policy_effect':'TELEMETRY_ONLY'}
    except Exception as e:
        return {'available':False,'reason':'entry_context_exception','error':type(e).__name__,'schema_version':'entry_market_context.v1'}

def _dynamic_gate(p: Dict[str,Any], score: float) -> Dict[str,Any]:
    base=float(os.getenv('COIN_LONG_THRESHOLD_NEARUSDT',os.getenv('LONG_THRESHOLD','0.525')) or .525)
    floor=float(os.getenv('LONG_DYNAMIC_MODEL_GATE_FLOOR','0.5114') or .5114)
    min_hist=int(float(os.getenv('LONG_DYNAMIC_MODEL_GATE_MIN_HISTORY','80') or 80)); min_atr=float(os.getenv('LONG_DYNAMIC_MODEL_GATE_MIN_ATR_RANK','0.60') or .60)
    min_close=float(os.getenv('LONG_DYNAMIC_MODEL_GATE_MIN_CLOSE_LOC','0.25') or .25); min_wick=float(os.getenv('LONG_DYNAMIC_MODEL_GATE_MIN_LOWER_WICK_FRAC','0.25') or .25)
    atr=_fnum(p.get('research_m3_atr_rank_240')); hist=int(p.get('research_m3_atr_rank_history') or 0); close=_fnum(p.get('research_m3_close_loc')); wick=_fnum(p.get('research_m3_lower_wick_frac'))
    structural_recovery=bool(hist>=min_hist and np.isfinite(atr) and atr>=min_atr and ((np.isfinite(close) and close>=min_close) or (np.isfinite(wick) and wick>=min_wick)))
    # Exact runtime parity: scores already >= base need no relaxation; scores
    # below the configured floor are never rescued. Only floor <= score < base
    # may consume the structural recovery condition.
    recovery=bool(structural_recovery and score>=floor and score<base)
    eff=floor if recovery else base
    return {'base_threshold':base,'floor':floor,'effective_threshold':eff,'recovery':recovery,'structural_recovery':structural_recovery,'reason':'strong_recovery' if recovery else 'base'}

def _fnum(x: Any) -> float:
    try: return float(x)
    except Exception: return float('nan')

def next_close_sleep(grace_sec: float)->float:
    now=time.time(); nxt=(int(now//60)+1)*60+grace_sec
    return max(0.5,nxt-now)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--symbols',default='NEARUSDT'); ap.add_argument('--strategy-id',default='LONG1'); ap.add_argument('--ttl-sec',type=int,default=180)
    ap.add_argument('--grace-sec',type=float,default=1.5); ap.add_argument('--poll-sec',type=float,default=None,help='deprecated; close-aligned polling is automatic')
    a=ap.parse_args(); syms=[s.strip().upper() for s in a.symbols.split(',') if s.strip()]
    strategy_id=str(a.strategy_id or 'LONG1').strip().upper(); strategy_ns=strategy_id.lower()
    model_stream=f'shadow:telemetry:{strategy_ns}:model_candidate_v1'
    r=RedisConfig().client
    if r is None: raise SystemExit('redis_unavailable')
    session=requests.Session(); session.headers.update({'User-Agent':'binance1-structure-shadow/2.0'})
    models={}; schemas={}
    for s in syms:
        try: models[s],schemas[s]=_load_long_model(s)
        except Exception as e: models[s],schemas[s]=None,[]; print(f'MODEL_WARN symbol={s} err={type(e).__name__}',flush=True)
    cache3: Dict[str,Dict[str,Any]]={}; calls_1m=0; calls_3m=0
    print(f'START shadow-only smart-poll strategy={strategy_id} symbols={",".join(syms)} grace_sec={a.grace_sec} ttl_sec={a.ttl_sec}',flush=True)
    while True:
      cycle_ms=int(time.time()*1000); minute=int(time.time()//60)
      refresh3=(minute%3)==0
      for s in syms:
        try:
          t0=time.time(); one=closed_klines(session,s,'1m',120); calls_1m+=1; p1=build_1m(one)
          if s not in cache3 or refresh3:
              rows3=closed_klines(session,s,'3m',260); calls_3m+=1
              cache3[s]=build_3m(rows3)
              score=_long_model_score(rows3,models.get(s),schemas.get(s) or [])
              gate=_dynamic_gate(cache3[s],score) if np.isfinite(score) else {'effective_threshold':float('inf'),'reason':'model_unavailable','recovery':False}
              flow60=_fnum(cache3[s].get('research_m3_flow60_completed')); flow_exh=float(os.getenv('LONG_MONEY_FLOW_EXHAUSTION_60M','0.15') or .15); exhausted=bool(np.isfinite(flow60) and flow60>=flow_exh)
              cache3[s]['model_shadow_score']=score if np.isfinite(score) else None; cache3[s]['model_shadow_gate']=gate; cache3[s]['long_money_flow_exhaustion']=exhausted
              gate_pass=bool(np.isfinite(score) and score>=float(gate.get('effective_threshold',float('inf'))))
              cache3[s]['model_shadow_gate_pass']=gate_pass
              # Publish a candidate only on the actual fresh 3m boundary.
              # A mid-cycle process restart may warm cache/model state, but must
              # never reinterpret the previous completed 3m bar as a new signal.
              if refresh3 and gate_pass and not exhausted:
                  close_ms=int(cache3[s].get('research_3m_close_time_ms') or 0)
                  dedupe_key=f'shadow:telemetry:{strategy_ns}:model_candidate:last_close:{s}'
                  prior_close=0
                  try:
                      prior_close=int(r.get(dedupe_key) or 0)
                  except Exception:
                      prior_close=0
                  if close_ms>0 and close_ms!=prior_close:
                      confirm_open_ms=(int(time.time()*1000)//60000)*60000
                      one_metrics=_one_min_entry_metrics(one,confirm_open_ms); entry_ctx=_central_entry_context(r,s,one_metrics)
                      micro={}
                      try:
                          mraw=r.get(f'shadow:market_context:microstructure:{s}'); micro=json.loads(mraw) if isinstance(mraw,str) else (mraw if isinstance(mraw,dict) else {})
                      except Exception: micro={}
                      rec={'schema_version':'strategy_model_shadow_candidate.v1','strategy_id':strategy_id,'ts':time.time(),'observed_at_ms':int(time.time()*1000),'symbol':s,'side':'long','interval':'3m',
                           'routing':'OFF','policy_effect':'TELEMETRY_ONLY','completed_close_time_ms':close_ms,
                           'model_score':float(score),'effective_threshold':float(gate.get('effective_threshold')),'base_threshold':gate.get('base_threshold'),'gate_reason':gate.get('reason'),'dynamic_recovery':gate.get('recovery'),
                           'money_flow60_completed':flow60,'long_money_flow_exhaustion':False,'entry_market_context':entry_ctx,
                           'microstructure':{'status':micro.get('status'),'spread_bps':micro.get('spread_bps'),'l1_imbalance':micro.get('l1_imbalance'),'depth5_imbalance':micro.get('depth5_imbalance'),'depth20_imbalance':micro.get('depth20_imbalance'),'microprice_dev_bps':micro.get('microprice_dev_bps')}}
                      r.xadd(model_stream,{'symbol':s,'json':json.dumps(rec,separators=(',',':'),sort_keys=True)},maxlen=20000,approximate=True)
                      r.set(dedupe_key,str(close_ms),ex=172800)
                      print(f"MODEL_CAND symbol={s} score={score:.6f} need={float(gate.get('effective_threshold')):.6f} reason={gate.get('reason')} flow60={flow60:.4f} close={close_ms} ctx={entry_ctx.get('regime')}",flush=True)
                  elif close_ms>0:
                      print(f'MODEL_SKIP_DUP symbol={s} close={close_ms}',flush=True)
          now_ms=int(time.time()*1000); p={'schema_version':3,'shadow_only':True,'source':'binance_public','symbol':s,
             'interval':'1m','observed_at_ms':now_ms,'source_age_sec':round(max(0,(now_ms-p1['source_close_time_ms'])/1000),3),
             'latency_ms':round((time.time()-t0)*1000,2),'status':'OK','network_calls_1m':calls_1m,'network_calls_3m':calls_3m,
             'smart_poll':True}; p.update(p1); p.update(cache3[s])
          raw=json.dumps(p,separators=(',',':')); r.set(f'shadow:market_context:binance_structure:{s}',raw,ex=a.ttl_sec)
          print(f"OK symbol={s} close1={p['source_close_time_ms']} close3={p['research_3m_close_time_ms']} refresh3={refresh3} calls={calls_1m}/{calls_3m} r1={p['m1_ret1']:.6f} m3accel={p['research_m3_ret1_accel']:.6f} flow15={p['research_m3_flow15_completed']:.4f} flow60={p['research_m3_flow60_completed']:.4f} model={p.get('model_shadow_score')} pass={p.get('model_shadow_gate_pass')}",flush=True)
        except Exception as e:
          print(f'ERR symbol={s} type={type(e).__name__} msg={str(e)[:140]}',flush=True)
      time.sleep(next_close_sleep(a.grace_sec))
if __name__=='__main__': main()
