"""Generate prospective UNAPPLIED diff from current production sources."""
from pathlib import Path
import difflib
import hashlib

main=Path("main.py").read_text()
agg=Path("orchestration/aggregator/aggregator.py").read_text()
def replace_once(s,old,new):
    assert s.count(old)==1, (s.count(old),old[:90])
    return s.replace(old,new,1)

# Candidate metadata must never change model scoring or risk gates.
m=main
anchor='''            "dedup_key": (
                f"{symbol0}|{interval0}|{side0}"
            ),

            "meta": {'''
# Add optional candle metadata only AFTER payload builder returns.
# Producer patch is LOCAL to HeavyEngine model path; explicit model_raw_df input.
m=replace_once(m,
'''        signal_source: str,
        shadow: bool = False,
    ) -> Optional[Dict[str, Any]]:''',
'''        signal_source: str,
        shadow: bool = False,
        model_candle_identity=None,
    ) -> Optional[Dict[str, Any]]:''')
m=replace_once(m,
'''        return {
            "ts_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "event_id": str(uuid.uuid4()),''',
'''        payload = {
            "ts_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "event_id": str(uuid.uuid4()),''')
m=replace_once(m,
'''            },
        }

    def _publish_model_signal_production(''',
'''            },
        }
        # Metadata only: no inference from wallclock close_id.
        if model_candle_identity is not None:
            payload["model_candle_key"] = model_candle_identity.model_candle_key
            payload["model_open_time_ms"] = model_candle_identity.model_open_time_ms
            payload["model_close_time_ms"] = model_candle_identity.model_close_time_ms
        return payload

    def _publish_model_signal_production(''')
m=replace_once(m,
'''        signal_source: str,
    ) -> str:
        """
        Publish one canonical HeavyEngine SignalEvent''',
'''        signal_source: str,
        model_candle_identity=None,
    ) -> str:
        """
        Publish one canonical HeavyEngine SignalEvent''')
m=replace_once(m,
'''            signal_source=signal_source,
            shadow=False,
        )

        if not isinstance(payload, dict):
            return ""''',
'''            signal_source=signal_source,
            shadow=False,
            model_candle_identity=model_candle_identity,
        )

        if not isinstance(payload, dict):
            return ""''')
m=replace_once(m,
'''        model_raw_df = _closed_kline_df(raw_df, min_rows=30)
        feat_df = build_features(model_raw_df)''',
'''        model_raw_df = _closed_kline_df(raw_df, min_rows=30)
        # Observability only; validate from the actual CLOSED model input.
        # Absence is explicit, never manufacture a close_id from wall time.
        model_candle_identity = None
        if str(symbol).upper() == "NEARUSDT":
            try:
                from orchestration.schemas.identity_provenance import identity_from_closed_frame
                model_candle_identity = identity_from_closed_frame(
                    model_raw_df,
                    symbol=symbol,
                    interval=interval,
                    observed_at_ms=int(time.time() * 1000),
                )
            except (ValueError, KeyError, TypeError):
                pass
        feat_df = build_features(model_raw_df)''')
# target uniquely call inside orchestration route
m=replace_once(m,
'''                sid = self._publish_model_signal_production(
                    symbol=symbol,
                    interval=interval,
                    side=side_route,''',
'''                sid = self._publish_model_signal_production(
                    symbol=symbol,
                    interval=interval,
                    side=side_route,
                    model_candle_identity=model_candle_identity,''')

# Fail-closed on bad upstream source: no purported exact parent.
a=agg
a=replace_once(a,
'''        return payload
    def run_forever(self) -> None:''',
'''        # Immutable source identity only, validated in shared helper.
        if sym == "NEARUSDT" and side == "long" and itv == "3m":
            from orchestration.schemas.identity_provenance import verified_source_lineage
            lineage = verified_source_lineage(
                evt, symbol=sym, side=side, interval=itv,
                observed_at_ms=int(time.time() * 1000),
            )
            if lineage is not None:
                payload["lineage"] = lineage
        return payload
    def run_forever(self) -> None:''')
# Produce a new shared runtime module as an UNAPPLIED diff entry.
target="orchestration/schemas/identity_provenance.py"
assert not Path(target).exists(), "already deployed: cannot prepare clean diff"
new_shared=Path("research/staging/long1_identity_runtime_v1.py").read_text()
compile(new_shared,target,"exec")
output=Path("research/results/LONG1_STAGE13_UNAPPLIED_SHARED_RUNTIME_PATCH_20261116.diff")
oldfiles={"main.py":main,"orchestration/aggregator/aggregator.py":agg}
newfiles={"main.py":m,"orchestration/aggregator/aggregator.py":a}
parts=[]
for file in oldfiles:
    old=oldfiles[file].splitlines(keepends=True)
    new=newfiles[file].splitlines(keepends=True)
    parts.extend(difflib.unified_diff(old,new,fromfile="a/"+file,tofile="b/"+file))
    compile(newfiles[file],file,"exec")
parts.extend(difflib.unified_diff(
    [],new_shared.splitlines(keepends=True),
    fromfile="/dev/null",tofile="b/"+target,
))
output.write_text("".join(parts))
print("PATCH_PATH",output,"SIZE_BYTES",output.stat().st_size)
print("SOURCE_SHA256", {k:hashlib.sha256(v.encode()).hexdigest() for k,v in oldfiles.items()})
print("PRODUCTION_FILES_CHANGED",False)
