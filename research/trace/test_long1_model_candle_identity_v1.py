import pandas as pd
from research.trace.long1_model_candle_identity_v1 import from_closed_candle, from_closed_frame

op = 1794845520000  # normalized in test to 3-minute UTC boundary below
op -= op % 180000
cl = op + 180000 - 1
args = dict(symbol="NEARUSDT", interval="3m", open_time_ms=op,
            close_time_ms=cl, observed_at_ms=cl+1000)
v = from_closed_candle(**args)
assert v.model_candle_key == f"NEARUSDT:3m:{op}:{cl}"
assert from_closed_candle(**args) == v
assert from_closed_frame(pd.DataFrame([{"open_time":op,"close_time":cl}]),
                         symbol="NEARUSDT",interval="3m",observed_at_ms=cl+1) == v
count=0
def bad(**delta):
    global count
    a = dict(args,**delta)
    try: from_closed_candle(**a)
    except ValueError: count += 1
    else: raise AssertionError("must reject "+str(delta))
bad(symbol="INJUSDT")
bad(interval="2m")
bad(open_time_ms=op+1000)
bad(close_time_ms=cl-1)
bad(close_time_ms=cl+180000)
bad(observed_at_ms=cl)
bad(observed_at_ms=cl-1)
bad(open_time_ms=True)
bad(open_time_ms=op/1.0)
bad(close_time_ms=str(cl)+"foo")
bad(open_time_ms=-1)
assert count==11
assert from_closed_candle(**dict(args,open_time_ms=str(op)))==v
try:
    from_closed_frame(pd.DataFrame([{"open_time":op}]),symbol="NEARUSDT",
                      interval="3m",observed_at_ms=cl+1000)
except ValueError: pass
else: raise AssertionError("missing close time")
print("PASS: source candle identity deterministic, 11 negative checks, frame extraction")
# Regression: real Binance candle frames have mixed numeric columns; a Pandas
# whole-row access promotes timestamps to float64, per-column access must not.
mixed=pd.DataFrame([{"open_time":op,"close_time":cl,"open":3.0,"close":3.01}])
assert isinstance(mixed.iloc[-1]["open_time"],float)
assert from_closed_frame(mixed,symbol="NEARUSDT",interval="3m",observed_at_ms=cl+1)==v
print("PASS: mixed-type Pandas frame preserves source time identity")
