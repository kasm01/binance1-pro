#!/usr/bin/env python3
"""Research-only LONG1 1m OHLC lifecycle bounds, NOT a fill-exact backtest."""
from __future__ import annotations
import bisect, json, math, time
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import redis

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/"research/data/NEARUSDT_1m_LIVE26_20261022_20261102.csv"
SIGNALS=ROOT/"research/results/LONG1_ALL_REAL_SIGNALS_CAUSAL_MARKOUT.csv"
OUTPUT=ROOT/"research/results"

LEV=3.0
ARM=.04
GIVEBACK=.0024
SL=.0299
CAT=.035
ROI_HARD=-.135
STALL_SEC=2400
STALL_PROFIT=.001
FEE=.0008

def build():
    d=pd.read_csv(DATA).sort_values("open_time").reset_index(drop=True)
    return {col:d[col].to_numpy() for col in ("open_time","close_time","open","high","low","close")}

def replay_market(arr, start_ms, entry, path="OHLC", max_eval_minutes=4320):
    times=arr["open_time"]; start=int(np.searchsorted(times,start_ms,side="left"))
    if start>=len(times):return None
    best_roi=0.0; best_ts=start_ms;stop_pending=None
    highest=entry
    end=min(len(times),start+max_eval_minutes)
    last_t=None;last_px=None
    for i in range(start,end):
        t0=int(times[i])
        if t0<start_ms:continue
        if i>start and t0-int(times[i-1])>60000:
            return dict(exit_reason="data_gap_censored",exit_t=last_t,exit_px=last_px,
                        best_roi=best_roi,entry_price=entry,minute_bars=i-start)
        op=float(arr["open"][i]); hi=float(arr["high"][i]);lo=float(arr["low"][i]);cl=float(arr["close"][i])
        # Four samples per 1m candle; OHLC order is unknown to historical 1m data.
        points=(op,hi,lo,cl) if path=="OHLC" else (op,lo,hi,cl)
        for j,px in enumerate(points):
            ts=t0+j*15000
            roi=(px/entry-1)*LEV
            if roi>best_roi:
                best_roi=roi
                best_ts=ts
                highest=max(highest,px)
            last_t=ts;last_px=px
            # Source code PRIORITY 1: lifecycle ROI exit.
            if roi<=ROI_HARD:
                return dict(exit_reason="roi_hard_stop_lifecycle",exit_t=ts,exit_px=px,
                            best_roi=best_roi,entry_price=entry,minute_bars=i-start+1)
            if best_roi>=ARM and roi<=best_roi-GIVEBACK:
                return dict(exit_reason="fixed_roi_tp_lifecycle_lock",exit_t=ts,exit_px=px,
                            best_roi=best_roi,entry_price=entry,minute_bars=i-start+1)
            # General lifecycle: dynamic stop -2.99% below entry; 30sec confirm or -3.5% catastrophe.
            if px<=entry*(1-SL):
                if px<=entry*(1-CAT):
                    reason="dynamic_stop_catastrophic"
                elif stop_pending is None:
                    stop_pending=ts;reason=None
                elif ts-stop_pending>=30000:
                    reason="dynamic_stop_confirmed"
                else:reason=None
                if reason:
                    return dict(exit_reason=reason,exit_t=ts,exit_px=px,best_roi=best_roi,
                                entry_price=entry,minute_bars=i-start+1)
            else:stop_pending=None
            # STALL requires CURRENT positive price PnL, NOT best pnl.
            if px/entry-1>=STALL_PROFIT and ts-best_ts>=STALL_SEC*1000:
                return dict(exit_reason="stall_exit",exit_t=ts,exit_px=px,
                            best_roi=best_roi,entry_price=entry,minute_bars=i-start+1)
    return dict(exit_reason="horizon_censored",exit_t=last_t,exit_px=last_px,
                best_roi=best_roi,entry_price=entry,minute_bars=end-start)

def simulate_policy(arr, signals, policy, path):
    occupied_until=-1;pending_until=-1;pending_origin=None
    trades=[];cnt=dict(flat_candidates=0,blocked_dual=0,pending=0,
                        recovery=0,expired=0,already_open=0,censored=0)
    for ev in signals.itertuples(index=False):
        t=int(ev.signal_ts_ms)
        if t<occupied_until:
            cnt["already_open"]+=1;continue
        if pending_until>0 and t>pending_until:
            cnt["expired"]+=1;pending_until=-1;pending_origin=None
        dual=bool(ev.dual_contra)
        if pending_until>0:
            if dual:continue
            if policy=="pending":
                cnt["recovery"]+=1;wait=(t-pending_origin)/60000
            else:wait=0.0
            pending_until=-1;pending_origin=None
        else:
            cnt["flat_candidates"]+=1;wait=0.0
            if dual and policy=="skip":
                cnt["blocked_dual"]+=1;continue
            if dual and policy=="pending":
                cnt["pending"]+=1;pending_until=t+1800000;pending_origin=t
                continue
        start=int(np.searchsorted(arr["open_time"],t,side="right"))
        if start>=len(arr["open_time"]):continue
        if int(arr["open_time"][start])-t>120000:continue
        ep=float(arr["open"][start]);entry_time=int(arr["open_time"][start])
        x=replay_market(arr,entry_time,ep,path)
        if x is None:continue
        if "censored" in x["exit_reason"]:
            cnt["censored"]+=1
            # Do not count unclosed/censored trade as realized PnL.
            occupied_until=(int(x["exit_t"]) if x["exit_t"] else entry_time)+1
            continue
        xp=float(x["exit_px"]);fee=FEE*ep
        # Equal-notional return, fee applied as 0.08% of notional.
        ret=(xp-ep)/ep-FEE
        trades.append(dict(policy=policy,path=path,signal_id=ev.signal_id,
           signal_ts_ms=t,entry_ms=entry_time,exit_ms=int(x["exit_t"]),
           entry_price=ep,exit_price=xp,
           context_dual=dual,pending_wait_min=wait,
           model_score=ev.model_score,net_return_pct=100*ret,
           net_roi_on_margin_pct=100*LEV*ret,
           gross_return_pct=100*(xp-ep)/ep,
           fee_notional_pct=FEE*100,
           best_roi_pct=100*x["best_roi"],
           exit_reason=x["exit_reason"],hold_min=(x["exit_t"]-entry_time)/60000))
        occupied_until=int(x["exit_t"])+1
    return pd.DataFrame(trades),cnt

def main():
    arr=build()
    signals=pd.read_csv(SIGNALS).sort_values("signal_ts_ms")
    out=[]
    for path in ("OHLC","OLHC"):
        print("\nPATH ASSUMPTION",path)
        for policy in ("base","skip","pending"):
            trades,counts=simulate_policy(arr,signals,policy,path)
            if len(trades):
                out.append(trades)
                wins=trades[trades.net_return_pct>0].net_return_pct.sum()
                losses=-trades[trades.net_return_pct<0].net_return_pct.sum()
                print(policy,"N",len(trades),
                      "sum_equal_notional_pctpt",round(trades.net_return_pct.sum(),3),
                      "avg_net_pct",round(trades.net_return_pct.mean(),4),
                      "win_pct",round((trades.net_return_pct>0).mean()*100,2),
                      "PF",round(wins/losses,3) if losses else None,
                      "exit_counts",trades.exit_reason.value_counts().to_dict(),
                      "mean_hold_min",round(trades.hold_min.mean(),2),
                      "mean_wait_min",round(trades.pending_wait_min.mean(),2),
                      "cost_notional_pctpt",round(FEE*100*len(trades),2),
                      "counters",counts)
            else:print(policy,"no settled trades",counts)
    if out:
        df=pd.concat(out,ignore_index=True)
        f=OUTPUT/"LONG1_REAL_SIGNALS_LIFECYCLE_1M_BOUNDS.csv"
        df.to_csv(f,index=False)
        print("CSV",f)
if __name__=="__main__":main()
