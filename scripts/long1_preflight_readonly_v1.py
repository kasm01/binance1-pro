#!/usr/bin/env python3
"""Read-only LONG1 operational preflight.

Does not change config, daemon state, Redis, exchange orders or positions.
Its assertions are operational observations, not authorization to trade.
"""
from __future__ import annotations
import json,os,sys,subprocess,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
load_dotenv(ROOT/'.runtime_secrets.env',override=False)
def truth(name):return str(os.getenv(name,'')).lower() in ('1','on','yes','true')
def val(name,default=''):return os.getenv(name,default)
def unit(name):
    p=subprocess.run(['systemctl','--user','is-active',name],capture_output=True,text=True,timeout=5)
    return p.stdout.strip() or 'unknown'
findings=[]
def note(level,kind,detail):
    findings.append(dict(level=level,kind=kind,detail=detail))
def main():
    cfg={
      k:val(k) for k in (
       'SYMBOL','DRY_RUN','ARMED','LIVE_KILL_SWITCH','MAX_OPEN_POSITIONS','MAX_LEVERAGE',
       'PER_POSITION_BALANCE_PCT','LONG_SCALE_IN_ENABLE',
       'LONG_ROLLING_MODEL_GATE_ENABLE','LONG_ROLLING_MODEL_GATE_QUANTILE',
       'LONG_ROLLING_MODEL_GATE_MIN','LONG_ROLLING_MODEL_GATE_MAX',
       'LONG_DYNAMIC_MODEL_GATE_ENABLE','LONG_CONTEXT_ADAPTIVE_GATE_ENABLE',
       'LONG_CONTRA_GUARD_ENABLE','ENTRY_CONFIRM_ENABLE',
       'SNIPER_ENTRY_MIN_CANDLE_PROGRESS','SNIPER_ENTRY_MAX_CANDLE_PROGRESS',
       'FIXED_ROI_TP_ENABLE','FIXED_ROI_TP_PCT','FIXED_ROI_TP_GIVEBACK',
       'PROFIT_LOCK_ENABLE','LONG_DYNAMIC_STOP_ENABLE',
       'LONG1_NATIVE_STOP_AUTO_ENABLE','SL_PCT',
       'LONG_DYNAMIC_STOP_CATASTROPHIC_PCT')}
    services={
     s:unit(s) for s in (
       'binance1-long-supervisor.service','binance1-long1-native-stop.service',
       'binance1-long1-decision-shadow.service','binance1-central-risk-enforce-dry.service')}
    for s,state in services.items():
        if s in ('binance1-long-supervisor.service','binance1-long1-native-stop.service'):
            if state!='active':note('BLOCK','required_service',f'{s}={state}')
        elif state!='active':note('WARN','research_or_risk_service',f'{s}={state}')
    if truth('DRY_RUN') or not truth('ARMED') or truth('LIVE_KILL_SWITCH'):
        note('WARN','live_flags','LONG1 not in expected live mode, may be intentionally disarmed')
    if cfg['SYMBOL']!='NEARUSDT':note('WARN','symbol_mismatch',cfg['SYMBOL'])
    if cfg['MAX_OPEN_POSITIONS']!='1' or truth('LONG_SCALE_IN_ENABLE'):
        note('BLOCK','single_position_invariant','expected one position and layering disabled')
    if not truth('LONG_ROLLING_MODEL_GATE_ENABLE'):
        note('WARN','rolling_score_authority','rolling model gate disabled')
    else:
        note('INFO','rolling_score_authority','rolling quantile is the entry score authority; MIN is NOT the actual fixed threshold')
    if truth('LONG_DYNAMIC_MODEL_GATE_ENABLE'):
        note('INFO','dynamic_model_gate','separate legacy model gate enabled; inspect interaction')
    if truth('LONG_CONTEXT_ADAPTIVE_GATE_ENABLE'):
        note('INFO','adaptive_gate','current adaptive market context is shadow telemetry only, not order permission')
    if not truth('LONG_CONTRA_GUARD_ENABLE') or not truth('ENTRY_CONFIRM_ENABLE'):
        note('BLOCK','entry_safety','contra or entry confirmation switched off')
    if not truth('LONG1_NATIVE_STOP_AUTO_ENABLE'):
        note('BLOCK','native_stop','native reconciler explicitly disabled')
    note('INFO','exit_authority',
         'Fixed direct gross ROI TP='+cfg['FIXED_ROI_TP_PCT']+
         ', giveback='+cfg['FIXED_ROI_TP_GIVEBACK']+
         '; PROFIT_LOCK_ENABLE='+cfg['PROFIT_LOCK_ENABLE'])
    redis_data={}
    try:
        import redis
        r=redis.Redis(host=val('REDIS_HOST','127.0.0.1'),port=int(val('REDIS_PORT','6379')),
            db=int(val('REDIS_DB','0')),decode_responses=True,socket_timeout=3)
        redis_data['ping']=bool(r.ping())
        for k in ('signals_stream_long1','trade_intents_stream_long1','exec_events_stream_long1'):
            if r.type(k)=='stream':
                z=r.xrevrange(k,count=1)
                redis_data[k]=dict(count=r.xlen(k),last_age_sec=
                 round(time.time()-int(z[0][0].split('-')[0])/1000,1) if z else None)
        key='telemetry:central_risk:shadow:current'
        raw=r.get(key)
        if raw:
            obj=json.loads(raw)
            redis_data['central_risk']=dict(age_sec=round(time.time()-float(obj.get('ts') or 0),1),
                 authority=obj.get('authority'),production_ready=obj.get('production_ready'),
                 exposure_health=(obj.get('exposure_health') or {}).get('status'))
            if obj.get('production_ready') is not True:
                note('WARN','central_risk_authority','current risk master is SHADOW ONLY, not a shared production hard gate')
        else:note('WARN','central_risk_data','central snapshot missing')
    except Exception as exc:
        note('BLOCK','redis_failure',type(exc).__name__)
    exchange={}
    try:
        from core.binance_futures_v3 import signed_get,position_risk
        positions=position_risk('NEARUSDT')
        active=[p for p in positions if abs(float(p.get('positionAmt') or 0))>0]
        normal=signed_get('/fapi/v1/openOrders',{'symbol':'NEARUSDT'})
        algos=signed_get('/fapi/v1/openAlgoOrders',{'symbol':'NEARUSDT'})
        exchange=dict(nonzero_positions=len(active),normal_orders=len(normal),algo_orders=len(algos),
           positions=[dict(side=p.get('positionSide'),qty=p.get('positionAmt'),leverage=p.get('leverage')) for p in active])
        if active:
            has_long=any(float(p.get('positionAmt') or 0)>0 for p in active)
            protective=[o for o in algos if o.get('side')=='SELL' and
                str(o.get('orderType') or o.get('type'))=='STOP_MARKET']
            if has_long and not protective:
                note('BLOCK','exchange_stop_absent','live LONG detected without matching native SELL STOP_MARKET algo')
            else:note('INFO','exchange_stop','nonflat position; STOP presence checked, exact stop coverage requires full reconcile')
        else:note('INFO','exchange_flat','no open NEAR position; empty native stop count is expected')
    except Exception as exc:
        note('BLOCK','exchange_read_failed',type(exc).__name__+':'+str(exc)[:130])
    latch={}
    try:
        from core.long1_native_stop_fail_safe import KEY,DISK_LATCH
        latch=dict(disk_latch=DISK_LATCH.exists(),redis_latch=r.get(KEY))
        if latch['disk_latch'] or latch['redis_latch'] not in (None,'','0'):
            note('WARN','native_stop_latch','safety latch present; investigate before any entry')
    except Exception as exc:
        note('BLOCK','latch_read_failed',type(exc).__name__)
    report=dict(schema='long1_preflight_readonly_v1',generated_utc=datetime.now(timezone.utc).isoformat(),
      live_order_authority=False,read_only=True,config=cfg,services=services,
      redis=redis_data,exchange=exchange,safety_latch=latch,
      findings=findings,
      status='BLOCKED' if any(x['level']=='BLOCK' for x in findings) else
         'WARN' if any(x['level']=='WARN' for x in findings) else 'PASS')
    out=ROOT/'research/results/LONG1_PREFLIGHT_READONLY_LATEST.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],findings=findings,services=services,
         exchange=exchange,safety_latch=latch,output=str(out)),ensure_ascii=False,indent=2))
    return 2 if report['status']=='BLOCKED' else 0
if __name__=='__main__':
    sys.exit(main())
