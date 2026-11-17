"""Production read-only release-gate audit. Never accesses private API credentials."""
from __future__ import annotations
import hashlib
import json
import subprocess
import time
from pathlib import Path
import redis

STREAMS=(
    "signals_stream_long1","candidates_stream_long1","top5_stream_long1",
    "trade_intents_stream_long1","exec_events_stream_long1",
)
FILES=("main.py","orchestration/aggregator/aggregator.py",
       "orchestration/selector/top_selector.py",
       "orchestration/executor/master_executor.py",
       "orchestration/executor/intent_bridge.py",
       "core/trade_executor.py")
r=redis.Redis(decode_responses=True,socket_timeout=5)
streams=[]
for key in STREAMS:
    info=r.xinfo_stream(key)
    groups=[]
    for g in r.xinfo_groups(key):
        pending=r.xpending(key,g["name"])
        groups.append({
            "name":g["name"],
            "pending":int(g["pending"]),
            "lag":g["lag"],
            "consumer_count":g["consumers"],
            "pending_min_id":pending.get("min"),
            "pending_max_id":pending.get("max"),
        })
    latest=info.get("last-entry")
    ms=int(latest[0].split("-")[0]) if latest else None
    streams.append({
        "stream":key,
        "length":r.xlen(key),
        "latest_id":latest[0] if latest else None,
        "age_min":round((time.time()*1000-ms)/60000,1) if ms else None,
        "groups":groups,
    })
status={}
for unit in ("binance1-long-supervisor.service","binance1-long-orch.service",
             "binance1-long1-native-stop.service","binance1-central-risk-enforce-dry.service"):
    cp=subprocess.run(["systemctl","--user","is-active",unit],capture_output=True,text=True)
    status[unit]=cp.stdout.strip()
pids={}
for pid in (1274,1276,1278,1285,940695):
    try:
        path=Path(f"/proc/{pid}/cmdline")
        command=path.read_bytes().replace(b"\0",b" ").decode(errors="replace").strip()
        pids[str(pid)]={"alive":True,"command":command.rsplit("/",1)[-1][:100]}
    except (OSError,ValueError):
        pids[str(pid)]={"alive":False}
files={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in FILES}
audit={
    "timestamp_unix":int(time.time()),
    "streams":streams,
    "units":status,
    "processes":pids,
    "file_sha256":files,
    "release_gate":"NO_GO",
    "reason":[
        "staged identity patch NOT applied",
        "no frozen-clock full execution / PENDING / final safety replay",
        "not all downstream paths preserve explicit trace ID",
        "live orders prohibited during rollback verification",
    ],
}
print(json.dumps(audit,ensure_ascii=False,indent=2))
