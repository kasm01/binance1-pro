import tempfile
import unittest
from pathlib import Path
from tg_bot.telegram_auth_probe_v1 import check,read_credentials
class Fake:
 def __init__(self,code=200):self.status_code=code
 def json(self):return {'ok':True,'result':{}}
class Test(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.p=Path(self.tmp.name)/'tg.env'
  self.p.write_text("TELEGRAM_BOT_TOKEN='1234567890:valid_fixture_abcdefghijklmnopqr'\n"
     "TELEGRAM_CHAT_ID='111111'\nTELEGRAM_ALLOWED_CHAT_IDS='111111'\n")
 def test_good_two_readonly_requests(self):
  n=[]
  def getter(url,**kwargs):
   n.append(url.split('/')[-1]);return Fake()
  x=check(get=getter,path=self.p)
  assert x=={'status':'AUTH_AND_CHAT_VALID','messages_sent':0}
  assert n==['getMe','getChat']
 def test_no_delivery_when_unauthorized(self):
  n=[]
  def getter(url,**kwargs):
   n.append(url);return Fake(401)
  assert check(get=getter,path=self.p)['status']=='BOT_TOKEN_UNAUTHORIZED'
  assert len(n)==1
 def test_invalid_chat_or_missing(self):
  self.p.write_text("TELEGRAM_BOT_TOKEN='1234567890:valid_fixture_abcdefghijklmnopqr'\n"
    "TELEGRAM_CHAT_ID='111111'\nTELEGRAM_ALLOWED_CHAT_IDS='222222'\n")
  assert read_credentials(self.p) is None
  assert check(path=self.p)['status']=='CONFIG_INVALID'
if __name__=='__main__':unittest.main()
