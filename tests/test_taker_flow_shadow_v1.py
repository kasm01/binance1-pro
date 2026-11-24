import unittest
from scanner.shared_market_snapshot_v1 import parse_closed_klines
from scanner.closed_bar_bus_v1 import ClosedBarBus
from scanner.taker_flow_quality_shadow_v1 import assess_flow
from scanner.extreme_momentum_v1 import MS
START=1800000000000-(1800000000000%MS)
def rows(buy_frac=.7,price_direction=1):
 result=[];price=10
 for i in range(70):
  o=price;price=o*(1+price_direction*.0006)
  result.append({'t':START+i*MS,'o':o,'h':max(o,price)*1.0005,
    'l':min(o,price)*.9995,'c':price,'quote_volume':1000.,
    'taker_buy_quote_volume':1000.*buy_frac})
 return result
class Tests(unittest.TestCase):
 def test_long_and_short_pressure(self):
  for buy,direction,trend in ((.70,'LONG',1),(.30,'SHORT',-1)):
   x=assess_flow(rows(buy,trend),direction,observed_at_ms=START+70*MS)
   assert x['state']=='FLOW_SUPPORTIVE',x
   assert x['ready'] is False and x['order_authorized'] is False
 def test_opposing_flow_unverified_and_gap(self):
  a=assess_flow(rows(.30,1),'LONG',observed_at_ms=START+70*MS)
  assert a['state']=='FLOW_OPPOSING'
  b=rows();b[-1].pop('taker_buy_quote_volume')
  assert assess_flow(b,'LONG',observed_at_ms=START+70*MS)['state']=='FLOW_UNVERIFIED'
  b=rows();b[-10]['t']+=MS
  assert assess_flow(b,'LONG',observed_at_ms=START+70*MS)['state']=='FLOW_UNVERIFIED'
  assert assess_flow(rows(),'LONG',observed_at_ms=START+70*MS-1)['state']=='FLOW_UNVERIFIED'
 def test_rest_binance_index10_restored(self):
  raw=[]
  for i in range(70):
   r=rows()[i];raw.append([r['t'],str(r['o']),str(r['h']),str(r['l']),str(r['c']),
    '100',r['t']+MS-1,'1000',20,'70','700','0'])
  parsed=parse_closed_klines(raw,asof_ms=START+70*MS)
  assert parsed[0]['taker_buy_quote_volume']==700.
  assert assess_flow(parsed,'LONG',observed_at_ms=START+70*MS)['state']=='FLOW_SUPPORTIVE'
  raw[-1][10]='1100'
  with self.assertRaises(ValueError):parse_closed_klines(raw,asof_ms=START+70*MS)
 def test_ws_binance_Q_restored(self):
  bus=ClosedBarBus(['AAAUSDT'])
  raw=[]
  for i in range(180):
   t=START+i*MS
   raw.append([t,'10','10.1','9.9','10','100',t+MS-1,'1000',10,'70','700','0'])
  assert bus.bootstrap('AAAUSDT',raw,asof_ms=START+180*MS)
  t=START+180*MS
  event={'s':'AAAUSDT','k':{'s':'AAAUSDT','i':'1m','x':True,'t':t,
     'T':t+MS-1,'o':'10','h':'10.1','l':'9.9','c':'10',
     'v':'100','q':'1000','V':'70','Q':'700'}}
  assert bus.update_ws('AAAUSDT',event,observed_at_ms=t+MS+50)=='CLOSED_ACCEPTED'
  assert bus.data['AAAUSDT'][-1]['taker_buy_quote_volume']==700.
if __name__=='__main__':unittest.main()
