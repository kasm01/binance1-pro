#!/usr/bin/env python3
"""Historical LONG1 real-trade matched audit. No exchange connections or Redis writes."""
from __future__ import annotations
import csv, json, math, statistics
from pathlib import Path
import redis

ROOT=Path(__file__).resolve().parents[2]
DEST=ROOT/"research/results"
OPEN="shadow:telemetry:position_open"
CLOSE="shadow:telemetry:position_outcome"

def num(x):
    try:
        y=float(x)
        return y if math.isfinite(y) else None
    except (ValueError,TypeError): return None

def fetch(r,name):
    out=[]
    for sid,d in r.xrange(name):
        try:
            x=json.loads(d.get("json","{}"))
            if isinstance(x,dict):out.append((sid,x))
        except (ValueError,TypeError):pass
    return out

def flag(x):
    if x is True:return True
    return str(x).lower() in ("true","1")

def classify(x):
    mean=num(x.get("research_m3_ret1_mean3"))
    up=num(x.get("research_m3_up_frac3"))
    f15=num(x.get("research_m3_flow15_completed"))
    f60=num(x.get("research_m3_flow60_completed"))
    st_status=x.get("structure_status")
    st_age=num(x.get("structure_cache_age_sec"))
    st_ok=(st_status=="OK" and st_age is not None and st_age<=180)
    if not st_ok or mean is None or up is None:market="UNKNOWN"
    elif up >= 2/3 and mean>0:market="LONG"
    elif up <= 1/3 and mean<0:market="SHORT"
    else:market="NEUTRAL"
    if not st_ok or f15 is None or f60 is None:flow="UNKNOWN"
    elif f15>0 and f60>0:flow="LONG"
    elif f15<0 and f60<0:flow="SHORT"
    else:flow="MIXED"
    oi_age=num(x.get("oi_source_age_sec"))
    oi_cache=num(x.get("oi_cache_age_sec"))
    oi_limit=num(x.get("oi_source_fresh_limit_sec"))
    oi_quality="VALID_4H" if x.get("oi_status")=="OK" and oi_age is not None and oi_cache is not None and oi_limit is not None and oi_age<=oi_limit else "UNKNOWN"
    micro_quality="VALID" if x.get("micro_status")=="OK" and num(x.get("micro_cache_age_sec")) is not None and num(x.get("micro_cache_age_sec"))<=15 else "UNKNOWN"
    # Historical position telemetry did not store a reliable whale side/score.
    return market,flow,oi_quality,micro_quality,"UNKNOWN"

def metrics(rows):
    if not rows:return {"n":0,"net":0,"win_pct":None,"avg_net":None}
    vals=[x["net_usdt"] for x in rows]
    wins=sum(y>0 for y in vals)
    pos=sum(max(0,y) for y in vals)
    neg=-sum(min(0,y) for y in vals)
    return {"n":len(rows),"net":round(sum(vals),5),
            "avg_net":round(statistics.mean(vals),6),
            "win_pct":round(100*wins/len(vals),2),
            "pf":round(pos/neg,4) if neg>0 else None}

def main():
    r=redis.Redis(host="127.0.0.1",port=6379,decode_responses=True,socket_timeout=4)
    opens=fetch(r,OPEN);closes=fetch(r,CLOSE)
    o_by={};c_by={}
    for sid,obj in opens:o_by.setdefault(str(obj.get("trade_id")),[]).append((sid,obj))
    for sid,obj in closes:c_by.setdefault(str(obj.get("trade_id")),[]).append((sid,obj))
    matched=sorted(set(o_by)&set(c_by),key=lambda k:num(o_by[k][0][1].get("position_open_at_ms")) or 0)
    rows=[]
    for trade in matched:
        # One matched open/outcome per unique trade; duplicate outcomes excluded explicitly.
        if len(o_by[trade])!=1 or len(c_by[trade])!=1:continue
        sid,o=o_by[trade][0];_,c=c_by[trade][0]
        net=num(c.get("net_pnl_usdt_est"))
        if net is None:continue
        m,f,oi,micro,whale=classify(o)
        model=num(o.get("signal_score"));gate=num(o.get("open_min_score"))
        model_ok=model is not None and gate is not None and model>=gate
        contra_m=m=="SHORT";contra_f=f=="SHORT"
        rows.append({
            "trade_id":trade,"entry_ms":int(num(o.get("position_open_at_ms")) or 0),
            "side":"LONG","model_score":model,"gate_at_entry":gate,
            "model_gate_pass":model_ok,"market":m,"flow":f,"oi_quality":oi,
            "micro_quality":micro,"whale":"UNKNOWN",
            "contra_market":contra_m,"contra_flow":contra_f,
            "any_contra":contra_m or contra_f,"dual_contra":contra_m and contra_f,
            "net_usdt":net,"close_reason":str(c.get("close_reason") or ""),
            "est_fee_usdt":num(c.get("estimated_fee_usdt")),
            "est_slip_usdt":num(c.get("estimated_slippage_usdt")),
            "status":"MATCHED_REAL_OPEN_OUTCOME"
        })
    DEST.mkdir(parents=True,exist_ok=True)
    f=DEST/"LONG1_REAL26_FUSION_HISTORICAL_AUDIT.csv"
    if rows:
        with f.open("w",newline="",encoding="utf-8") as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
    configs={
        "BASE_ALL_REAL":lambda x:True,
        "KEEP_WHEN_NO_ANY_CONTRA":lambda x:not x["any_contra"],
        "KEEP_UNLESS_DUAL_CONTRA":lambda x:not x["dual_contra"],
        "KEEP_ONLY_FULL_ALIGNMENT":lambda x:x["market"]=="LONG" and x["flow"]=="LONG",
        "KEEP_ONLY_MARKET_NONSHORT":lambda x:x["market"]!="SHORT",
    }
    print("SOURCE",len(opens),"opens",len(closes),"outcomes","distinct",len(o_by),len(c_by))
    print("MATCHED",len(rows),"unmatched_open",sorted(set(o_by)-set(c_by)),
          "unmatched_outcome",sorted(set(c_by)-set(o_by)),
          "duplicates",{k:len(v) for k,v in c_by.items() if len(v)>1})
    print("DATA_COVERAGE","gate_ok",sum(x["model_gate_pass"] for x in rows),
          "micro_missing",sum(x["micro_quality"]!="VALID" for x in rows),
          "whale_missing",len(rows),"oi_valid",sum(x["oi_quality"]=="VALID_4H" for x in rows))
    base=metrics(rows)
    print("BASE",base)
    print("DIAGNOSTICS")
    for k in ("market","flow","oi_quality"):
        for val in sorted({x[k] for x in rows}):
            a=[x for x in rows if x[k]==val]
            print(k,val,metrics(a))
    print("HYPOTHETICAL_SKIP_NO_REENTRY (NOT A REAL PORTFOLIO BACKTEST)")
    for name,policy in configs.items():
        kept=[x for x in rows if policy(x)]
        skipped=[x for x in rows if not policy(x)]
        m=metrics(kept);z=metrics(skipped)
        print(name,"kept",m,"skipped",z,"delta_from_real_only",round(m["net"]-base["net"],5))
    print("CSV",f)
if __name__=="__main__":main()
