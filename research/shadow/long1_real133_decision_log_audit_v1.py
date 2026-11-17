#!/usr/bin/env python3
"""Offline real-intent decision funnel audit. No Redis writes, no orders."""
import collections
import datetime as dt
import json
import re
from bisect import bisect_left
from pathlib import Path

import pandas as pd
import redis

ROOT = Path(__file__).resolve().parents[2]
LOGS = [ROOT/"logs"/x for x in
        ("main.log", "main.log.1", "main.log.2", "main.log.3", "main.log.4", "main.log.5")]
OUTPUT = ROOT/"research/results"
START = "2026-10-24"
END = "2026-11-03"
DATE = re.compile(r"^(2026-\d\d-\d\d \d\d:\d\d:\d\d,\d\d\d)")
DISPATCH = re.compile(r"\[EXEC-EVENTS\] dispatch decision .*intent=([a-f0-9-]+)")
ENTRY = re.compile(r"\[EXEC\]\[ENTRY-DECISION\] action=(\S+) reason=(\S+)")
OPEN_BLOCK = re.compile(r"\[EXEC\]\[OPEN-BLOCK\](?:\[([^]]+)\])?")
PENDING = re.compile(r"\[EXEC\]\[PENDING-(STORE|RECHECK|EXPIRE)\]")

def unix_ms(line):
    m = DATE.search(line)
    if not m:
        return None
    x = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f")
    return int(x.replace(tzinfo=dt.timezone.utc).timestamp()*1000)

def collect():
    matched = []
    for file in LOGS:
        if not file.exists():
            continue
        for line in file.open(encoding="utf-8", errors="replace"):
            if not line.startswith(("2026-10-", "2026-11-")):
                continue
            if not any(tag in line for tag in
                       ("[EXEC-EVENTS] dispatch decision", "[EXEC][ENTRY-DECISION]",
                        "[EXEC][PENDING-", "[EXEC][OPEN-BLOCK]",
                        "[EXEC-EVENTS] execute_decision failed",
                        "[EXEC][OPEN][COMMIT]")):
                continue
            t = unix_ms(line)
            if t is None:
                continue
            matched.append((t, line.strip()))
    matched.sort()
    return matched

def main():
    r=redis.Redis(decode_responses=True, socket_timeout=4)
    intents=[]
    for sid, fields in r.xrange("trade_intents_stream_long1"):
        try:
            obj=json.loads(fields["json"])
            for item in obj.get("items",[]):
                if isinstance(item,dict):
                    intents.append(dict(intent_id=item.get("intent_id"),
                        ts=int(sid.split("-")[0]),model_score=item.get("score")))
        except (ValueError,KeyError):
            continue
    opened={}
    for sid,fields in r.xrange("shadow:telemetry:position_open"):
        try:
            obj=json.loads(fields["json"])
            opened[obj.get("intent_id")]=obj
        except (ValueError,KeyError):
            pass
    lines=collect()
    disp={}
    logs_by_ts=[x[0] for x in lines]
    for index,(ts,line) in enumerate(lines):
        match=DISPATCH.search(line)
        if match:
            disp.setdefault(match.group(1),[]).append((ts,index))
    rows=[]
    for i in intents:
        ident=i["intent_id"]
        hits=disp.get(ident,[])
        row=dict(intent_id=ident,intent_ts_ms=i["ts"],
                 actual_open=(ident in opened),dispatch_found=bool(hits),
                 dispatch_count=len(hits),first_action="NO_LOG",
                 first_reason="NOT_OBSERVED",first_shadow=None,
                 immediate_decision_count=0,pending_events_15m=0,
                 immediate_open_block=None,decision_log_age_sec=None)
        if hits:
            ts,index=hits[0]
            row["dispatch_time_ms"]=ts
            # Inclusive time window around dispatch only. Do not attribute
            # later unrelated pending decisions to the same intent.
            next_dispatch_ts=min(
                (v[0] for h in disp.values() for v in h if v[0]>ts),default=ts+20000)
            limit=min(ts+15000,next_dispatch_ts)
            local=[v for t,v in lines[index+1:] if ts<=t<=limit]
            reasons=[]
            for msg in local:
                a=ENTRY.search(msg)
                if a:
                    reasons.append((a.group(1),a.group(2),msg))
                b=OPEN_BLOCK.search(msg)
                if b and row["immediate_open_block"] is None:
                    row["immediate_open_block"]=b.group(1) or "UNSPECIFIED"
            row["immediate_decision_count"]=len(reasons)
            if reasons:
                action,reason,raw=reasons[0]
                row["first_action"]=action
                row["first_reason"]=reason
                mt=re.search(r"\bshadow=(\S+)",raw)
                row["first_shadow"]=mt.group(1) if mt else None
                row["decision_log_age_sec"]=round((unix_ms(raw)-ts)/1000,3)
            # 15min PENDING activity is unlinked unless a stable intent ID
            # is included, so count only as vicinity diagnostic.
            loc15=[m for tt,m in lines[index+1:] if ts<=tt<ts+900000 and PENDING.search(m)]
            row["pending_events_15m"]=len(loc15)
        rows.append(row)
    frame=pd.DataFrame(rows).sort_values("intent_ts_ms")
    OUTPUT.mkdir(exist_ok=True,parents=True)
    path=OUTPUT/"LONG1_REAL133_INTENT_DECISION_LOG_AUDIT.csv"
    frame.to_csv(path,index=False)
    print("INTENTS",len(frame),"OPEN",int(frame.actual_open.sum()),
          "DISPATCH_MATCH",int(frame.dispatch_found.sum()),
          "LOG_ACTION",int(frame.first_action.ne("NO_LOG").sum()))
    print("FIRST_ACTION CROSS-TAB")
    print(pd.crosstab([frame.first_action,frame.first_reason,frame.first_shadow.fillna("NA")],
                      frame.actual_open,dropna=False).to_string())
    no=frame[~frame.actual_open]
    print("NO OPEN",len(no),"FIRST_ACTION",no.first_action.value_counts().to_dict())
    print("OPEN FIRST ACTION",frame[frame.actual_open].first_action.value_counts().to_dict())
    print("LOG COVERAGE MISSING",len(frame[~frame.dispatch_found]),
          "WITH DISPATCH BUT NO DECISION",len(frame[(frame.dispatch_found)&(frame.first_action=="NO_LOG")]))
    print("OPEN BLOCK",frame.immediate_open_block.value_counts(dropna=False).to_dict())
    print("CSV",path)
if __name__=="__main__":
    main()
