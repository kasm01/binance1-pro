from __future__ import annotations
import argparse, json, math, sys, time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Tuple
import requests, websocket
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig

WS_BASE='wss://fstream.binance.com/stream?streams='

def _f(x: Any, d: float=0.0) -> float:
    try: return float(x)
    except Exception: return d

def _imb(levels: List[List[str]], n: int) -> float:
    if not levels: return 0.0
    q=sum(_f(x[1]) for x in levels[:n]); return q

def _safe_div(a: float,b: float,d: float=0.0) -> float:
    return a/b if abs(b)>1e-15 else d

def _current_trade_candle_features(candle: Dict[str,Any], now_ms: int) -> Dict[str,Any]:
    op=_f(candle.get('open')); hi=_f(candle.get('high')); lo=_f(candle.get('low')); cl=_f(candle.get('close'))
    start=int(candle.get('start_ms') or 0); end=start+59999 if start>0 else 0
    rng=max(0.0,hi-lo)
    progress=max(0.0,min(1.0,(now_ms-start)/60000.0)) if start>0 else None
    body_ratio=_safe_div(abs(cl-op),rng,0.0) if rng>0 else 0.0
    long_span=max(0.0,hi-op); short_span=max(0.0,op-lo)
    long_retrace=_safe_div(max(0.0,hi-cl),long_span,0.0) if long_span>0 else 0.0
    short_retrace=_safe_div(max(0.0,cl-lo),short_span,0.0) if short_span>0 else 0.0
    return {
      'live1m_start_ms':start,'live1m_end_ms':end,'live1m_progress':progress,
      'live1m_complete_from_open':bool(candle.get('complete_from_open')),
      'live1m_open':op,'live1m_high':hi,'live1m_low':lo,'live1m_close':cl,
      'live1m_body_ratio':body_ratio,
      'live1m_long_direction_support':bool(cl>=op) if op>0 and cl>0 else None,
      'live1m_short_direction_support':bool(cl<=op) if op>0 and cl>0 else None,
      'live1m_long_retrace_ratio':min(1.0,long_retrace),
      'live1m_short_retrace_ratio':min(1.0,short_retrace),
      'live1m_long_location':_safe_div(cl-lo,rng,0.5) if rng>0 else 0.5,
      'live1m_short_location':_safe_div(hi-cl,rng,0.5) if rng>0 else 0.5,
    }

def _trade_stats(trades: Deque[Tuple[int,float,float,bool]], now_ms: int, sec: int, mid: float) -> Dict[str,float]:
    lo=now_ms-sec*1000; rows=[x for x in trades if x[0]>=lo]
    if not rows: return {'count':0,'qty':0.0,'quote':0.0,'buy_ratio':0.5,'delta_qty':0.0,'delta_quote':0.0,'signed_ratio':0.0,'vwap_dev_bps':0.0,'min_price':0.0,'max_price':0.0}
    qty=sum(x[2] for x in rows); quote=sum(x[1]*x[2] for x in rows)
    buyq=sum(x[2] for x in rows if not x[3]); sellq=sum(x[2] for x in rows if x[3])
    buy_not=sum(x[1]*x[2] for x in rows if not x[3]); sell_not=sum(x[1]*x[2] for x in rows if x[3])
    vwap=_safe_div(quote,qty,mid)
    return {'count':len(rows),'qty':qty,'quote':quote,'buy_ratio':_safe_div(buyq,qty,0.5),'delta_qty':buyq-sellq,
            'delta_quote':buy_not-sell_not,'signed_ratio':_safe_div(buy_not-sell_not,quote,0.0),
            'vwap_dev_bps':_safe_div(vwap-mid,mid,0.0)*1e4,'min_price':min(x[1] for x in rows),'max_price':max(x[1] for x in rows)}

def build_snapshot(symbol: str, depth: Dict[str,Any], book: Dict[str,Any], mark: Dict[str,Any], trades: Deque[Tuple[int,float,float,bool]], recv_ms: int) -> Dict[str,Any]:
    bids=depth.get('b') or []; asks=depth.get('a') or []
    bid=_f((book or {}).get('b') or (bids[0][0] if bids else 0)); ask=_f((book or {}).get('a') or (asks[0][0] if asks else 0))
    bq=_f((book or {}).get('B') or (bids[0][1] if bids else 0)); aq=_f((book or {}).get('A') or (asks[0][1] if asks else 0))
    mid=(bid+ask)/2 if bid>0 and ask>0 else 0.0
    spread=_safe_div(ask-bid,mid,0.0)*1e4 if mid else 0.0
    micro=_safe_div(ask*bq+bid*aq,bq+aq,mid) if mid else 0.0
    bid5=_imb(bids,5); ask5=_imb(asks,5); bid20=_imb(bids,20); ask20=_imb(asks,20)
    i1=_safe_div(bq-aq,bq+aq,0.0); i5=_safe_div(bid5-ask5,bid5+ask5,0.0); i20=_safe_div(bid20-ask20,bid20+ask20,0.0)
    mark_px=_f(mark.get('p')); index_px=_f(mark.get('i')); funding=_f(mark.get('r'))
    basis_bps=_safe_div(mark_px-index_px,index_px,0.0)*1e4 if index_px else 0.0
    now_ms=int(time.time()*1000); event_ms=max(int(depth.get('E') or 0),int((book or {}).get('E') or 0),int(mark.get('E') or 0),max([t[0] for t in trades],default=0))
    out={'schema_version':2,'shadow_only':True,'source':'binance_futures_ws','symbol':symbol,'status':'OK','observed_at_ms':now_ms,
         'event_time_ms':event_ms,'event_age_sec':max(0.0,(now_ms-event_ms)/1000) if event_ms else None,'recv_age_sec':max(0.0,(now_ms-recv_ms)/1000),
         'best_bid':bid,'best_ask':ask,'mid':mid,'spread_bps':spread,'microprice':micro,'microprice_dev_bps':_safe_div(micro-mid,mid,0.0)*1e4 if mid else 0.0,
         'mark_price':mark_px,'index_price':index_px,'basis_bps':basis_bps,'funding_rate':funding,'next_funding_time_ms':mark.get('T'),
         'l1_imbalance':i1,'depth5_imbalance':i5,'depth20_imbalance':i20,'bid_qty_l1':bq,'ask_qty_l1':aq,'bid_qty_5':bid5,'ask_qty_5':ask5,'bid_qty_20':bid20,'ask_qty_20':ask20}
    for sec in (1,5,15,30):
        st=_trade_stats(trades,now_ms,sec,mid)
        for k,v in st.items(): out[f't{sec}_{k}']=v
    return out

def _read_json_key(r: Any, key: str) -> Dict[str,Any]:
    try:
        raw=r.get(key)
        if not raw: return {}
        obj=json.loads(raw) if isinstance(raw,str) else raw
        return obj if isinstance(obj,dict) else {}
    except Exception:
        return {}

def build_entry_context(r: Any, sym: str, micro: Dict[str,Any]) -> Dict[str,Any]:
    st=_read_json_key(r,f'shadow:market_context:binance_structure:{sym}')
    oi=_read_json_key(r,f'shadow:market_context:okx_oi:{sym}')
    return {
      'schema_version':2,'shadow_only':True,'symbol':sym,'observed_at_ms':micro.get('observed_at_ms'),'mid':micro.get('mid'),
      'spread_bps':micro.get('spread_bps'),'basis_bps':micro.get('basis_bps'),'funding_rate':micro.get('funding_rate'),
      'l1_imbalance':micro.get('l1_imbalance'),'depth5_imbalance':micro.get('depth5_imbalance'),'depth20_imbalance':micro.get('depth20_imbalance'),
      't5_signed_ratio':micro.get('t5_signed_ratio'),'t15_signed_ratio':micro.get('t15_signed_ratio'),'t30_signed_ratio':micro.get('t30_signed_ratio'),
      'm1_ret1':st.get('m1_ret1'),'m1_ret3':st.get('m3_ret1'),'recovery_from_low':st.get('recovery_from_low'),
      'structure_close_time_ms':st.get('source_close_time_ms'),'m3_close_time_ms':st.get('research_3m_close_time_ms'),
      'deep_pullback':st.get('deep_pullback'),'low_recovery':st.get('low_recovery'),'price_down_3m':st.get('price_down_3m'),
      'm3_ret1':st.get('research_m3_ret1'),'m3_ret2':st.get('research_m3_ret2'),'m3_ret3':st.get('research_m3_ret3'),
      'm3_up_frac3':st.get('research_m3_up_frac3'),'m3_ret1_mean3':st.get('research_m3_ret1_mean3'),'m3_accel':st.get('research_m3_ret1_accel'),
      'm3_imbalance':st.get('research_m3_imbalance'),'m3_imb_mean3':st.get('research_m3_imb_mean3'),'m3_body':st.get('research_m3_body'),
      'm3_range':st.get('research_m3_range'),'m3_close_loc':st.get('research_m3_close_loc'),
      'price_above_ema99':st.get('price_above_ema99'),'ema7_above_ema25':st.get('ema7_above_ema25'),
      'price_vs_ema99_bps':st.get('price_vs_ema99_bps'),'ema7_vs_ema25_bps':st.get('ema7_vs_ema25_bps'),
      'ema_long_context_score':int(bool(st.get('price_above_ema99')))+int(bool(st.get('ema7_above_ema25'))),
      'ema_short_context_score':int(st.get('price_above_ema99') is False)+int(st.get('ema7_above_ema25') is False),
      'live1m_start_ms':micro.get('live1m_start_ms'),'live1m_progress':micro.get('live1m_progress'),
      'live1m_complete_from_open':micro.get('live1m_complete_from_open'),'live1m_body_ratio':micro.get('live1m_body_ratio'),
      'live1m_long_direction_support':micro.get('live1m_long_direction_support'),'live1m_short_direction_support':micro.get('live1m_short_direction_support'),
      'live1m_long_retrace_ratio':micro.get('live1m_long_retrace_ratio'),'live1m_short_retrace_ratio':micro.get('live1m_short_retrace_ratio'),
      'live1m_long_location':micro.get('live1m_long_location'),'live1m_short_location':micro.get('live1m_short_location'),
      'oi_direction':oi.get('oi_direction'),'oi_ret_period':oi.get('oi_ret_period'),'oi_source_ts_ms':oi.get('source_ts_ms'),
      'structure_status':st.get('status'),'oi_status':oi.get('status'),'micro_event_age_sec':micro.get('event_age_sec')
    }

def main() -> int:
    ap=argparse.ArgumentParser(description='Shadow-only Binance Futures microstructure collector')
    ap.add_argument('--symbol',default='NEARUSDT'); ap.add_argument('--ttl-sec',type=int,default=10); ap.add_argument('--snapshot-sec',type=float,default=1.0); ap.add_argument('--telemetry-sec',type=float,default=30.0)
    a=ap.parse_args(); sym=a.symbol.upper(); low=sym.lower(); r=RedisConfig().client
    if r is None: raise SystemExit('redis_unavailable')
    streams=f'{low}@depth20@100ms/{low}@trade/{low}@bookTicker'; url=WS_BASE+streams
    depth: Dict[str,Any]={}; book: Dict[str,Any]={}; mark: Dict[str,Any]={}; live_candle: Dict[str,Any]={}; trades: Deque[Tuple[int,float,float,bool]]=deque(); exec_interval_trades: List[Tuple[int,float,float,bool]]=[]; last_emit=0.0; last_tel=0.0; last_mark=0.0
    print(f'START shadow-only microstructure symbol={sym}',flush=True)
    while True:
        try:
            ws=websocket.create_connection(url,timeout=10); ws.settimeout(2.0)
            print('WS_CONNECTED',flush=True)
            while True:
                try: raw=ws.recv()
                except Exception as e:
                    if 'timed out' in str(e).lower(): raw=None
                    else: raise
                now=time.time(); recv_ms=int(now*1000)
                if raw:
                    msg=json.loads(raw); stream=str(msg.get('stream') or ''); d=msg.get('data') or {}
                    if '@depth20' in stream: depth=d
                    elif '@bookTicker' in stream: book=d
                    elif '@trade' in stream:
                        trade_ms=int(d.get('T') or d.get('E') or recv_ms)
                        trade_px=_f(d.get('p')); trade_qty=_f(d.get('q')); trade_maker=bool(d.get('m'))
                        trades.append((trade_ms,trade_px,trade_qty,trade_maker))
                        exec_interval_trades.append((trade_ms,trade_px,trade_qty,trade_maker))
                        bucket=(trade_ms//60000)*60000
                        if int(live_candle.get('start_ms') or 0)!=bucket:
                            complete_from_open=bool(live_candle)
                            live_candle={'start_ms':bucket,'open':trade_px,'high':trade_px,'low':trade_px,'close':trade_px,'complete_from_open':complete_from_open}
                        else:
                            live_candle['high']=max(_f(live_candle.get('high'),trade_px),trade_px)
                            live_candle['low']=min(_f(live_candle.get('low'),trade_px),trade_px)
                            live_candle['close']=trade_px
                    cutoff=recv_ms-35000
                    while trades and trades[0][0]<cutoff: trades.popleft()
                if now-last_mark>=15.0:
                    try:
                        q=requests.get('https://fapi.binance.com/fapi/v1/premiumIndex',params={'symbol':sym},timeout=2.0).json()
                        mark={'E':recv_ms,'p':q.get('markPrice'),'i':q.get('indexPrice'),'r':q.get('lastFundingRate'),'T':q.get('nextFundingTime')}
                        last_mark=now
                    except Exception:
                        pass
                if depth and book and mark and now-last_emit>=a.snapshot_sec:
                    p=build_snapshot(sym,depth,book,mark,trades,recv_ms)
                    if live_candle:
                        p.update(_current_trade_candle_features(live_candle,int(p['observed_at_ms'])))
                    js=json.dumps(p,separators=(',',':'),sort_keys=True)
                    r.setex(f'shadow:market_context:microstructure:{sym}',a.ttl_sec,js)
                    # Integrity-safe execution interval: disjoint trades since the previous
                    # execution snapshot. Binance trade field m=True means buyer is maker,
                    # so the seller is aggressive (relevant for LONG bid fills).
                    buy_levels={}; sell_levels={}
                    for _tm,_px,_q,_m in exec_interval_trades:
                        if _q <= 0 or _px <= 0:
                            continue
                        target=sell_levels if _m else buy_levels
                        target[_px]=target.get(_px,0.0)+_q
                    # Cap retained price levels to control Redis/network cost. Dropped volume
                    # is ignored by research, making queue fill estimates conservative.
                    sell_items=sorted(sell_levels.items(), key=lambda z:z[0])[:20]
                    buy_items=sorted(buy_levels.items(), key=lambda z:z[0], reverse=True)[:20]
                    exec_l1={
                        'schema_version':2,'shadow_only':True,'symbol':sym,
                        'observed_at_ms':p.get('observed_at_ms'),
                        'best_bid':p.get('best_bid'),'best_ask':p.get('best_ask'),
                        'bid_qty_l1':p.get('bid_qty_l1'),'ask_qty_l1':p.get('ask_qty_l1'),
                        'mid':p.get('mid'),'spread_bps':p.get('spread_bps'),
                        # Legacy rolling t1 fields retained for backward compatibility only.
                        't1_count':p.get('t1_count'),'t1_qty':p.get('t1_qty'),
                        't1_min_price':p.get('t1_min_price'),'t1_max_price':p.get('t1_max_price'),
                        # Preferred execution-research fields: non-overlapping interval trades.
                        'interval_trade_count':len(exec_interval_trades),
                        'interval_buy_qty':sum(q for _,_,q,m in exec_interval_trades if not m),
                        'interval_sell_qty':sum(q for _,_,q,m in exec_interval_trades if m),
                        'interval_buy_levels':[[px,q] for px,q in buy_items],
                        'interval_sell_levels':[[px,q] for px,q in sell_items],
                        'interval_buy_levels_truncated':len(buy_levels)>20,
                        'interval_sell_levels_truncated':len(sell_levels)>20,
                    }
                    r.xadd('shadow:telemetry:execution_l1',{'symbol':sym,'json':json.dumps(exec_l1,separators=(',',':'),sort_keys=True)},maxlen=10000,approximate=True)
                    exec_interval_trades.clear()
                    last_emit=now
                    if now-last_tel>=a.telemetry_sec:
                        r.xadd('shadow:telemetry:microstructure',{'symbol':sym,'json':js},maxlen=20000,approximate=True)
                        ep=build_entry_context(r,sym,p); ejs=json.dumps(ep,separators=(',',':'),sort_keys=True)
                        r.xadd('shadow:telemetry:entry_context_research',{'symbol':sym,'json':ejs},maxlen=20000,approximate=True)
                        last_tel=now
                    print(f"OK spread={p['spread_bps']:.3f} basis={p['basis_bps']:.3f} funding={p['funding_rate']:.7f} l1={p['l1_imbalance']:.3f} d5={p['depth5_imbalance']:.3f} t15={p['t15_signed_ratio']:.3f} n15={p['t15_count']}",flush=True)
        except Exception as e:
            print(f'ERR type={type(e).__name__} msg={str(e)[:180]}',flush=True); time.sleep(3)
    return 0

if __name__=='__main__': raise SystemExit(main())
