"""LONG1 opt-in audit of actual Sniper/Entry/PENDING decisions; never order authority.

This observer has no gate or execution callback. Caller must ensure it is
enabled; 'emit' itself also fail-closes when disabled. Uses bounded Redis
XADD records and per-executor dedup to avoid repeated 1m sampling costs.
Only exact available provenance is copied; no score/time heuristic joins.
"""
from __future__ import annotations
import json,os,math
from collections.abc import Mapping
from datetime import datetime,timezone
from orchestration.trace.long1_execution_lineage_v1 import compact

STREAM='telemetry:long1:entry_decision_trace:v1'
STAGES=frozenset(('sniper','entry_confirmation','pending_store','pending_recheck'))
STATUSES=frozenset(('open','block','pending','ready','wait','blocked','cleared','expired','invalid'))
def enabled():
    return str(os.getenv('LONG1_ENTRY_DECISION_TRACE_SHADOW_ENABLE','0')).lower() in ('1','true','yes','on')
def safe_num(v):
    try:
        n=float(v)
        return round(n,6) if math.isfinite(n) else None
    except (TypeError,ValueError):return None
def prepare(*,symbol,stage,decision,extra=None,pending=None,ts_ms=None):
    if str(symbol or '').upper()!='NEARUSDT' or stage not in STAGES:
        return None
    if not isinstance(decision,Mapping):
        return None
    action=str(decision.get('action') or decision.get('status') or '').lower()
    if action not in STATUSES:return None
    details=decision.get('details')
    details=details if isinstance(details,Mapping) else {}
    x=extra if isinstance(extra,Mapping) else {}
    lineage=compact(dict(x,symbol='NEARUSDT'))
    record={
        'schema':'long1_entry_decision_audit.v1',
        'source':'ACTUAL_EXECUTOR_DECISION',
        'ts_ms':int(ts_ms) if ts_ms is not None else 0,
        'symbol':'NEARUSDT','side':'long','stage':stage,'action':action,
        'reason':str(decision.get('reason') or '')[:96],
        'intent_id':str(x.get('intent_id') or '')[:160],
        'lineage':lineage,
        'metrics':{key:safe_num(value) for key,value in {
          'score':decision.get('score'),'required_score':decision.get('required_score'),
          'progress':decision.get('progress'),'quality':details.get('entry_quality'),
          'body_ratio':details.get('body_ratio'),'retrace_ratio':details.get('retrace_ratio'),
          'direction_support':details.get('direction_support'),
          'atr_reversal':details.get('atr_reversal')}.items() if safe_num(value) is not None},
        'pending_attempt_id':str(x.get('pending_attempt_id') or '')[:160],
        'pending_origin_intent_id':str(x.get('pending_origin_intent_id') or '')[:160],
        'pending_recheck_intent_id':str(x.get('pending_recheck_intent_id') or '')[:160],
        'pending_recheck_count':int(x.get('pending_recheck_count') or 0),
        'pending_kind':str(details.get('pending_kind') or '')[:32],
        'entry_candle_interval':str(details.get('entry_candle_interval') or '')[:16],
        'entry_context_source':str(details.get('entry_context_source') or '')[:64],
        'market_context_3m_5m_recovery_verified':False,
        'decision_candle_identity_verified':False,
        'advisory_only':True,'order_authority':False,
    }
    if stage=='pending_recheck' and isinstance(pending,Mapping):
        record['pending_attempt_id']=str(pending.get('pending_attempt_id') or record['pending_attempt_id'])[:160]
    return record
def emit(*,redis_client,symbol,stage,decision,extra=None,pending=None,cache=None,ts_ms=None,maxlen=2500):
    if not enabled():return False
    if redis_client is None:return False
    item=prepare(symbol=symbol,stage=stage,decision=decision,
        extra=extra,pending=pending,ts_ms=ts_ms)
    if item is None:return False
    # Dedupe repeat decisions without repeated expensive writes:
    # same trace origin and reason/action/stage within ONE executor lifetime.
    identity=(item['intent_id'],item['pending_attempt_id'],stage)
    signature=(item['action'],item['reason'])
    if isinstance(cache,dict) and cache.get(identity)==signature:return False
    try:
        redis_client.xadd(STREAM,{'json':json.dumps(item,separators=(',',':'),ensure_ascii=False)},
               maxlen=min(5000,max(100,int(maxlen))),approximate=True)
    except Exception:
        return False
    if isinstance(cache,dict):
        if len(cache)>6000:cache.clear()
        cache[identity]=signature
    return True
