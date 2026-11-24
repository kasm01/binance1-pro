import asyncio,os,unittest
from unittest.mock import patch
from scanner.universe_40_v1 import select
from tg_bot.signal_center_v1 import normalize,format_message,SignalDispatcher
from tg_bot.read_only_commands_v1 import authorized,allowed_ids,answer,handle
from tg_bot.transport_v1 import send
class CenterTest(unittest.TestCase):
 def setUp(self):
  self.ex={'symbols':[{'symbol':f'COIN{i}USDT','baseAsset':f'COIN{i}',
      'quoteAsset':'USDT','contractType':'PERPETUAL','status':'TRADING'} for i in range(70)]}
  self.ticks=[{'symbol':f'COIN{i}USDT','quoteVolume':str((70-i)*1_000_000)} for i in range(70)]
  self.signal=dict(symbol='COIN32USDT',strategy='LONG1',state='READY',
       observed_at_ms=100000,price=12.3,reason='Test için kapalı 15m trend',
       signal_asof_verified=True,market_context_verified=True,
       entry_confirmation_verified=True,cost_check_pass=True)
 def test_40_shared_universe_exclude15(self):
  x=select(self.ex,self.ticks,min_quote_volume_usdt=5e6)
  assert x['unique_count']==40 and x['selected_symbols'][0]=='COIN15USDT'
  assert x['selected_symbols'][-1]=='COIN54USDT'
  assert x['excluded_top_rank_symbols']==[f'COIN{i}USDT' for i in range(15)]
  assert set(x['bot_allocations'])=={f'{s}{i}' for s in ('LONG','SHORT') for i in range(1,5)}
  for i in range(1,5):
   assert x['bot_allocations'][f'LONG{i}']==x['bot_allocations'][f'SHORT{i}']
   assert len(x['bot_allocations'][f'LONG{i}'])==10
  assert len(set(sum((x['bot_allocations'][f'LONG{i}'] for i in range(1,5)),[])))==40
  assert not x['live_order_authority']
 def test_no_ineligible_pair_or_forced_fill(self):
  x=self.ex.copy()
  x['symbols']=self.ex['symbols'][:30]+[
   {'symbol':'BTCUSDC','baseAsset':'BTC','quoteAsset':'USDC','contractType':'PERPETUAL','status':'TRADING'},
   {'symbol':'ZZZUSDT','baseAsset':'ZZZ','quoteAsset':'USDT','contractType':'CURRENT_QUARTER','status':'TRADING'}]
  y=select(x,self.ticks,min_quote_volume_usdt=2e6)
  assert y['unique_count']==15 and len(y['bot_allocations']['LONG3'])==0
 def test_validation(self):
  for bad in (dict(self.signal,strategy='LONG5'),dict(self.signal,state='ORDER'),
    dict(self.signal,price=-1),dict(self.signal,reason='abc\nxyz')):
   with self.assertRaises(ValueError):normalize(bad)
  assert 'OTOMATİK EMİR YOK' in format_message(self.signal)
  assert 'MANUEL' in format_message(self.signal)
 def test_no_telegram_unless_double_optin(self):
  calls=[]
  d=SignalDispatcher(sender=lambda s:calls.append(s) or True,
      bot_allocations={'LONG1':{'COIN32USDT'}})
  with patch.dict(os.environ,{'TELEGRAM_SIGNAL_CENTER_ENABLED':'0',
                              'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'0'}):
   assert d.dispatch(self.signal,now_ms=100001)=='PREVIEW_ONLY'
   assert calls==[]
  with patch.dict(os.environ,{'TELEGRAM_SIGNAL_CENTER_ENABLED':'1',
                              'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'1'}):
   assert d.dispatch(self.signal,now_ms=100001)=='SENT'
   assert d.dispatch(self.signal,now_ms=100002)=='DEDUPED'
   assert d.dispatch(dict(self.signal,state='INVALIDATED'),now_ms=100003)=='SENT'
  assert len(calls)==2
 def test_ready_requires_evidence_and_allocation(self):
  with self.assertRaises(ValueError):
   normalize(dict(self.signal,cost_check_pass=False))
  c=[]
  d=SignalDispatcher(sender=lambda s:c.append(s) or True)
  with patch.dict(os.environ,{'TELEGRAM_SIGNAL_CENTER_ENABLED':'1',
                              'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'1'}):
   assert d.dispatch(self.signal,now_ms=100001)=='SYMBOL_NOT_ALLOCATED_TO_STRATEGY'
  assert not c
 def test_old_signal_rejected(self):
  assert SignalDispatcher().dispatch(self.signal,now_ms=300001)=='STALE'
 def test_delivery_never_assumes_success(self):
  class Fake:
   status_code=200
   def json(self):return {'ok':False}
  post_calls=[]
  def post(url,**kw):
   post_calls.append(True)
   return Fake()
  with patch.dict(os.environ,{'TELEGRAM_SIGNAL_CENTER_ENABLED':'0',
       'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'0',
       'TELEGRAM_CHAT_ID':'111','TELEGRAM_BOT_TOKEN':'fixture-no-real-token'}):
   assert not send('test',post=post) and not post_calls
  with patch.dict(os.environ,{'TELEGRAM_SIGNAL_CENTER_ENABLED':'1',
       'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'1',
       'TELEGRAM_ALLOWED_CHAT_IDS':'333',
       'TELEGRAM_CHAT_ID':'111','TELEGRAM_BOT_TOKEN':'fixture-no-real-token'}):
   assert not send('test',post=post) and not post_calls
  with patch.dict(os.environ,{'TELEGRAM_SIGNAL_CENTER_ENABLED':'1',
       'TELEGRAM_SIGNAL_CENTER_SEND_ENABLED':'1',
       'TELEGRAM_ALLOWED_CHAT_IDS':'111',
       'TELEGRAM_CHAT_ID':'111','TELEGRAM_BOT_TOKEN':'fixture-no-real-token'}):
   assert not send('test',post=post) and len(post_calls)==1
 def test_access_fail_closed(self):
  assert not authorized(111,222,chats=set(),users=set())
  assert authorized(111,222,chats={111},users=set())
  assert not authorized(111,222,chats={111},users={333})
  assert not authorized(333,222,chats={111},users=set())
  assert allowed_ids('1,2,nonsense')=={1,2}
  assert 'manuel' in answer('risk').lower()
 def test_command_auth(self):
  class Message:
   text='/status'
   def __init__(self):self.received=[]
   async def reply_text(self,t):self.received.append(t)
  class Obj:
   id=123
  class Update:
   effective_chat=Obj()
   effective_user=Obj()
   effective_message=Message()
  x=Update()
  with patch.dict(os.environ,{'TELEGRAM_ALLOWED_CHAT_IDS':'456'},clear=False):
   asyncio.run(handle(x,None))
  assert 'Yetkisiz' in x.effective_message.received[0]
if __name__=='__main__':unittest.main()
