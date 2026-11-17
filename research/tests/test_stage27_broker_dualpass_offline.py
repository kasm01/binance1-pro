"""Pure injected Binance GET fixtures, fail closed, no network or Redis."""
import copy,json
from research.staging.stage27_broker_consistency_evidence_v1 import capture,SYMBOLS

T=1794948000000
def base():
    return {
      "account":{"totalMarginBalance":"100","availableBalance":"80",
                 "totalInitialMargin":"0",
                 "totalOpenOrderInitialMargin":"0",
                 "totalPositionInitialMargin":"0","positions":[]},
      "positions":[],
      "orders":{s:[] for s in SYMBOLS},
      "algos":{s:[] for s in SYMBOLS},
      "end_ms":T+750,
    }

def run(alter=None):
    state=base()
    if alter:alter(state)
    calls=[]
    def account():
        calls.append('account')
        return copy.deepcopy(state['account'])
    def pos():
        calls.append('positionRisk')
        return copy.deepcopy(state['positions'])
    def orders(symbol):
        calls.append('orders:'+symbol)
        return copy.deepcopy(state['orders'][symbol])
    def algos(symbol):
        calls.append('algos:'+symbol)
        return copy.deepcopy(state['algos'][symbol])
    ticks=iter([T,state['end_ms']])
    result=capture(get_account=account,get_all_position_risk=pos,
       get_open_orders=orders,get_open_algos=algos,clock_ms=lambda:next(ticks))
    return result,calls
ok,calls=run()
assert ok.state=="CONSISTENT_READONLY_ONLY" and ok.fingerprint and len(ok.fingerprint)==64
assert ok.source_authenticated is False and ok.independently_verified_account_id is False
assert ok.live_order_authorized is False
assert calls==['account','positionRisk','orders:NEARUSDT','algos:NEARUSDT',
              'orders:INJUSDT','algos:INJUSDT','positionRisk','account'],calls
def change(field,value):
    return lambda state:state.__setitem__(field,value)
def setnested(field,key,value):
    return lambda state:state[field].__setitem__(key,value)
nonflat={"symbol":"NEARUSDT","positionSide":"LONG","positionAmt":"1"}
invalid={
 "account_absent":change("account",None),
 "margin_nan":setnested("account","totalMarginBalance","NaN"),
 "outside_scope_open_order_margin":setnested("account","totalOpenOrderInitialMargin","0.1"),
 "outside_scope_position_margin":setnested("account","totalPositionInitialMargin","0.1"),
 "invalid_available":setnested("account","availableBalance","120"),
 "account_missing_positions":lambda v:v['account'].pop('positions'),
 "broker_positions_missing":change('positions',None),
 "broker_position_nan":change('positions',[dict(nonflat,positionAmt="NaN")]),
 "broker_position_duplicate":change('positions',[nonflat,nonflat]),
 "broker_position_wrong_sign":change('positions',[dict(nonflat,positionAmt="-1")]),
 "broker_nonflat_conflict":change('positions',[nonflat]),
 "broker_matching_nonflat_requires_reconcile":lambda v: (
    v['positions'].append(nonflat),v['account']['positions'].append(nonflat)),
 "broker_position_other_symbol":lambda v: (
    v['positions'].append(dict(nonflat,symbol="BTCUSDT")),
    v['account']['positions'].append(dict(nonflat,symbol="BTCUSDT"))),
 "missing_regular_orders":lambda v:v['orders'].__setitem__('NEARUSDT',None),
 "missing_algo_orders":lambda v:v['algos'].__setitem__('INJUSDT',None),
 "malformed_regular_order":lambda v:v['orders']['NEARUSDT'].append({"symbol":"NEARUSDT"}),
 "wrong_algo_symbol":lambda v:v['algos']['NEARUSDT'].append({"symbol":"INJUSDT","algoId":4}),
 "standard_open_order":lambda v:v['orders']['NEARUSDT'].append({"symbol":"NEARUSDT","orderId":123}),
 "algo_open_order":lambda v:v['algos']['INJUSDT'].append({"symbol":"INJUSDT","algoId":456}),
 "stale_capture":change('end_ms',T+6000),
 "reverse_clock":change('end_ms',T-1),
}
results={}
for name,mut in invalid.items():
    outcome,_=run(mut)
    assert outcome.state=="UNKNOWN" and not outcome.live_order_authorized,(name,outcome)
    results[name]=outcome.reason
# Explicitly catch motion BETWEEN first and second GET responses.
from research.staging.stage27_broker_consistency_evidence_v1 import capture
def drift(kind):
    ticks=iter([T,T+500])
    reads={"account":0,"pos":0}
    def acc():
        reads["account"]+=1
        value=copy.deepcopy(base()["account"])
        if kind=="account" and reads["account"]==2:
            value["availableBalance"]="79"
        return value
    def pos():
        reads["pos"]+=1
        return [nonflat] if kind=="position" and reads["pos"]==2 else []
    return capture(get_account=acc,get_all_position_risk=pos,
            get_open_orders=lambda s:[],get_open_algos=lambda s:[],
            clock_ms=lambda:next(ticks))
for kind in ("position","account"):
    result=drift(kind)
    assert result.state=="UNKNOWN" and result.live_order_authorized is False,(kind,result)
print(json.dumps({"flat_stable_candidate":True,"full_broker_read_calls":len(calls),
  "negative_cases":len(results)+2,"negative_all_unknown":True,
  "independent_account_identity_verified":False,
  "source_authenticated":False,"live_order_authorized":False,
  "exchange_calls":0,"redis_writes":0,"result":"PASS"},sort_keys=True))
