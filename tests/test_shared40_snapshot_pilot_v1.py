import unittest
from scanner.shared_market_snapshot_v1 import parse_closed_klines,evaluate
from scanner.extreme_momentum_v1 import MS
START=1794400000000-(1794400000000%MS)
ASOF=START+71*MS+13500
def source(direction=1,volume_factor=7):
 rows=[];price=5.0
 for i in range(72):
  new=price*(1+direction*.002)
  vol=1e6*(volume_factor if i>=65 else 1)
  rows.append([START+i*MS,str(price),str(max(price,new)*1.0001),
    str(min(price,new)*.9999),str(new),'0',START+(i+1)*MS-1,str(vol)])
  price=new
 return rows
class Tests(unittest.TestCase):
 def test_closed_partial_removed(self):
  k=source()
  d=parse_closed_klines(k,asof_ms=START+71*MS+500)
  assert len(d)==71
  assert d[-1]['t']==START+70*MS
 def test_consecutive_and_bad_timestamp(self):
  k=source()
  bad=k.copy();bad[17]=list(bad[17]);bad[17][0]+=MS
  with self.assertRaises(ValueError):parse_closed_klines(bad,asof_ms=ASOF)
  dup=k.copy();dup[18]=list(dup[17])
  with self.assertRaises(ValueError):parse_closed_klines(dup,asof_ms=ASOF)
  k2=source();k2[-1]=list(k2[-1]);k2[-1][6]+=1
  with self.assertRaises(ValueError):parse_closed_klines(k2,asof_ms=ASOF)
 def test_shared_one_source_opposite_sides(self):
  u=['RISEUSDT','FALLUSDT','UNKNOWNUSDT']
  a={'LONG1':['RISEUSDT','FALLUSDT','UNKNOWNUSDT'],
     'SHORT1':['RISEUSDT','FALLUSDT','UNKNOWNUSDT']}
  m={'RISEUSDT':source(1),'FALLUSDT':source(-1)}
  snap=evaluate(selected_symbols=u,bot_allocations=a,klines_by_symbol=m,
   observed_at_ms=ASOF,universe_time_ms=ASOF-5000)
  assert snap['unique_klines_sources_scanned']==3
  assert snap['per_symbol']['UNKNOWNUSDT']['status']=='INSUFFICIENT_DATA'
  assert snap['watch_candidates_by_direction']['LONG']==['RISEUSDT']
  assert snap['watch_candidates_by_direction']['SHORT']==['FALLUSDT']
  assert not snap['per_bot']['LONG1'][1]['watch_for_this_bot']
  assert not snap['per_bot']['SHORT1'][0]['watch_for_this_bot']
  assert not snap['no_order_authority'] is False
  assert all(not row['telegram_ready'] for b in snap['per_bot'].values() for row in b)
 def test_reject_old_universe_future_and_unknown(self):
  args=dict(selected_symbols=['RISEUSDT'],bot_allocations={'LONG1':['RISEUSDT']},
    klines_by_symbol={'RISEUSDT':source()},observed_at_ms=ASOF)
  with self.assertRaises(ValueError):
   evaluate(**args,universe_time_ms=ASOF-1000000,universe_ttl_ms=120000)
  with self.assertRaises(ValueError):
   evaluate(**args,universe_time_ms=ASOF+1)
  with self.assertRaises(ValueError):
   evaluate(**dict(args,bot_allocations={'LONG5':['RISEUSDT']}),universe_time_ms=ASOF)
  with self.assertRaises(ValueError):
   evaluate(**dict(args,selected_symbols=['RISEUSDT','RISEUSDT']),universe_time_ms=ASOF)
 def test_fail_closed_bad_bar(self):
  bad=source()
  bad[-4]=list(bad[-4]);bad[-4][4]='nan'
  x=evaluate(selected_symbols=['RISEUSDT'],bot_allocations={'LONG1':['RISEUSDT']},
   klines_by_symbol={'RISEUSDT':bad},observed_at_ms=ASOF,
   universe_time_ms=ASOF)
  assert x['per_symbol']['RISEUSDT']['reason']=='INVALID_SOURCE'
  assert not x['per_bot']['LONG1'][0]['watch_for_this_bot']
if __name__=='__main__':unittest.main()
