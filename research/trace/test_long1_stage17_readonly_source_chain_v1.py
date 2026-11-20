"""No network/redis, no orders; no guess from same prices or timestamp."""
from __future__ import annotations
import json,subprocess,sys
from pathlib import Path
from research.trace.audit_long1_stage17_readonly_source_chain_v1 import audit,STREAMS
from orchestration.trace.long1_lineage_v1 import candidate_parent,MODEL_CLOSE_KIND
from orchestration.trace.long1_candidate_intent_lineage_v1 import candidate_intent_parent
s={'symbol':'NEARUSDT','side_candidate':'long','event_id':'signal-1',
 'producer_id':'heavy_engine','model_evaluation_id':'eval-new',
 'model_close_id':1234,'model_close_id_kind':MODEL_CLOSE_KIND}
c=dict(symbol='NEARUSDT',side='long',candidate_id='cand-1')
c.update(candidate_parent(s,STREAMS[0],'1794706000000-0'))
i=dict(symbol='NEARUSDT',side='long',intent_id='intent-new')
i.update(candidate_intent_parent(candidate=dict(c,_source_stream_id='1794706001000-0'),
 candidate_stream=STREAMS[1]))
def do(si=None,ca=None,it=None):
 return audit({STREAMS[0]:[('1794706000000-0',si if si is not None else s)],
 STREAMS[1]:[('1794706001000-0',ca if ca is not None else c)],
 STREAMS[2]:[('1794706003000-0',{'items':[it if it is not None else i]})]},
 source_lengths={k:1 for k in STREAMS},limit=3000)
good=do()
assert good['counts']=={'EXACT_SOURCE_ONLY_NO_ORDER_AUTHORITY':1}
assert not good['live_order_authorized'] and not good['redis_writes']
invalid=[
 do(ca=dict(c,parent_trace_id='invalid')),
 do(it=dict(i,source_candidate_stream_id='1794706001000-1')),
 do(si=dict(s,model_evaluation_id='eval-different')),
 do(it=dict(i,model_evaluation_id='eval-invalid')),
 do(it=dict(i,source_signal_stream_id='1794706000000-1')),
 do(it=dict(i,side='short')),
 do(ca=dict(c,symbol='INJUSDT')),
 do(it=dict(i,intent_id='')),
 do(it={k:v for k,v in i.items() if k!='parent_trace_id'}),
]
for x in invalid:
 assert x['counts'].get('EXACT_SOURCE_ONLY_NO_ORDER_AUTHORITY',0)==0
 assert not x['live_order_authorized']
# CLI default disabled without connecting to Redis
root=Path(__file__).resolve().parents[2]
p=subprocess.run([sys.executable,str(root/'research/trace/audit_long1_stage17_readonly_source_chain_v1.py')],
 cwd=root,text=True,capture_output=True,timeout=8)
assert p.returncode==0 and 'DISABLED' in p.stdout
print(json.dumps({'status':'PASS','exact_pure_fixture':1,
 'tamper_and_missing_cases':len(invalid),'cli_default_disabled':True,
 'time_score_join':False,'real_orders':0,'redis_writes':0},sort_keys=True))
