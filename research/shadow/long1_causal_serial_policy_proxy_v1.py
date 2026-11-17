#!/usr/bin/env python3
"""Time-ordered fixed-horizon *proxy*, never a production trade backtest."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/"research/results/LONG1_ALL_REAL_SIGNALS_CAUSAL_MARKOUT.csv"
OUT=ROOT/"research/results"

def simulate(data,hold_minutes=60,pending_minutes=30,filter_mode="none"):
    x=data.sort_values("signal_ts_ms").reset_index(drop=True)
    open_after_ms=-1
    pending_until=-1
    pending_from=None
    selected=[]
    counters=dict(seeds=0,pending=0,revalidated=0,expired=0,
                  ignored_busy=0,abandoned_end=0)
    for _,r in x.iterrows():
        now=int(r.signal_ts_ms)
        if now < open_after_ms:
            counters["ignored_busy"]+=1
            continue
        if pending_until>0 and now>pending_until:
            counters["expired"]+=1
            pending_until=-1
            pending_from=None

        dual=bool(r.dual_contra)
        if pending_until>0:
            if dual:
                continue
            if not bool(r[f"valid_{hold_minutes}m"]):
                continue
            counters["revalidated"]+=1
            origin=pending_from
            pending_until=-1
            pending_from=None
            tag="PENDING_RECOVERY"
        else:
            counters["seeds"]+=1
            if filter_mode=="pending" and dual:
                pending_until=now+pending_minutes*60000
                pending_from=now
                counters["pending"]+=1
                continue
            if filter_mode=="skip" and dual:
                continue
            if not bool(r[f"valid_{hold_minutes}m"]):
                continue
            origin=None
            tag="IMMEDIATE"

        selected.append(dict(time_ms=now,entry_price=r.assumed_next_1m_open,
            signal_id=r.signal_id,market=r.market,flow=r.flow,dual=dual,
            entry_kind=tag,pending_origin_ms=origin,
            wait_min=round((now-origin)/60000,3) if origin else 0.0,
            net_return_pct=float(r[f"net_return_{hold_minutes}m_pct"]),
            net_roi_pct=float(r[f"net_roi_{hold_minutes}m_pct"]),
            source="1m_OHLC_next_min_open_fixed_horizon_fee_proxy"))
        # New positions cannot open until the fixed hold horizon finishes.
        # This is an artificial one-position constraint for scenario comparability.
        open_after_ms=now+hold_minutes*60000
    if pending_until>0:
        counters["abandoned_end"]+=1
    d=pd.DataFrame(selected)
    return d,counters

def summary(rows):
    if rows.empty:return {"n":0,"net_equal_notional_pct":0.0,"positive_pct":None}
    return {"n":len(rows),
            "net_equal_notional_pct":round(rows.net_return_pct.sum(),4),
            "avg_net_return_pct":round(rows.net_return_pct.mean(),4),
            "positive_pct":round(100*(rows.net_return_pct>0).mean(),2),
            "worst_trade_pct":round(rows.net_return_pct.min(),4),
            "wait_mean_min":round(rows.wait_min.mean(),3)}

def main():
    d=pd.read_csv(DATA)
    # Avoid accidental integer/float nan conversion to truthy.
    for h in (15,30,60):
        d[f"valid_{h}m"]=d[f"valid_{h}m"].fillna(False).astype(bool)
    print("INPUT unique3m",len(d),"DUAL",int(d.dual_contra.sum()))
    allrows=[]
    for hold in (15,30,60):
        print("\nFIXED HORIZON",hold,"minutes - one open position max; 0.08% roundtrip notional fee")
        scenarios={}
        for policy in ("none","skip","pending"):
            r,counts=simulate(d,hold_minutes=hold,pending_minutes=30,filter_mode=policy)
            scenarios[policy]=r
            print(policy,summary(r),"counts",counts)
            if not r.empty:
                r["policy"]=policy
                r["hold_minutes"]=hold
                allrows.append(r)
        # Paired calendar-day summary: both strategies measured on same window, but different entries.
        for label,fr in scenarios.items():
            if fr.empty:continue
            x=fr.copy()
            x["day"]=pd.to_datetime(x.time_ms,unit="ms",utc=True).dt.strftime("%Y-%m-%d")
            days=x.groupby("day").net_return_pct.sum()
            print("  days",label,"n",len(days),"negative",int((days<0).sum()),
                  "worst_day_equal_notional_pct",round(days.min(),4))
    if allrows:
        result=pd.concat(allrows,ignore_index=True)
        output=OUT/"LONG1_REAL_SIGNAL_FIXED_HORIZON_PROXY_SCENARIOS.csv"
        result.to_csv(output,index=False)
        print("\nSCENARIO_CSV",output)

if __name__=="__main__":
    main()
