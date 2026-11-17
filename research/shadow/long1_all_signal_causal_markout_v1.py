#!/usr/bin/env python3
"""Causal 1m-bar markout of archived LONG1 model signals; NO orders or new API calls."""
import json, math, redis
import numpy as np
import pandas as pd
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"research/data/NEARUSDT_1m_LIVE26_20261022_20261102.csv"
OUT=ROOT/"research/results"
HORIZONS=(15,30,60)
ROUNDTRIP_FEE=0.0008
LEV=3.0

def features(df):
    x=df.copy()
    x["bucket"]=x.open_time//180000
    g=x.groupby("bucket",sort=True)
    b=g.agg(open_time=("open_time","first"),close_time=("close_time","last"),
            open=("open","first"),high=("high","max"),low=("low","min"),
            close=("close","last"),quote=("quote_asset_volume","sum"),
            taker_buy_quote=("taker_buy_quote_volume","sum"),
            count=("open_time","size")).reset_index(drop=True)
    b=b[b["count"]==3].copy()
    b["ret1"]=b.close.pct_change()
    b["mean3"]=b.ret1.rolling(3,min_periods=3).mean()
    b["up_frac3"]=b.ret1.gt(0).rolling(3,min_periods=3).mean()
    net_quote=2*b.taker_buy_quote-b.quote
    b["flow15"]=net_quote.rolling(5,min_periods=5).sum()/b.quote.rolling(5,min_periods=5).sum()
    b["flow60"]=net_quote.rolling(20,min_periods=20).sum()/b.quote.rolling(20,min_periods=20).sum()
    return b.reset_index(drop=True)

def market(row):
    up=row.up_frac3;mean=row.mean3
    if pd.isna(up) or pd.isna(mean):return "UNKNOWN"
    if up >= 2/3-1e-9 and mean>0:return "LONG"
    if up <= 1/3+1e-9 and mean<0:return "SHORT"
    return "NEUTRAL"

def flow(row):
    a=row.flow15;b=row.flow60
    if pd.isna(a) or pd.isna(b):return "UNKNOWN"
    if a>0 and b>0:return "LONG"
    if a<0 and b<0:return "SHORT"
    return "MIXED"

def evaluate():
    one=pd.read_csv(SRC).sort_values("open_time").reset_index(drop=True)
    o=one.open_time.to_numpy(np.int64)
    close_times=one.close_time.to_numpy(np.int64)
    oclose=one.close.to_numpy(float)
    oopen=one.open.to_numpy(float)
    ohigh=one.high.to_numpy(float);olow=one.low.to_numpy(float)
    three=features(one)
    bar_t=three.close_time.to_numpy(np.int64)
    r=redis.Redis(decode_responses=True,socket_timeout=5)
    signal_events=[]
    for key,fields in r.xrange("signals_stream_long1"):
        try:
            ev=json.loads(fields["json"])
            if ev.get("symbol")!="NEARUSDT" or str(ev.get("side_candidate")).lower()!="long":continue
            signal_events.append((int(key.split("-")[0]),key,ev))
        except (KeyError,ValueError):pass
    # Deduplicate by three-minute UTC signal clock bucket.
    # Keep FIRST historical publishing event; do not use later (more informed) duplicates.
    groups={}
    for stamp,sid,ev in signal_events:
        bucket=stamp//180000
        groups.setdefault(bucket,(stamp,sid,ev))
    chosen=sorted(groups.values())

    out=[]
    for t,sid,ev in chosen:
        bi=int(np.searchsorted(bar_t,t,side="right")-1)
        if bi<0:continue
        b=three.iloc[bi]
        a=int(np.searchsorted(o,t,side="right"))
        # Only future minute OPEN. Reject gaps/bad alignment.
        if a>=len(o) or o[a]-t>120000:continue
        entry=float(oopen[a]);m=market(b);f=flow(b)
        if entry<=0:continue
        d=dict(signal_id=ev.get("event_id"),stream_id=sid,
               signal_ts_ms=t,signal_bucket=t//180000,
               model_score=float(ev.get("model_score") or 0),
               whale_dir=ev.get("whale_dir"),whale_score=ev.get("whale_score"),
               last_completed_3m_ms=int(b.close_time),
               last_bar_age_sec=round((t-b.close_time)/1000,3),
               model_price=ev.get("price"),assumed_next_1m_open=entry,
               market=m,flow=f,
               m3_up_frac3=float(b.up_frac3),m3_mean3=float(b.mean3),
               flow15=float(b.flow15),flow60=float(b.flow60),
               dual_contra=(m=="SHORT" and f=="SHORT"),
               source="recomputed_completed_1m_to_3m")
        for h in HORIZONS:
            end_ms=int(o[a])+h*60000
            ix=int(np.searchsorted(o,end_ms,side="left")-1)
            valid=(ix>=a and ix<len(o) and
                   o[ix]-o[a]==(h-1)*60000 and
                   int(close_times[ix])<=int(close_times[-1]))
            # markout after h full future 1m bars; no use of partially completed signal bar.
            d[f"valid_{h}m"]=bool(valid)
            if valid:
                gross=float(oclose[ix]/entry-1.0)
                d[f"net_return_{h}m_pct"]=100*(gross-ROUNDTRIP_FEE)
                d[f"net_roi_{h}m_pct"]=100*LEV*(gross-ROUNDTRIP_FEE)
                d[f"mfe_{h}m_pct"]=100*(float(np.max(ohigh[a:ix+1]))/entry-1)
                d[f"mae_{h}m_pct"]=100*(float(np.min(olow[a:ix+1]))/entry-1)
            else:
                d[f"net_return_{h}m_pct"]=np.nan
                d[f"net_roi_{h}m_pct"]=np.nan
                d[f"mfe_{h}m_pct"]=np.nan
                d[f"mae_{h}m_pct"]=np.nan
        out.append(d)

    result=pd.DataFrame(out)
    DEST=OUT/"LONG1_ALL_REAL_SIGNALS_CAUSAL_MARKOUT.csv"
    result.to_csv(DEST,index=False)
    print("SOURCE SIGNALS",len(signal_events),"UNIQUE_3M_BUCKETS",len(groups),
          "CAUSAL_VALID_SAMPLES",len(result),"range",pd.to_datetime(result.signal_ts_ms.min(),unit="ms",utc=True),
          pd.to_datetime(result.signal_ts_ms.max(),unit="ms",utc=True))
    print("CONTEXT",result.groupby(["market","flow"],dropna=False).size().to_string())
    print("DISTRIBUTIONS candidate (3m unique) / NOT trades")
    for h in HORIZONS:
        y=f"net_return_{h}m_pct"
        z=result[result[f"valid_{h}m"]]
        print("\nHORIZON",h,"MIN roundtrip_fee",ROUNDTRIP_FEE*100,"pct underlying")
        for name,v in [("ALL",z),("DUAL",z[z.dual_contra]),("NONDUAL",z[~z.dual_contra])]:
            if v.empty:continue
            a=v[y]
            print(name,"N",len(v),"mean_net_return_pct",round(a.mean(),4),
                  "median",round(a.median(),4),
                  "profitable_pct",round(100*(a>0).mean(),2),
                  "mfe_mean_pct",round(v[f"mfe_{h}m_pct"].mean(),4),
                  "mae_mean_pct",round(v[f"mae_{h}m_pct"].mean(),4))
    print("CSV",DEST)
    return result,three

def validate(tri):
    r=redis.Redis(decode_responses=True,socket_timeout=5)
    obs=[]
    for _,fields in r.xrange("shadow:telemetry:position_open"):
        d=json.loads(fields.get("json") or "{}")
        ms=d.get("position_open_at_ms")
        if ms:obs.append(d)
    obs_a=[]
    times=tri.close_time.to_numpy(np.int64)
    for v in obs:
        t=int(v["position_open_at_ms"])
        k=int(np.searchsorted(times,t,side="right")-1)
        if k<0:continue
        row=tri.iloc[k]
        obs_a.append({"trade_id":v.get("trade_id"),"time":t,
              "snap_up":v.get("research_m3_up_frac3"),"hist_up":row.up_frac3,
              "snap_mean":v.get("research_m3_ret1_mean3"),"hist_mean":row.mean3,
              "snap_f15":v.get("research_m3_flow15_completed"),"hist_f15":row.flow15,
              "snap_f60":v.get("research_m3_flow60_completed"),"hist_f60":row.flow60,
              "snap_3m_close":v.get("research_3m_close_time_ms"),"hist_3m_close":int(row.close_time)})
    x=pd.DataFrame(obs_a)
    x["bar_match"]=x.snap_3m_close.eq(x.hist_3m_close) & x.snap_3m_close.notna()
    print("\nSNAPSHOT VALIDATION",len(x),"archived_snapshot_3m_timestamp_present",int(x.snap_3m_close.notna().sum()),
          "direct_bar_matches",int(x.bar_match.sum()),"note: absent source timestamp cannot be compared")
    for field in ("up","mean","f15","f60"):
        a=pd.to_numeric(x["snap_"+field],errors="coerce")
        b=pd.to_numeric(x["hist_"+field],errors="coerce")
        delta=(a-b).abs()
        print(field,"valid",int(delta.notna().sum()),"max_abs_diff",round(delta.max(),7),
              "median_abs_diff",round(delta.median(),7),
              "matches_1e-4",int((delta<1e-4).sum()))
    dest=OUT/"LONG1_CAUSAL_RECON_VALIDATION_26.csv"
    x.to_csv(dest,index=False)
    print("VALIDATION_CSV",dest)
    return x

if __name__=="__main__":
    results,tri=evaluate()
    validate(tri)
