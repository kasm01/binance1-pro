"""Read-only reproducible research and architecture inventory; no orders."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import re,json,hashlib,redis,collections,subprocess,os
roots={'LONG1':Path('/home/kasm920/binance1-pro'),'SHORT1':Path('/home/kasm920/binance1')}
filename='research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json'
items={}
for side,root in roots.items():
 path=root/filename
 data=path.read_bytes()
 items[side]=dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),
                     bytes=len(data))
assert items['LONG1']['sha256']==items['SHORT1']['sha256']
ref=json.loads((roots['LONG1']/filename).read_text())
assert ref['long_wanted_count']==44 and ref['long_avoid_count']==26
def envscan(root):
 data={}
 duplicate=collections.Counter()
 for line in (root/'.env').read_text().splitlines():
  line=line.strip()
  if not line or line.startswith('#') or '=' not in line:continue
  k,v=line.split('=',1)
  duplicate[k]+=1
  if any(word in k.upper() for word in ('TOKEN','SECRET','API_KEY','PASSWORD','ARM_TOKEN','PASS_PHRASE')):continue
  data[k]=v.strip().strip('"').strip("'")
 return data,[k for k,n in duplicate.items() if n>1]
env={};duplicates={}
for side,path in roots.items():env[side],duplicates[side]=envscan(path)
def service(unit):
 cp=subprocess.run(['systemctl','--user','is-active',unit],capture_output=True,text=True)
 return cp.stdout.strip()
units=['binance1-long-supervisor.service','binance1-long1-native-stop.service',
 'binance1-long1-decision-shadow.service','binance1-central-risk-enforce-dry.service',
 'binance1-short1-model-shadow.service','binance1-short1-model-shadow-v6.service',
 'binance1-short1-entry-hazard-v44.service','binance1-short1-inj-shadow-signal-bus.service',
 'binance1-short1-v30-shadow.service']
states={unit:service(unit) for unit in units}
r=redis.Redis(decode_responses=True,socket_timeout=4)
tz=timezone(timedelta(hours=3))
source_summary={}
for k in ['telemetry:long1:context_adaptive_gate:v1','telemetry:short1:inj:model_shadow_v5',
'telemetry:short1:inj:model_shadow_v6','telemetry:short1:decision_funnel:v1',
'telemetry:central_risk:shadow','central:risk:requests:v1']:
 if r.type(k)!='stream':continue
 a=r.xrange(k,count=1);b=r.xrevrange(k,count=1)
 def t(v):
  return datetime.fromtimestamp(int(v[0][0].split('-')[0])/1000,tz).isoformat() if v else None
 source_summary[k]=dict(count=r.xlen(k),first_tr=t(a),last_tr=t(b))
profile={}
try:
 raw=r.get('telemetry:central_risk:shadow:current')
 obj=json.loads(raw) if raw else {}
 profile=dict(authority=obj.get('authority'),production_ready=obj.get('production_ready'),
   age_sec=int(datetime.now(timezone.utc).timestamp()-float(obj.get('ts') or 0)),
   exposure_status=(obj.get('exposure_health') or {}).get('status'))
except Exception:pass
# Detect old preflight literal expectations vs current .env, not auto-rewriting scripts.
preflight=(roots['SHORT1']/'scripts/short1_preflight.sh').read_text()
mismatches=[]
for k,want in re.findall(r'^eqv ([A-Z0-9_]+) ([^\s]+)',preflight,re.M):
 val=env['SHORT1'].get(k)
 if val is not None and val!=want:mismatches.append(dict(key=k,old_preflight_expected=want,current_config=val))
# categorize disabled knobs: don't mistake config presence for active pipeline.
disabled={}
for side,v in env.items():
 disabled[side]=[k for k,val in v.items() if k.endswith(('_ENABLE','_ENABLED')) and val.lower() in ('0','false','off')]
payload=dict(schema='binance1_coordination_audit_v1',research_only=True,no_live_settings_changed=True,
 reference=items,counts=dict(long_wanted=44,long_avoid=26,
 conflicts=sum(s['labels'][0]=='CONFLICT_NO_TRADE' for s in ref['derived_disjoint_segments'])),
 services=states,streams=source_summary,central_risk=profile,
 current_configs={side:{k:v.get(k) for k in (
 'SYMBOL','STRATEGY_ID','DRY_RUN','ARMED','LIVE_KILL_SWITCH','MODEL_SIGNAL_ROUTE',
 'LONG_ROLLING_MODEL_GATE_QUANTILE','LONG_CONTEXT_ADAPTIVE_GATE_ENABLE',
 'LONG_DYNAMIC_MODEL_GATE_ENABLE','LONG_CONTRA_GUARD_ENABLE',
 'SNIPER_ENTRY_MIN_CANDLE_PROGRESS','SNIPER_ENTRY_MAX_CANDLE_PROGRESS',
 'ENTRY_CONFIRM_ENABLE','MASTER_MIN_TRADE_SCORE','MASTER_SHORT_SOFT_SCORE_ENABLE',
 'MASTER_SHORT_SOFT_SCORE_MIN','MASTER_SHORT_HARD_CONTRA_PENDING_ENABLE',
 'MASTER_SHORT_HARD_CONTRA_PENDING_DRYRUN_ONLY','BRIDGE_SHORT_MICRO_GATE_FAIL_OPEN',
 'MAX_OPEN_POSITIONS','DEFAULT_ORDER_LEVERAGE','MAX_LEVERAGE',
 'SHORT_NATIVE_STOP_ENABLE','LONG1_NATIVE_STOP_AUTO_ENABLE','FIXED_ROI_TP_PCT',
 'FIXED_ROI_TP_GIVEBACK','CENTRAL_RISK_ENFORCE_DRY_RUN','PROFIT_LOCK_ENABLE',
 'LONG_SCALE_IN_ENABLE','SHORT_PENDING_REQUIRE_NEW_MODEL_PROOF')} for side,v in env.items()},
 duplicate_env_keys=duplicates,legacy_short_preflight_mismatches=mismatches,
 disabled_flags=disabled,
 risk_findings=[
 'SHORT1 live promotion currently blocked by its own read-only preflight',
 'SHORT1 DRY_RUN=1 ARMED=0 LIVE_KILL_SWITCH=1, no live SHORT main/orchestration processes',
 'LONG1 production entry path does not reference CentralRiskClient; short central request used when dry_run',
 'Central risk dry service active but central risk snapshot authority SHADOW_ONLY and production_ready False',
 'LONG adaptive entry gate currently shadow telemetry; dynamic model gate disabled; rolling enabled',
 'LONG Contra Guard in executor final safety, native pending distinct from Contra in-memory state',
 'Short preflight literal expected settings mismatched current runtime configuration',
 'SHORT1 model-shadow v5 and v6 use same program but distinct model directories and streams; do not call them exact duplicates',
 'SHORT INJ and LONG NEAR symbols require independent outcome labels',
 'VM disk >90% used; Redis no configured maxmemory, monitor memory',
 'Research reference never authorizes a live order; overlap is conflict_no_trade for both in training labels'])
out=roots['LONG1']/'research/shared_reference/LONG_SHORT_COORDINATION_AUDIT_V1.json'
out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
print('AUDIT_SAVED',out)
print('ENV_DUPLICATES',duplicates)
print('PREFLIGHT_MISMATCHES',len(mismatches),mismatches[:20])
print('RISK',profile)
print('SERVICES',states)
