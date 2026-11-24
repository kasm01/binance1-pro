import unittest,os
from unittest.mock import patch
from scanner.execution_cost_shadow_v1 import assess_quote
from scanner.cost_quote_public_v1 import check_candidate
NOW=1800000000100
CTX={'schema':'manual_context_entry_shadow.v1','state':'COST_PENDING',
     'symbol':'AAAUSDT','direction':'LONG',
     'observed_at_ms':NOW-250,'atr14_1m_pct':0.40}
def quote(bid='10.000',ask='10.003',bidQty='1000',askQty='1000'):
 return {'symbol':'AAAUSDT','bidPrice':bid,'askPrice':ask,
         'bidQty':bidQty,'askQty':askQty}
class Tests(unittest.TestCase):
 def test_quote_budget_pass_still_no_ready(self):
  x=assess_quote('AAAUSDT','LONG',CTX,quote(),now_ms=NOW)
  assert x['state']=='COST_ESTIMATE_PASS',x
  assert x['ready'] is False and x['order_authorized'] is False
  assert x['fee_tier_verified'] is False
  assert x['slippage_verified'] is False
  assert x['funding_cost_verified'] is False
  assert x['spread_bps']>0
  assert x['assumed_roundtrip_bps']>20
 def test_wide_spread(self):
  x=assess_quote('AAAUSDT','LONG',CTX,quote(ask='10.025'),now_ms=NOW)
  assert x['state']=='COST_REJECT' and x['reason']=='wide_spread'
 def test_shallow_best_bid_and_ask(self):
  for qty in [('3','1000'),('1000','3')]:
   x=assess_quote('AAAUSDT','SHORT',dict(CTX,direction='SHORT'),
       quote(bidQty=qty[0],askQty=qty[1]),now_ms=NOW)
   assert x['state']=='COST_REJECT' and x['reason']=='shallow_best_quote'
 def test_invalid_stale_wrong_identity(self):
  for b in (quote(bid='nan'),quote(ask='0'),quote(bid='12',ask='10')):
   assert assess_quote('AAAUSDT','LONG',CTX,b,now_ms=NOW)['state']=='COST_PENDING'
  assert assess_quote('AAAUSDT','LONG',CTX,quote(),now_ms=NOW+10000)['state']=='COST_PENDING'
  assert assess_quote('AAAUSDT','LONG',dict(CTX,symbol='BBB USDT'),quote(),now_ms=NOW)['reason']=='mismatched_context_identity'
  assert assess_quote('AAAUSDT','LONG',CTX,dict(quote(),symbol='BBB USDT'),now_ms=NOW)['reason']=='quote_missing_or_wrong_symbol'
 def test_low_stop_budget_reject(self):
  c=dict(CTX,atr14_1m_pct=.02)
  x=assess_quote('AAAUSDT','LONG',c,quote(),now_ms=NOW)
  assert x['state']=='COST_REJECT' and x['reason']=='assumed_cost_over_35pct_of_2atr'
 def test_no_quote_if_context_not_eligible(self):
  calls=[]
  x=check_candidate(dict(CTX,state='ENTRY_PENDING'),
      get=lambda *a,**kw:calls.append(True))
  assert x['state']=='NOT_QUERIED' and not calls
 def test_public_rest_faux_payload_does_not_send_order(self):
  class Fake:
   def raise_for_status(self):pass
   def json(self):return quote()
  calls=[]
  def get(url,**kwargs):
   assert url.endswith('/fapi/v1/ticker/bookTicker')
   assert kwargs['params']=={'symbol':'AAAUSDT'}
   calls.append(url);return Fake()
  with patch('time.time',return_value=NOW/1000):
   result=check_candidate(CTX,get=get)
  assert len(calls)==1
  assert result['state']=='COST_ESTIMATE_PASS'
  assert not result['order_authorized'] and not result['ready']
  assert result['quote_exchange_timestamp_verified'] is False
 def test_status_contains_short_lived_cost_research_without_ready(self):
  from scanner.manual_watch_runner_v1 import make_status
  from scanner.closed_bar_bus_v1 import ClosedBarBus
  from tests.test_context_entry_shadow_v1 import fixture,ASOF
  bus=ClosedBarBus(['AAAUSDT'])
  bus.data['AAAUSDT'].extend(fixture())
  alloc={'LONG1':['AAAUSDT'],'SHORT1':['AAAUSDT']}
  costs={'AAAUSDT':{'asof_ms':ASOF,'state':'COST_ESTIMATE_PASS',
                    'reason':'indicative_cost_under_research_budget',
                    'spread_bps':3.0,'assumed_roundtrip_bps':23.0}}
  x=make_status(bus,alloc,ASOF,{'excluded_top_volume_15':[]},
                latest_cost_checks=costs)
  assert x['cost_gate_mode']=='SHADOW_ONLY_INDICATIVE_COST_NO_READY'
  assert x['order_authorized'] is False
  assert x['confirmed_telegram_sends_since_start']==0
  assert all(v['research_ready'] is False for v in x['last_signals'])
  assert all(v['research_entry_confirmed'] is False for v in x['last_signals'])
if __name__=='__main__':unittest.main()
