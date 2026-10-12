from __future__ import annotations
import json, sys, os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config.redis_config import RedisConfig

STREAM='shadow:telemetry:execution_l1'
SYMBOL='NEARUSDT'
WAIT_SECS=(1,2,3)
TAKER_BPS=4.0
MAKER_BPS_SCENARIOS=(0.0,2.0,4.0)
QUEUE_MULTS=(0.5,1.0,2.0)
TOUCH_VOLUME_HAIRCUT=0.50
ANCHOR_GAP_MS=10000
SESSION_GAP_MS=120000
VALIDATION_BLOCK_MS=6*60*60*1000
MIN_ANCHORS=30
MARKOUT_SECS=(5,15)

def _notional_scenarios():
    raw=os.getenv('SHADOW_EXECUTION_NOTIONALS_USDT','25,50,100')
    out=[]
    for x in str(raw).split(','):
        try:
            v=float(x.strip())
            if v>0: out.append(v)
        except Exception:
            pass
    return tuple(out or (25.0,50.0,100.0))

NOTIONAL_SCENARIOS=_notional_scenarios()


def load_rows(r,count=20000):
    rows=[]
    for _,f in r.xrevrange(STREAM,count=count):
        try:d=json.loads(f.get('json') or '{}')
        except Exception:continue
        if str(d.get('symbol') or '').upper()!=SYMBOL: continue
        if int(d.get('schema_version') or 0) < 2: continue
        if d.get('observed_at_ms') is None: continue
        rows.append(d)
    if not rows:return pd.DataFrame()
    df=pd.DataFrame(rows).drop_duplicates('observed_at_ms').sort_values('observed_at_ms')
    nums=['observed_at_ms','best_bid','best_ask','bid_qty_l1','ask_qty_l1','mid','spread_bps','t1_count','t1_qty','t1_min_price','t1_max_price']
    for c in nums:
        if c in df: df[c]=pd.to_numeric(df[c],errors='coerce')
    req=['observed_at_ms','best_bid','best_ask','bid_qty_l1','ask_qty_l1','mid','t1_qty']
    df=df.dropna(subset=[c for c in req if c in df.columns]).reset_index(drop=True)
    if df.empty:return df
    gap=df.observed_at_ms.diff().fillna(0)
    # continuity_id prevents forward/markout joins from crossing collector downtime.
    df['session_id']=(gap>SESSION_GAP_MS).cumsum().astype(int)
    # validation_block_id is research-only segmentation, NOT a trading-hour gate.
    # It lets 24/7 continuous collection accumulate independent temporal blocks.
    df['validation_block_id']=(df.observed_at_ms//VALIDATION_BLOCK_MS).astype('int64')
    return df


def anchors(df):
    keep=[]
    for _,g in df.groupby('session_id',sort=False):
        last=None
        for i,t in zip(g.index,g.observed_at_ms):
            if last is None or t-last>=ANCHOR_GAP_MS:
                keep.append(i); last=t
    return df.loc[keep].copy()


def at_or_after(g,target_ms,max_lag_ms=1800):
    x=g[g.observed_at_ms>=target_ms]
    if x.empty:return None
    row=x.iloc[0]
    if row.observed_at_ms-target_ms>max_lag_ms:return None
    return row


def _level_qty(levels, side, limit_px):
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


def queue_diagnostics(window,side,limit_px,queue_ahead,queue_mult,order_qty):
    if window.empty or not np.isfinite(queue_ahead) or queue_ahead<=0 or not np.isfinite(order_qty) or order_qty<=0:
        return {'fill_fraction':np.nan}
    level_col='interval_sell_levels' if side=='long' else 'interval_buy_levels'
    book_px_col='best_bid' if side=='long' else 'best_ask'
    book_qty_col='bid_qty_l1' if side=='long' else 'ask_qty_l1'
    touch_qty=0.0
    visible_cancel_qty=0.0
    visible_replenish_qty=0.0
    price_through=False
    prev_qty=float(queue_ahead)
    prev_at_limit=True
    for _,row in window.iterrows():
        traded=_level_qty(row.get(level_col), side, limit_px)
        touch_qty += traded
        try:
            px=float(row.get(book_px_col)); q=float(row.get(book_qty_col))
        except Exception:
            continue
        at_limit=np.isfinite(px) and np.isfinite(q) and abs(px-limit_px)<=1e-12 and q>=0
        if side=='long':
            price_through = price_through or (np.isfinite(float(row.get('best_ask'))) and float(row.get('best_ask'))<=limit_px)
        else:
            price_through = price_through or (np.isfinite(float(row.get('best_bid'))) and float(row.get('best_bid'))>=limit_px)
        if at_limit and prev_at_limit:
            expected_after_trade=max(prev_qty-traded,0.0)
            if q < expected_after_trade:
                visible_cancel_qty += expected_after_trade-q
            elif q > expected_after_trade:
                visible_replenish_qty += q-expected_after_trade
            prev_qty=q
        elif at_limit:
            prev_qty=q
        prev_at_limit=at_limit
    effective_touch=touch_qty*TOUCH_VOLUME_HAIRCUT
    queue_needed=max(queue_ahead*queue_mult,0.0)
    qty_available_for_us=max(effective_touch-queue_needed,0.0)
    maker_filled_qty=min(qty_available_for_us,order_qty)
    fill_fraction=float(np.clip(maker_filled_qty/max(order_qty,1e-12),0.0,1.0))
    return {
        'fill_fraction':fill_fraction,
        'touch_qty_raw':float(touch_qty),
        'effective_touch_qty':float(effective_touch),
        'visible_cancel_qty':float(visible_cancel_qty),
        'visible_replenish_qty':float(visible_replenish_qty),
        'price_through':bool(price_through),
        'queue_needed_qty':float(queue_needed),
    }


def market_edge_bps(side,ref_mid,entry_px,fee_bps):
    px_edge=((ref_mid-entry_px)/ref_mid*1e4) if side=='long' else ((entry_px-ref_mid)/ref_mid*1e4)
    return float(px_edge-fee_bps)


def bootstrap_ci(x,seed=42,n_boot=2000):
    x=np.asarray(x,dtype=float); x=x[np.isfinite(x)]
    if len(x)<20:return (np.nan,np.nan)
    rng=np.random.default_rng(seed)
    means=np.empty(n_boot)
    for i in range(n_boot):means[i]=rng.choice(x,size=len(x),replace=True).mean()
    return tuple(np.quantile(means,[.025,.975]))


def main():
    r=RedisConfig().client; df=load_rows(r)
    print('queue_rows',len(df),'sessions',df.session_id.nunique() if len(df) else 0)
    if len(df)<30:
        for name in ('NEAR_SHADOW_EXECUTION_QUEUE.csv','NEAR_SHADOW_EXECUTION_QUEUE_SUMMARY.csv','NEAR_SHADOW_EXECUTION_QUEUE_ROBUST.csv'):
            q=ROOT/'research/results'/name
            if q.exists(): q.unlink()
        print('INSUFFICIENT_QUEUE_DATA_V2'); return
    anc=anchors(df); rec=[]
    for _,a in anc.iterrows():
        g=df[df.session_id==a.session_id]
        t0=float(a.observed_at_ms); bid=float(a.best_bid); ask=float(a.best_ask); mid=float(a.mid)
        if min(bid,ask,mid)<=0:continue
        for side in ('long','short'):
            market_px=ask if side=='long' else bid
            market_now=market_edge_bps(side,mid,market_px,TAKER_BPS)
            limit_px=bid if side=='long' else ask
            queue_ahead=float(a.bid_qty_l1 if side=='long' else a.ask_qty_l1)
            for wait in WAIT_SECS:
                deadline=t0+wait*1000
                window=g[(g.observed_at_ms>t0)&(g.observed_at_ms<=deadline+300)]
                fb=at_or_after(g,deadline)
                if fb is None:continue
                fallback_px=float(fb.best_ask if side=='long' else fb.best_bid)
                deadline_mid=float(fb.mid)
                markouts={}
                for ms in MARKOUT_SECS:
                    future=at_or_after(g,deadline+ms*1000)
                    if future is None:
                        markouts[ms]=np.nan
                        continue
                    future_mid=float(future.mid)
                    signed=(future_mid-deadline_mid)/max(deadline_mid,1e-12)*1e4
                    if side=='short': signed=-signed
                    markouts[ms]=float(signed)
                for notional_usdt in NOTIONAL_SCENARIOS:
                    order_qty=float(notional_usdt)/max(limit_px,1e-12)
                    for qm in QUEUE_MULTS:
                        qdiag=queue_diagnostics(window,side,limit_px,queue_ahead,qm,order_qty)
                        fill_frac=qdiag.get('fill_fraction',np.nan)
                        if not np.isfinite(fill_frac):continue
                        fill_frac_upper=1.0 if bool(qdiag.get('price_through',False)) else float(fill_frac)
                        queue_uncertainty=max(0.0,float(fill_frac_upper)-float(fill_frac))
                        fallback_only_edge=market_edge_bps(side,mid,fallback_px,TAKER_BPS)
                        wait_timing_bps=fallback_only_edge-market_now
                        for maker_fee in MAKER_BPS_SCENARIOS:
                            rem=1.0-fill_frac
                            eff_px=limit_px*fill_frac+fallback_px*rem
                            eff_fee=maker_fee*fill_frac+TAKER_BPS*rem
                            strategy=market_edge_bps(side,mid,eff_px,eff_fee)
                            maker_incremental_bps=strategy-fallback_only_edge
                            rec.append({
                                'session_id':int(a.session_id),'validation_block_id':int(a.validation_block_id),
                                'anchor_ms':int(t0),'side':side,'wait_s':wait,
                                'notional_usdt':float(notional_usdt),'order_qty':float(order_qty),
                                'order_to_queue_ratio':float(order_qty/max(queue_ahead,1e-12)),
                                'queue_mult':qm,'maker_fee_bps':maker_fee,'fill_fraction':fill_frac,
                                'fill_fraction_upper':fill_frac_upper,
                                'queue_fill_uncertainty':queue_uncertainty,
                                'queue_ahead_qty':queue_ahead,
                                'touch_qty_raw':qdiag.get('touch_qty_raw',np.nan),
                                'effective_touch_qty':qdiag.get('effective_touch_qty',np.nan),
                                'visible_cancel_qty':qdiag.get('visible_cancel_qty',np.nan),
                                'visible_replenish_qty':qdiag.get('visible_replenish_qty',np.nan),
                                'price_through':bool(qdiag.get('price_through',False)),
                                'queue_needed_qty':qdiag.get('queue_needed_qty',np.nan),
                                'market_now_edge_bps':market_now,
                                'strategy_edge_bps':strategy,'advantage_vs_market_bps':strategy-market_now,
                                'fallback_only_edge_bps':fallback_only_edge,
                                'wait_timing_bps':wait_timing_bps,
                                'maker_incremental_bps':maker_incremental_bps,
                                'post_wait_markout_5s_bps':markouts.get(5,np.nan),
                                'post_wait_markout_15s_bps':markouts.get(15,np.nan),
                                'maker_weighted_markout_5s_bps':fill_frac*markouts.get(5,np.nan) if np.isfinite(markouts.get(5,np.nan)) else np.nan,
                                'maker_weighted_markout_15s_bps':fill_frac*markouts.get(15,np.nan) if np.isfinite(markouts.get(15,np.nan)) else np.nan,
                            })
    x=pd.DataFrame(rec)
    out=ROOT/'research/results/NEAR_SHADOW_EXECUTION_QUEUE.csv'; out.parent.mkdir(parents=True,exist_ok=True); x.to_csv(out,index=False)
    if x.empty:
        print('NO_QUEUE_ROWS');return
    rows=[]
    for keys,g in x.groupby(['side','wait_s','notional_usdt','queue_mult','maker_fee_bps']):
        side,wait,notional,qm,mf=keys; vals=g.advantage_vs_market_bps.to_numpy(float)
        lo,hi=bootstrap_ci(vals,seed=100+int(wait*10+qm*10+mf))
        n=int(g.anchor_ms.nunique()); sessions=int(g.validation_block_id.nunique())
        continuity_segments=int(g.session_id.nunique())
        status='INSUFFICIENT_ANCHORS' if n<MIN_ANCHORS else ('OBSERVE' if not np.isfinite(lo) or lo<=0 else 'PRELIMINARY')
        rows.append({'side':side,'wait_s':wait,'notional_usdt':float(notional),'queue_mult':qm,'maker_fee_bps':mf,
                     'n':n,'sessions':sessions,'continuity_segments':continuity_segments,
                     'avg_order_qty':float(g.order_qty.mean()),'avg_order_to_queue_ratio':float(g.order_to_queue_ratio.mean()),
                     'avg_fill_fraction':float(g.fill_fraction.mean()),
                     'avg_fill_fraction_upper':float(g.fill_fraction_upper.mean()),
                     'avg_queue_fill_uncertainty':float(g.queue_fill_uncertainty.mean()),
                     'full_fill_pct':float((g.fill_fraction>=.999).mean()*100),
                     'upper_full_fill_pct':float((g.fill_fraction_upper>=.999).mean()*100),
                     'avg_touch_qty_raw':float(g.touch_qty_raw.mean()),
                     'avg_visible_cancel_qty':float(g.visible_cancel_qty.mean()),
                     'avg_visible_replenish_qty':float(g.visible_replenish_qty.mean()),
                     'price_through_pct':float(g.price_through.mean()*100),
                     'avg_advantage_bps':float(np.mean(vals)),'adv_ci95_lo_bps':lo,'adv_ci95_hi_bps':hi,
                     'avg_wait_timing_bps':float(g.wait_timing_bps.mean()),
                     'avg_maker_incremental_bps':float(g.maker_incremental_bps.mean()),
                     'avg_post_wait_markout_5s_bps':float(g.post_wait_markout_5s_bps.mean()),
                     'avg_post_wait_markout_15s_bps':float(g.post_wait_markout_15s_bps.mean()),
                     'avg_maker_weighted_markout_5s_bps':float(g.maker_weighted_markout_5s_bps.mean()),
                     'avg_maker_weighted_markout_15s_bps':float(g.maker_weighted_markout_15s_bps.mean()),
                     'status':status})
    s=pd.DataFrame(rows)
    sout=ROOT/'research/results/NEAR_SHADOW_EXECUTION_QUEUE_SUMMARY.csv'; s.to_csv(sout,index=False)

    robust=[]
    for keys,g in s.groupby(['side','wait_s','queue_mult','maker_fee_bps']):
        side,wait,qm,mf=keys
        required=set(float(x) for x in NOTIONAL_SCENARIOS)
        present=set(float(x) for x in g.notional_usdt.tolist())
        complete=required.issubset(present)
        robust.append({
            'side':side,'wait_s':wait,'queue_mult':qm,'maker_fee_bps':mf,
            'notional_count':int(g.notional_usdt.nunique()),
            'min_notional_usdt':float(g.notional_usdt.min()),'max_notional_usdt':float(g.notional_usdt.max()),
            'n_min':int(g.n.min()),'sessions_min':int(g.sessions.min()),
            'worst_avg_advantage_bps':float(g.avg_advantage_bps.min()),
            'worst_avg_wait_timing_bps':float(g.avg_wait_timing_bps.min()),
            'worst_avg_maker_incremental_bps':float(g.avg_maker_incremental_bps.min()),
            'worst_ci95_lo_bps':float(g.adv_ci95_lo_bps.min()) if g.adv_ci95_lo_bps.notna().all() else np.nan,
            'min_avg_fill_fraction':float(g.avg_fill_fraction.min()),
            'min_avg_fill_fraction_upper':float(g.avg_fill_fraction_upper.min()),
            'max_avg_queue_fill_uncertainty':float(g.avg_queue_fill_uncertainty.max()),
            'max_order_to_queue_ratio':float(g.avg_order_to_queue_ratio.max()),
            'worst_avg_maker_weighted_markout_5s_bps':float(g.avg_maker_weighted_markout_5s_bps.min()),
            'worst_avg_maker_weighted_markout_15s_bps':float(g.avg_maker_weighted_markout_15s_bps.min()),
            'size_scenarios_complete':bool(complete),
        })
    rs=pd.DataFrame(robust)

    # Temporal stability: within each 6h validation block, take the worst size scenario.
    # This prevents one strong period or one favorable order size from dominating promotion.
    block_rows=[]
    for keys,g0 in x.groupby(['side','wait_s','queue_mult','maker_fee_bps','validation_block_id']):
        side,wait,qm,mf,vbid=keys
        per_size=[]
        for notional,gn in g0.groupby('notional_usdt'):
            per_size.append({
                'notional_usdt':float(notional),
                'adv':float(gn.advantage_vs_market_bps.mean()),
                'm5':float(gn.maker_weighted_markout_5s_bps.mean()),
                'm15':float(gn.maker_weighted_markout_15s_bps.mean()),
                'anchors':int(gn.anchor_ms.nunique()),
            })
        pg=pd.DataFrame(per_size)
        required=set(float(v) for v in NOTIONAL_SCENARIOS)
        complete=required.issubset(set(pg.notional_usdt.tolist())) if len(pg) else False
        if not complete: continue
        block_rows.append({
            'side':side,'wait_s':wait,'queue_mult':qm,'maker_fee_bps':mf,
            'validation_block_id':int(vbid),
            'block_worst_advantage_bps':float(pg.adv.min()),
            'block_worst_markout_5s_bps':float(pg.m5.min()),
            'block_worst_markout_15s_bps':float(pg.m15.min()),
            'block_min_anchors':int(pg.anchors.min()),
        })
    br=pd.DataFrame(block_rows)
    if len(br):
        stab=[]
        for keys,g in br.groupby(['side','wait_s','queue_mult','maker_fee_bps']):
            side,wait,qm,mf=keys
            stab.append({
                'side':side,'wait_s':wait,'queue_mult':qm,'maker_fee_bps':mf,
                'validation_blocks':int(g.validation_block_id.nunique()),
                'positive_block_pct':float((g.block_worst_advantage_bps>0).mean()*100.0),
                'safe_markout5_block_pct':float((g.block_worst_markout_5s_bps>=0).mean()*100.0),
                'safe_markout15_block_pct':float((g.block_worst_markout_15s_bps>=0).mean()*100.0),
                'worst_block_advantage_bps':float(g.block_worst_advantage_bps.min()),
                'median_block_advantage_bps':float(g.block_worst_advantage_bps.median()),
            })
        st=pd.DataFrame(stab)
        rs=rs.merge(st,on=['side','wait_s','queue_mult','maker_fee_bps'],how='left')
    else:
        for c in ('validation_blocks','positive_block_pct','safe_markout5_block_pct','safe_markout15_block_pct','worst_block_advantage_bps','median_block_advantage_bps'):
            rs[c]=np.nan

    rs['status']=np.where(
        (~rs.size_scenarios_complete)|(rs.n_min<MIN_ANCHORS),
        'INSUFFICIENT_SIZE_ROBUST',
        np.where((rs.worst_avg_advantage_bps>0)&(rs.worst_ci95_lo_bps>0),'PRELIMINARY','OBSERVE')
    )
    rsout=ROOT/'research/results/NEAR_SHADOW_EXECUTION_QUEUE_ROBUST.csv'; rs.to_csv(rsout,index=False)

    print(s.sort_values('avg_advantage_bps',ascending=False).head(30).to_string(index=False))
    print('\nSIZE_ROBUST')
    print(rs.sort_values('worst_avg_advantage_bps',ascending=False).head(20).to_string(index=False))
    print('out',out); print('summary',sout); print('robust',rsout)

if __name__=='__main__':main()
