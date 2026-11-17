from research.trace.long1_trace_contract_v1 import event,validate,trace_id_from_transport
def fails(f):
 try:f()
 except ValueError:return
 raise AssertionError('expected ValueError')
a=event(stream="exec_events_stream_long1",stream_id="1794706740470-0",
 at_ms=1794706740470,stage="ENTRY_CONFIRMATION",state="PENDING",
 reason="entry_confirmation_no_directional_span",
 kind="EXACT_INTENT",intent_id="intent-abc")
assert validate(a)==a
assert trace_id_from_transport("a","1-0")==trace_id_from_transport("a","1-0")
assert trace_id_from_transport("a","1-0")!=trace_id_from_transport("b","1-0")
fails(lambda:validate(dict(a,advisory_only=False)))
fails(lambda:validate(dict(a,stage="ORDER_FILLED")))
fails(lambda:validate(dict(a,observed_at_ms="1794706740470")))
fails(lambda:validate(dict(a,source_closed_at_ms=a["observed_at_ms"]+1)))
fails(lambda:validate(dict(a,correlation_kind="EXACT_ORDER_ID")))
fails(lambda:validate(dict(a,intent_id=None)))
fails(lambda:validate(dict(a,reason="bad email@example.com")))
fails(lambda:validate(dict(a,state="UNLINKED")))
fails(lambda:validate(dict(a,trace_id="BAD SEPARATOR")))
fails(lambda:validate(dict(a,unexpected="secret")))
print("PASS 13 strict trace contract checks")
