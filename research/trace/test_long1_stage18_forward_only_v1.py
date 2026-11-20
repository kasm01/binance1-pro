"""No Redis, no network. Explicit stream baseline + strict idempotent replay."""
from __future__ import annotations
from copy import deepcopy
import subprocess,sys,json
from pathlib import Path
from research.trace.long1_stage18_forward_only_source_audit_v1 import (
 STREAMS,initial_state,audit_since
)
from orchestration.trace.long1_lineage_v1 import MODEL_CLOSE_KIND,candidate_parent
from orchestration.trace.long1_candidate_intent_lineage_v1 import candidate_intent_parent
class Stub:
 def __init__(self,data):
  self.data=data
  self.parent_reads=0
 def xrevrange(self,name,count=10):
  self.parent_reads+=1
  return [(k,{'json':json.dumps(v)}) for k,v in sorted(self.data[name],reverse=True)[:count]]
 def xrange(self,name,min='-',max='+',count=None):
  exclusive=min.startswith('(')
  val=min[1:] if exclusive else min
  key=lambda x:tuple(map(int,x.split('-')))
  out=[(k,{'json':json.dumps(v)}) for k,v in sorted(self.data[name]) if
   key(k)>key(val) if exclusive] if exclusive else [
   (k,{'json':json.dumps(v)}) for k,v in sorted(self.data[name]) if key(k)>=key(val)]
  return out[:count]
 def xlen(self,name):return len(self.data[name])
baseline={STREAMS[0]:'1794706000000-0',
 STREAMS[1]:'1794706001000-0',
 STREAMS[2]:'1794706003000-0'}
s={'symbol':'NEARUSDT','side_candidate':'long','event_id':'signal-2',
 'producer_id':'heavy_engine','model_evaluation_id':'eval-new',
 'model_close_id':900,'model_close_id_kind':MODEL_CLOSE_KIND}
c={'symbol':'NEARUSDT','side':'long','candidate_id':'cand-new'}
c.update(candidate_parent(s,STREAMS[0],'1794707000000-0'))
i={'symbol':'NEARUSDT','side':'long','intent_id':'intent-new'}
i.update(candidate_intent_parent(candidate=dict(c,_source_stream_id='1794707001000-0'),
 candidate_stream=STREAMS[1]))
data={
 STREAMS[0]:[(baseline[STREAMS[0]],{'symbol':'NEARUSDT'}),('1794707000000-0',s)],
 STREAMS[1]:[(baseline[STREAMS[1]],{'symbol':'NEARUSDT'}),('1794707001000-0',c)],
 STREAMS[2]:[(baseline[STREAMS[2]],{'items':[{'symbol':'NEARUSDT','side':'long','intent_id':'old'}]}),
   ('1794707003000-0',{'items':[i]})]}
r=Stub(data)
state=initial_state(baseline)
rep,nextstate=audit_since(r,state,limit=100)
assert rep['new_intent_batch_records']==1
assert rep['counts']=={'EXACT_SOURCE_ONLY_NO_ORDER_AUTHORITY':1}
assert rep['trade_intents_long_observed']==1
assert rep['cursor_after_intent_id']=='1794707003000-0'
assert nextstate['last_seen_intent_id']=='1794707003000-0'
assert not rep['live_order_authorized']
empty,_=audit_since(r,nextstate,limit=100)
assert empty['new_intent_batch_records']==0
assert empty['trade_intents_long_observed']==0
assert r.parent_reads==2  # first audit only; second audit skips upstream
# A historical batch cannot become a future event.
old=Stub({k:[z for z in rows if z[0]<=baseline[k]] for k,rows in data.items()})
no_new,_=audit_since(old,state,limit=100)
assert no_new['new_intent_batch_records']==0
tampered=deepcopy(data)
tampered[STREAMS[2]][-1][1]['items'][0]['parent_trace_id']='bad'
bad,_=audit_since(Stub(tampered),state,limit=100)
assert bad['counts']=={'NOT_PROVEN':1}
# missing retained candidate makes original intent unprovable, no guessed join
trimmed=deepcopy(data)
trimmed[STREAMS[1]]=trimmed[STREAMS[1]][:1]
bad2,_=audit_since(Stub(trimmed),state,limit=100)
assert bad2['counts']=={'NOT_PROVEN':1}
assert not bad2['live_order_authorized']
root=Path(__file__).resolve().parents[2]
result=subprocess.run([sys.executable,
 str(root/'research/trace/long1_stage18_forward_only_source_audit_v1.py')],
 cwd=root,capture_output=True,text=True,timeout=8)
assert result.returncode==0 and 'DISABLED' in result.stdout
print(json.dumps({'status':'PASS','forward_exact_intent':1,
 'historical_intent_recount':0,'idempotent_second_run':True,
 'corrupt_and_trimmed_fail_closed':True,'cli_default_disabled':True,
 'orders':0,'redis_writes':0},sort_keys=True))
