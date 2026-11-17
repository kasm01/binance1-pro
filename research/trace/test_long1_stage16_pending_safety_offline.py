"""Live method AST extraction with offline fake state and order sink."""
import ast,asyncio,copy,json,os,types
from pathlib import Path
from unittest.mock import patch
source=ast.parse(Path("core/trade_executor.py").read_text())
names={"_interval_to_seconds","_get_long_candle_id","_classify_long_pending_window",
 "_check_long_pending_window","_process_long_pending_candidate",
 "_get_long_pending_candidate","_clear_long_pending_candidate",
 "_evaluate_long_execution_risk_gate","_execute_long_validated_candidate"}
classes=[n for n in ast.walk(source) if isinstance(n,ast.ClassDef) and
 any(getattr(m,"name",None)=="_process_long_pending_candidate" for m in n.body)]
assert len(classes)==1
nodes=[copy.deepcopy(n) for n in classes[0].body if getattr(n,"name",None) in names]
assert {n.name for n in nodes}==names
for n in nodes:
 n.decorator_list=[ast.Name(id="staticmethod",ctx=ast.Load())] if n.name=="_interval_to_seconds" else []
 n.returns=None
 for a in n.args.args+n.args.kwonlyargs:a.annotation=None
mod=ast.Module(body=[ast.ClassDef(name="Isolated",bases=[],keywords=[],body=nodes,decorator_list=[])],type_ignores=[])
ast.fix_missing_locations(mod)
env={"os":os,"time":__import__("time")}
exec(compile(mod,"<stage16>","exec"),env)
E=env["Isolated"]
events=[]
async def fake_order(**kwargs):
 events.append("FAKE_ORDER_SINK")
 return {"status":"dry_run"}
def obj():
 x=E(); x.logger=None;x.long_pending_by_symbol={};x.max_open_positions=1;x.dry_run=True
 x._get_effective_position=lambda s:{}
 x._count_open_positions_for_side=lambda s:0
 x._long_contra_context_gate=lambda **k:True
 x._resolve_long_intent_price=lambda **k:k["price"]
 x._resolve_long_order_price=lambda **k:k["intent_price"]
 x._execute_long_order_pipeline=fake_order
 return x
C=29914354
windows=[
 ("confirmation",C,.20,"ready"),("confirmation",C,.02,"wait_same_candle"),
 ("confirmation",C+1,.20,"expired"),("early",C,.2,"ready"),
 ("early",C+1,.2,"expired"),("late",C,.2,"wait_same_candle"),
 ("late",C+1,.2,"ready"),("late",C+1,.02,"wait_window"),
 ("late",C+1,.8,"wait_window"),("late",C+2,.2,"expired"),
 ("late",C-1,.2,"invalid"),
]
for kind,current,progress,want in windows:
 x=obj();p={"candle_id":C,"decision":{"details":{"pending_kind":kind}}}
 x.long_pending_by_symbol["NEARUSDT"]=p
 with patch.dict(os.environ,{"SNIPER_ENTRY_MIN_CANDLE_PROGRESS":"0.08"}):
  got,_=x._classify_long_pending_window(created_candle_id=C,current_candle_id=current,
   progress=progress,max_pending_progress=.6,pending_kind=kind)
  assert got==want,(kind,current,got,want)
  accepted=x._check_long_pending_window(symbol="NEARUSDT",pending=p,
   current_candle_id=current,progress=progress,max_pending_progress=.6)
 assert accepted==(want=="ready")
 assert ("NEARUSDT" in x.long_pending_by_symbol)==(want not in ("expired","invalid"))
pending={}
for mode in ("ready","wait_preparation","wait_revalidation","blocked_revalidation","expired"):
 x=obj();p={"candle_id":C,"decision":{"details":{"pending_kind":"late"}}}
 x.long_pending_by_symbol["NEARUSDT"]=p
 x._prepare_long_pending_candidate=lambda **k: None if mode=="wait_preparation" else (3.9,.55,.49,{})
 def handle(**k):
  if mode=="blocked_revalidation":x._clear_long_pending_candidate(symbol="NEARUSDT")
  return mode in ("wait_revalidation","blocked_revalidation")
 x._handle_long_pending_candidate_result=handle
 status=x._process_long_pending_candidate(symbol="NEARUSDT",pending=p,
  current_candle_id=C+(2 if mode=="expired" else 1),progress=.2,max_pending_progress=.6)["status"]
 want={"ready":"ready","wait_preparation":"wait","wait_revalidation":"wait",
       "blocked_revalidation":"blocked","expired":"cleared"}[mode]
 assert status==want,(mode,status)
 pending[mode]=status
risk=0
for pos,count,allow in (({},0,True),({"side":"long"},0,False),({"side":"short"},0,False),({},1,False)):
 for meta in ({},{"lineage":{"source_signal_event_id":"s","source_signal_stream_id":"1794845694935-0"}}):
  x=obj();x._get_effective_position=lambda s,p=pos:p
  x._count_open_positions_for_side=lambda s,n=count:n
  with patch.dict(os.environ,{"LONG_SCALE_IN_ENABLE":"0"}):
   ok=x._evaluate_long_execution_risk_gate(symbol="NEARUSDT",side="long",
    price=3.9,interval="3m",extra={"score":.6,**meta})
  assert ok==allow,(pos,count,ok)
  risk+=1
async def path(mode):
 events.clear();x=obj()
 x._long_contra_context_gate=lambda **k:events.append("CONTRA") or mode!="contra"
 x._evaluate_long_execution_risk_gate=lambda **k:events.append("RISK") or mode!="risk"
 x._resolve_long_intent_price=lambda **k:events.append("PRICE") or (None if mode=="price" else 3.9)
 x._resolve_long_order_price=lambda **k:events.append("ORDER_PRICE") or 3.9
 kw=dict(symbol="NEARUSDT",side="long",price=3.9,signal_score=.6,
  decision_interval="3m",entry_interval="1m",exit_interval="1m",
  lifecycle_interval="3m",interval="3m",extra={"intent_id":"synthetic"},signal_label="offline")
 success=await x._execute_long_validated_candidate(**kw)
 expected={"contra":["CONTRA"],"risk":["CONTRA","RISK"],
  "price":["CONTRA","RISK","PRICE"],
  "ready":["CONTRA","RISK","PRICE","ORDER_PRICE","FAKE_ORDER_SINK"]}[mode]
 assert events==expected,(mode,events)
 assert success==(mode=="ready")
for mode in ("contra","risk","price","ready"):asyncio.run(path(mode))
print(json.dumps({"actual_executor_ast_methods":len(nodes),
 "pending_window_cases":len(windows),"pending_state_transitions":pending,
 "actual_execution_risk_metadata_ab_cases":risk,
 "guard_sequence_scenarios":4,"binance_orders":0,"redis_writes":0,
 "real_final_order_pipeline_tested":False},sort_keys=True))
# Additional non-order fault injection: exception during current-position count.
# Observed implementation catches Exception and returns True; document as hazard.
x=obj()
def broken_count(_): raise RuntimeError("simulated risk counter unavailable")
x._count_open_positions_for_side=broken_count
actual=x._evaluate_long_execution_risk_gate(
 symbol="NEARUSDT",side="long",price=3.9,interval="3m",extra={"score":.6})
print(json.dumps({"fault_injected_risk_counter_exception_allows_entry":bool(actual),
 "finding":"fail-open risk gate" if actual else "fail-closed risk gate",
 "production_changed":False,"order_calls":0},sort_keys=True))
