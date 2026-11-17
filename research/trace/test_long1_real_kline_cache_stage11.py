"""Read-only real cache schema and REST-format normalization smoke test."""
import json
import time
import pandas as pd
import redis
from research.trace.long1_model_candle_identity_v1 import from_closed_frame
r=redis.Redis(decode_responses=True,socket_timeout=5)
keys=list(r.scan_iter(match="*:kline_cache:NEARUSDT:3m",count=100))
assert keys, "No cache key to inspect"
key=next((x for x in keys if r.get(x)),None)
assert key is not None, "Cache expired"
payload=json.loads(r.get(key))
rows=payload.get("rows")
assert isinstance(rows,list) and len(rows)>=30
# Same code structure main.py: model_raw_df = _closed_kline_df(raw_df)
# no importing main.py (avoid startup side effects)
frame=pd.DataFrame(rows)
now=int(time.time()*1000)
closed=frame.loc[pd.to_numeric(frame["close_time"],errors="coerce")>0]
closed=closed.loc[pd.to_numeric(closed["close_time"],errors="coerce")<=now].copy().reset_index(drop=True)
assert len(closed)>=30, "insufficient closed candles"
identity=from_closed_frame(closed,symbol="NEARUSDT",interval="3m",observed_at_ms=now)
# 12-element strings imitate Binance REST shape (same normalization path), not
# a new network request / independent validation of Binance exchange service.
fields=["open_time","open","high","low","close","volume","close_time",
        "quote_asset_volume","number_of_trades","taker_buy_base_volume",
        "taker_buy_quote_volume","ignore"]
rest_strings=[[str(row.get(f,"0")) for f in fields] for row in rows]
rest_frame=pd.DataFrame(rest_strings,columns=fields)
for c in fields:rest_frame[c]=pd.to_numeric(rest_frame[c],errors="raise")
rest_closed=rest_frame.loc[rest_frame["close_time"]<=now].reset_index(drop=True)
rest_identity=from_closed_frame(rest_closed,symbol="NEARUSDT",interval="3m",observed_at_ms=now)
assert identity==rest_identity
# Verify time comes from actual columns even when mixed row becomes float64
assert isinstance(frame.iloc[-1]["open_time"],float) and frame["open_time"].dtype.kind=="i"
print(json.dumps({"cache_rows":len(rows),"closed_rows":len(closed),
    "cache_ttl_sec":r.ttl(key),"candle_key":identity.model_candle_key,
    "cache_vs_rest_shaped_equal":True,
    "rest_independently_fetched":False,
    "note":"Read-only Redis cache; REST-format synthetic serialization"},sort_keys=True))
