from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig

ANCHOR_STREAM='shadow:telemetry:execution_compare_anchor'
L1_STREAM='shadow:telemetry:execution_l1'
OUTCOME_STREAM='shadow:telemetry:position_outcome'
WAIT_SECS=(1,2,3)
QUEUE_MULTS=(0.5,1.0,2.0)
MAKER_FEE_BPS=(0.0,2.0,4.0)
TAKER_FEE_BPS=4.0
TOUCH_VOLUME_HAIRCUT=0.50
MAX_LAG_MS=1800


def _loads(fields):
    try:return json.loads(fields.get('json') or '{}')
    except Exception:return {}


def _stream_json(r,stream,count=20000):
    out=[]
    for _,f in r.xrevrange(stream,count=count):
        d=_loads(f)
        if isinstance(d,dict): out.append(d)
    return list(reversed(out))


def _rows(r,stream,count=20000):
    out=[]
    for d in _stream_json(r,stream,count):
        if d.get('observed_at_ms') is not None: out.append(d)
    if not out:return pd.DataFrame()
    x=pd.DataFrame(out).drop_duplicates('observed_at_ms').sort_values('observed_at_ms')
    for c in ['observed_at_ms','best_bid','best_ask','bid_qty_l1','ask_qty_l1','mid','t1_qty','t1_min_price','t1_max_price']:
        if c in x:x[c]=pd.to_numeric(x[c],errors='coerce')
    return x.reset_index(drop=True)


def _anchors(r,count=10000):
    return [d for d in _stream_json(r,ANCHOR_STREAM,count) if d.get('opened_ms') is not None]


def _outcomes_by_trade(r,count=10000):
    out={}
    for d in _stream_json(r,OUTCOME_STREAM,count):
        tid=str(d.get('trade_id') or d.get('intent_id') or '').strip()
        if tid: out[tid]=d
    return out


def _at_or_after(g,target):
    z=g[g.observed_at_ms>=target]
    if z.empty:return None
    row=z.iloc[0]
    return None if row.observed_at_ms-target>MAX_LAG_MS else row


def _level_qty(levels,side,limit_px):
    total=0.0
    if not isinstance(levels,list): return 0.0
    for item in levels:
        if not isinstance(item,(list,tuple)) or len(item)<2: continue
        try: px=float(item[0]); q=float(item[1])
        except Exception: continue
        if px<=0 or q<=0: continue
        if side=='long' and px<=limit_px: total+=q
        elif side=='short' and px>=limit_px: total+=q
    return total


def _fill(window,side,limit_px,queue_ahead,qm,order_qty):
    if order_qty<=0 or queue_ahead<=0:return np.nan
    touch_qty=0.0
    col='interval_sell_levels' if side=='long' else 'interval_buy_levels'
    for _,row in window.iterrows():
        touch_qty += _level_qty(row.get(col),side,limit_px)
    available=max(touch_qty*TOUCH_VOLUME_HAIRCUT-queue_ahead*qm,0.0)
    return float(np.clip(available/order_qty,0.0,1.0))


def _entry_edge_bps(side,ref_mid,px,fee_bps):
    edge=((ref_mid-px)/ref_mid*1e4) if side=='long' else ((px-ref_mid)/ref_mid*1e4)
    return float(edge-fee_bps)


def _gross_pnl(side,entry_px,exit_px,qty):
    if side=='long': return (exit_px-entry_px)*qty
    return (entry_px-exit_px)*qty


def _shadow_net(side,entry_px,exit_px,qty,entry_fee_bps,exit_fee_rate,slippage_bps):
    entry_notional=abs(entry_px*qty); exit_notional=abs(exit_px*qty)
    gross=_gross_pnl(side,entry_px,exit_px,qty)
    entry_fee=entry_notional*(entry_fee_bps/10000.0)
    exit_fee=exit_notional*exit_fee_rate
    slip=(entry_notional+exit_notional)*(slippage_bps/10000.0)
    net=gross-entry_fee-exit_fee-slip
    ret=net/entry_notional if entry_notional>0 else np.nan
    return gross,net,ret


def main():
    r=RedisConfig().client
    anchors=_anchors(r); l1=_rows(r,L1_STREAM); outcomes=_outcomes_by_trade(r)
    print('compare_anchors',len(anchors),'l1_rows',len(l1),'outcomes',len(outcomes))
    if not anchors or l1.empty:
        print('NO_LIVE_EXECUTION_COMPARE_DATA'); return
    rec=[]
    matched_outcomes=0
    for a in anchors:
        side=str(a.get('side') or '').lower(); sym=str(a.get('symbol') or '').upper()
        if side not in ('long','short'):continue
        tid=str(a.get('trade_id') or a.get('intent_id') or '').strip()
        t0=int(a.get('opened_ms') or 0); actual_px=float(a.get('actual_fill_price') or 0); qty=float(a.get('actual_qty') or 0)
        ref_mid=float(a.get('mid') or 0); bid=float(a.get('best_bid') or 0); ask=float(a.get('best_ask') or 0)
        qraw=a.get('bid_qty_l1') if side=='long' else a.get('ask_qty_l1')
        queue=float(qraw or 0)
        if min(t0,actual_px,qty,ref_mid,bid,ask)<=0:continue
        oc=outcomes.get(tid)
        if oc: matched_outcomes+=1
        exit_px=float((oc or {}).get('close_price') or 0)
        lev=float((oc or {}).get('leverage') or a.get('actual_leverage') or 1.0)
        actual_net=float((oc or {}).get('net_pnl_usdt_est') or np.nan)
        actual_roi=float((oc or {}).get('net_roi_pct_est') or np.nan)
        fee_rate=float((oc or {}).get('estimated_fee_rate') or TAKER_FEE_BPS/10000.0)
        slip_bps=float((oc or {}).get('estimated_slippage_bps') or 0.0)
        g=l1[(l1.observed_at_ms>=t0-1000)&(l1.observed_at_ms<=t0+20000)]
        actual_edge=_entry_edge_bps(side,ref_mid,actual_px,TAKER_FEE_BPS)
        limit_px=bid if side=='long' else ask
        for wait in WAIT_SECS:
            deadline=t0+wait*1000; fb=_at_or_after(g,deadline)
            if fb is None:continue
            fallback_px=float(fb.best_ask if side=='long' else fb.best_bid)
            window=g[(g.observed_at_ms>t0)&(g.observed_at_ms<=deadline+300)]
            for qm in QUEUE_MULTS:
                ff=_fill(window,side,limit_px,queue,qm,qty)
                if not np.isfinite(ff):continue
                for mf in MAKER_FEE_BPS:
                    rem=1-ff; eff_px=limit_px*ff+fallback_px*rem; eff_fee_bps=mf*ff+TAKER_FEE_BPS*rem
                    shadow_edge=_entry_edge_bps(side,ref_mid,eff_px,eff_fee_bps)
                    row={'trade_id':tid,'intent_id':a.get('intent_id'),'symbol':sym,'side':side,
                         'opened_ms':t0,'actual_fill_price':actual_px,'actual_qty':qty,'wait_s':wait,'queue_mult':qm,
                         'maker_fee_bps':mf,'fill_fraction':ff,'shadow_entry_price':eff_px,
                         'effective_entry_fee_bps':eff_fee_bps,'actual_market_edge_bps':actual_edge,
                         'shadow_edge_bps':shadow_edge,'shadow_advantage_vs_actual_bps':shadow_edge-actual_edge,
                         'outcome_matched':bool(oc),'actual_exit_price':exit_px if exit_px>0 else np.nan,
                         'actual_net_pnl_usdt_est':actual_net,'actual_net_roi_pct_est':actual_roi}
                    if oc and exit_px>0:
                        sg,sn,sret=_shadow_net(side,eff_px,exit_px,qty,eff_fee_bps,fee_rate,slip_bps)
                        row.update({'shadow_gross_pnl_usdt_est':sg,'shadow_net_pnl_usdt_est':sn,
                                    'shadow_net_return_pct_est':sret,'shadow_net_roi_pct_est':sret*lev,
                                    'net_pnl_delta_usdt_vs_actual':sn-actual_net if np.isfinite(actual_net) else np.nan,
                                    'net_roi_delta_pct_vs_actual':sret*lev-actual_roi if np.isfinite(actual_roi) else np.nan,
                                    'close_reason':oc.get('close_reason','')})
                    rec.append(row)
    df=pd.DataFrame(rec)
    out=ROOT/'research/results/NEAR_LIVE_EXECUTION_COMPARE.csv'; out.parent.mkdir(parents=True,exist_ok=True); df.to_csv(out,index=False)
    if df.empty:
        print('NO_MATCHED_COMPARE_ROWS'); return
    agg={'trades':('trade_id','nunique'),'avg_fill_fraction':('fill_fraction','mean'),
         'avg_advantage_bps':('shadow_advantage_vs_actual_bps','mean'),
         'median_advantage_bps':('shadow_advantage_vs_actual_bps','median'),
         'outcome_trades':('outcome_matched','sum')}
    if 'net_pnl_delta_usdt_vs_actual' in df.columns:
        agg.update({'avg_net_pnl_delta_usdt':('net_pnl_delta_usdt_vs_actual','mean'),
                    'median_net_pnl_delta_usdt':('net_pnl_delta_usdt_vs_actual','median'),
                    'avg_net_roi_delta_pct':('net_roi_delta_pct_vs_actual','mean')})
    s=df.groupby(['side','wait_s','queue_mult','maker_fee_bps'],as_index=False).agg(**agg)
    sout=ROOT/'research/results/NEAR_LIVE_EXECUTION_COMPARE_SUMMARY.csv'; s.to_csv(sout,index=False)
    print('matched_outcome_anchors',matched_outcomes)
    print(s.sort_values('avg_advantage_bps',ascending=False).head(20).to_string(index=False))
    print('out',out); print('summary',sout)

if __name__=='__main__':main()
