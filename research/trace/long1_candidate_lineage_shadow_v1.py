"""Proposed minimal candidate provenance, research only (not production).

Read original normalized signal with event_id and _source_stream_id before
the aggregator compacts raw. Add only immutable identity strings to candidate.
No model_close_id can be inferred unless actual producer supplies it explicitly.
Never reconstruct genealogy from dedup_key, score or timestamps.
"""
from __future__ import annotations
import re
from typing import Mapping
MAX=160
def valid_event_id(s):
 return isinstance(s,str) and 1<=len(s)<=MAX and bool(re.fullmatch(r'[A-Za-z0-9_.:-]+',s))
def valid_stream_id(s):
 return isinstance(s,str) and bool(re.fullmatch(r'\d{11,16}-\d{1,6}',s))
def lineage_from_signal(e:Mapping):
 if not isinstance(e,dict):return dict(lineage_state='UNLINKED',reason='invalid_payload')
 eid=e.get('event_id')
 source=e.get('_source_stream_id')
 if not valid_event_id(eid) or not valid_stream_id(source):
  return dict(lineage_state='UNLINKED',reason='missing_explicit_signal_identity')
 out=dict(lineage_state='EXACT_SIGNAL_EVENT_ID_AND_STREAM_ID',
    source_signal_event_id=eid,source_signal_stream_id=source)
 # Only preserve a *real* source-reported model close ID; never guess it.
 cid=e.get('model_close_id')
 if type(cid) is int and cid>0:out['model_close_id']=cid
 return out

def candidate_shadow(candidate:Mapping, signal:Mapping):
 if not isinstance(candidate,dict):raise ValueError('candidate dict expected')
 a=dict(candidate)
 # provenance fields don't impact score, permissions, price, side or filters
 a['lineage']=lineage_from_signal(signal)
 return a
