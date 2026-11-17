"""Read-only release gate for LONG1+SHORT1. Always conservative on UNKNOWN.

Does not start services, change env, make network or Redis requests, or order.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone
import json,os,re,subprocess
from dotenv import dotenv_values
LONG=Path.home()/'binance1-pro'
SHORT=Path.home()/'binance1'
live_source=(LONG/'core/trade_executor.py').read_text()
short_source=(SHORT/'core/trade_executor_short.py').read_text()
main_source=(LONG/'main.py').read_text()
master_source=(LONG/'orchestration/executor/master_executor.py').read_text()
long_env=dotenv_values(LONG/'.env')
short_env=dotenv_values(SHORT/'.env')
long_runtime=dotenv_values(LONG/'.runtime_secrets.env')
short_runtime=dotenv_values(SHORT/'.runtime_secrets.env')
def effective(config,runtime,key):
    return config.get(key) or runtime.get(key)
same_effective_keys=bool(
    effective(long_env,long_runtime,'BINANCE_API_KEY') and
    effective(short_env,short_runtime,'BINANCE_API_KEY') and
    effective(long_env,long_runtime,'BINANCE_API_KEY')==
        effective(short_env,short_runtime,'BINANCE_API_KEY') and
    effective(long_env,long_runtime,'BINANCE_API_SECRET') and
    effective(short_env,short_runtime,'BINANCE_API_SECRET') and
    effective(long_env,long_runtime,'BINANCE_API_SECRET')==
        effective(short_env,short_runtime,'BINANCE_API_SECRET'))
def stack_off():
 p=subprocess.run([str(LONG/'scripts/binance1_stack_control.sh'),'check'],
  capture_output=True,text=True,timeout=9)
 if p.returncode:return False
 lines=p.stdout.splitlines()
 # Expect only three section headers, no active unit/collector lines.
 return (len(lines)==3 and all(line.startswith('[STACK]') for line in lines))
services_off=stack_off()
api_keys_differ=not same_effective_keys
# Different keys are not proof of different Binance accounts. Do not assume
# shared account until independent broker-backed identity is established.
central_live_imports=any('orchestration.risk.central_risk_master' in x or
 'CentralRiskMaster(' in x for x in (live_source,main_source,master_source))
risk_fail_open_known=('except Exception:' in live_source and
                      'def _count_open_positions_for_side' in live_source)
native_stop_off=subprocess.run(['systemctl','--user','is-active',
    'binance1-long1-native-stop.service'],capture_output=True,text=True).stdout.strip()!='active'
results={
 'bots_stopped':{'ok':services_off,'blocking':False,
    'detail':'required safe paused state for offline handoff'},
 'account_identity_broker_verified':{'ok':False,'blocking':True,
    'detail':('same effective API credential pair found across bot configurations, '
     'but independently attested account ID and authoritative snapshot linkage are still missing')
    if same_effective_keys else 'effective API credentials differ or unavailable; account identity unknown'},
 'central_risk_live_authority_integrated':{'ok':False,'blocking':True,
    'detail':('source mentions CentralRiskMaster, but not proven bound to final order gate'
     if central_live_imports else 'no CentralRiskMaster direct import/call found in LONG1 order chain')},
 'short1_live_central_risk_authority_integrated':{'ok':False,'blocking':True,
    'detail':'SHORT1 has Execution Risk and Final Safety, but no synchronous centralized shared reservation in its verified live order path'},
 'live_position_uncertainty_fail_closed':{'ok':(
      'from core.strict_position_count_v1 import count_side' in live_source and
      'live_count = self._count_open_positions_for_side(side_norm)' in live_source and
      'return False' in live_source),
   'blocking':True,
   'detail':'Stage24 strict full-account position count + fail-closed risk verified using actual AST and fault injection; still requires external final safety'},
 'both_engines_share_hard_live_open_veto':{'ok':(
      'from core.joint_risk_live_guard_v1 import check_new_open' in live_source and
      'from core.joint_risk_live_guard_v1 import check_new_open' in short_source),
   'blocking':True,
   'detail':'both live OPEN entrypoints + exchange emitters call same fail-closed module; verified tests show zero order authority'},
 'live_fencing_authenticated':{'ok':False,'blocking':True,
    'detail':'stage19-22 research proofs are synthetic and independent of live order path'},
 'live_final_safety_order_fill_stop_e2e':{'ok':False,'blocking':True,
    'detail':'only mock sink tested; actual fills/stop lifecycle not executed'},
 'central_production_profile_authorized':{'ok':False,'blocking':True,
    'detail':'current central enforce-dry profile production_authorized=False'},
 'standby_native_stop_service_running':{'ok':not native_stop_off,'blocking':False,
    'detail':'native stop intentionally stopped with all bots, must be ACTIVE before any live entry'},
 'long1_env_is_live_if_started':{'ok':long_env.get('DRY_RUN')!='0','blocking':True,
    'detail':'LONG1 has DRY_RUN=0, so shadow_start can launch live strategy'},
 'short1_env_paper_only':{'ok':short_env.get('DRY_RUN')=='1','blocking':False,
    'detail':'SHORT1 remains paper-only by declared env'}
}
status='NO_GO' if any(x['blocking'] and not x['ok'] for x in results.values()) else 'REVIEW_REQUIRED'
report={
 'schema':'joint_release_gate.stage23.v1','audited_at_utc':datetime.now(timezone.utc).isoformat(),
 'state':status,'live_orders_authorized':False,
 'effective_api_credentials_match':same_effective_keys,
 'account_identity_same_or_different':'CONFIG_CREDENTIALS_MATCH_BROKER_ID_UNVERIFIED' if same_effective_keys else 'UNKNOWN',
 'blocking_count':sum(x['blocking'] and not x['ok'] for x in results.values()),
 'tests_prior_stages':'stage20_signed_GET_readonly;stage21_mock17;stage22_isolated_AOF',
 'checks':results}
destination=LONG/'research/results/LONG1_SHORT1_STAGE23_RELEASE_GATE_20261118.json'
destination.parent.mkdir(exist_ok=True)
destination.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'state':status,'blocking_count':report['blocking_count'],
 'effective_api_credentials_match':same_effective_keys,'broker_account_id_attested':False,
 'services_off':services_off,'live_orders_authorized':False,
 'report_path':str(destination.relative_to(LONG))},sort_keys=True))
raise SystemExit(3 if status=='NO_GO' else 0)
