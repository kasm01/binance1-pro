"""Telegram BOT auth check; reports status only. No messages sent.

CLI opt-in. Reads the dedicated signal-only secrets file, not old Binance .env.
No tokens, chat IDs, or API URLs printed.
"""
from __future__ import annotations
import argparse,json,os,shlex
from pathlib import Path
from tg_bot.read_only_commands_v1 import allowed_ids
PRIVATE=Path.home()/'.config/binance1-manual-signal/telegram.env'
def read_credentials(path=PRIVATE):
 if not path.is_file():return None
 try:
  env={}
  for line in path.read_text().splitlines():
   if not line.strip() or line.strip().startswith('#'):continue
   key,rest=line.split('=',1)
   if key not in {'TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID','TELEGRAM_ALLOWED_CHAT_IDS'}:
    continue
   parsed=shlex.split(rest)
   if len(parsed)!=1:return None
   env[key]=parsed[0]
  token=env.get('TELEGRAM_BOT_TOKEN','')
  chat=env.get('TELEGRAM_CHAT_ID','')
  if len(token)<25 or ':' not in token or not chat.lstrip('-').isdigit():return None
  allowed=allowed_ids(env.get('TELEGRAM_ALLOWED_CHAT_IDS') or chat)
  if int(chat) not in allowed:return None
  return token,chat
 except (OSError,ValueError):return None
def check(*,get=None,path=PRIVATE):
 creds=read_credentials(path)
 if creds is None:return {'status':'CONFIG_INVALID','messages_sent':0}
 import requests
 get=get or requests.get
 token,chat=creds
 try:
  for name,params in [('getMe',None),('getChat',{'chat_id':chat})]:
   res=get('https://api.telegram.org/bot'+token+'/'+name,params=params,timeout=7)
   if res.status_code==401:return {'status':'BOT_TOKEN_UNAUTHORIZED','messages_sent':0}
   if res.status_code in (400,403):return {'status':'CHAT_NOT_ACCESSIBLE','messages_sent':0}
   if res.status_code!=200:return {'status':'TELEGRAM_API_UNAVAILABLE','messages_sent':0}
   body=res.json()
   if body.get('ok') is not True:return {'status':'TELEGRAM_API_REJECTED','messages_sent':0}
  return {'status':'AUTH_AND_CHAT_VALID','messages_sent':0}
 except (requests.RequestException,ValueError,TypeError,AttributeError):
  return {'status':'NETWORK_OR_RESPONSE_ERROR','messages_sent':0}
def main():
 p=argparse.ArgumentParser()
 p.add_argument('--check-auth',action='store_true')
 a=p.parse_args()
 if not a.check_auth:
  print(json.dumps({'status':'DISABLED','messages_sent':0}))
  return 0
 result=check()
 print(json.dumps(result))
 return 0 if result['status']=='AUTH_AND_CHAT_VALID' else 2
if __name__=='__main__':raise SystemExit(main())
