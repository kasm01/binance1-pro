"""Optional PTB22 read-only commands. Never wired into live executor.

Default OFF, requires explicit --run plus TELEGRAM_READONLY_COMMANDS_ENABLED=1.
No keys to Binance, no trade actions and fail-closed chat/user allowlists.
"""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
from telegram.ext import Application,CommandHandler
ROOT=Path(__file__).resolve().parents[1]
STATUS=ROOT/'run/signal_center/status.json'
HELP=("/help — kullanılabilir komutlar\n"
 "/ping — servis yanıtı\n/status — sinyal tarayıcı özeti\n"
 "/universe — 40 coin havuzu\n/bots — 8 strateji durumu\n"
 "/signals — son araştırma sinyalleri\n"
 "/risk — manuel-only güvenlik durumu\n"
 "/trades ve /positions — gerçek işlem olmadığını bildirir\n"
 "/whoami — sohbet kimliği\n"
 "Bu komutlar hiçbir şekilde Binance emri üretmez.")
def allowed_ids(raw):
 out=set()
 for x in str(raw or '').split(','):
  try:out.add(int(x.strip()))
  except ValueError:pass
 return out
def authorized(chat_id,user_id,*,chats=None,users=None):
 ch=allowed_ids(os.getenv('TELEGRAM_ALLOWED_CHAT_IDS') or os.getenv('TELEGRAM_CHAT_ID')) if chats is None else chats
 us=allowed_ids(os.getenv('TELEGRAM_ALLOWED_USER_IDS')) if users is None else users
 # Chat allowlist mandatory. User allowlist optional extra protection.
 return bool(ch and chat_id in ch and (not us or user_id in us))
def snapshot(path=STATUS):
 try:
  # Prevent implicit arbitrary path injection. No live trade state mutation.
  if not path.is_file() or path.stat().st_size>200_000:return None
  obj=json.loads(path.read_text(encoding='utf-8'))
  if obj.get('schema')!='manual_signal_center_status.v1':return None
  if obj.get('manual_only') is not True:return None
  return obj
 except (OSError,ValueError,AttributeError):return None
def answer(command, snap=None):
 x=snap if isinstance(snap,dict) else None
 if command in ('start','help'):return HELP
 if command=='ping':return 'pong — manuel sinyal bildirim servisi'
 if command in ('trades','positions'):
  return 'Bu Telegram sinyal merkezi manuel-only çalışır. Otomatik işlem veya gerçek pozisyon kaydı üretmez.'
 if command=='risk':
  return 'Risk durumu: otomatik emir KAPALI; manuel karar gerekli; bu komut emir yetkisi vermez.'
 if x is None:return 'Veri henüz yok. Sinyal tarayıcı servisi kapalı veya status snapshot üretilmedi.'
 if command=='status':
  return (f"📊 MANUEL SİNYAL MERKEZİ\n"
    f"Son güncelleme ms: {x.get('updated_at_ms','?')}\n"
    f"Takip edilen coin: {len(x.get('selected_symbols',[]))}\n"
    "Otomatik emir: KAPALI")
 if command=='universe':
  return 'İzlenen coinler: '+', '.join(x.get('selected_symbols',[])[:40])
 if command=='bots':
  return '\n'.join(f"{bot}: {len(items)} coin" for bot,items in
    sorted(x.get('bot_allocations',{}).items()))
 if command in ('signals','signal'):
  data=x.get('last_signals',[])
  if not data:return 'Yeni sinyal yok.'
  return '\n'.join(
   f"{v.get('strategy','?')} {v.get('symbol','?')} "
   f"{v.get('status',v.get('state','?'))} / "
   f"{v.get('research_context_state','CONTEXT_NOT_CHECKED')}"
   for v in data[-10:] if isinstance(v,dict))
 return HELP
async def handle(update,context):
 chat=getattr(update,'effective_chat',None)
 user=getattr(update,'effective_user',None)
 msg=getattr(update,'effective_message',None)
 if msg is None:return
 if not authorized(getattr(chat,'id',None),getattr(user,'id',None)):
  await msg.reply_text('⛔ Yetkisiz Telegram sohbeti veya kullanıcı.')
  return
 command=getattr(msg,'text','').split(' ')[0].split('@')[0].lstrip('/').lower()
 if command=='whoami':
  await msg.reply_text(f"Chat ID: {getattr(chat,'id','?')}\nUser ID: {getattr(user,'id','?')}")
 else:
  await msg.reply_text(answer(command,snapshot())[:3500])
def make_application(token):
 app=Application.builder().token(token).build()
 for name in ('start','help','ping','status','universe','bots','signals','signal',
              'risk','positions','trades','whoami'):
  app.add_handler(CommandHandler(name,handle))
 return app
def main():
 p=argparse.ArgumentParser()
 p.add_argument('--run',action='store_true')
 a=p.parse_args()
 if not a.run or os.getenv('TELEGRAM_READONLY_COMMANDS_ENABLED','0')!='1':
  print('DISABLED: explicit --run and TELEGRAM_READONLY_COMMANDS_ENABLED=1 required')
  return 0
 if not allowed_ids(os.getenv('TELEGRAM_ALLOWED_CHAT_IDS') or os.getenv('TELEGRAM_CHAT_ID')):
  print('DENIED: no valid authorized chat IDs');return 2
 token=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
 if not token:print('DENIED: token not configured');return 2
 make_application(token).run_polling(drop_pending_updates=True,allowed_updates=['message'])
 return 0
if __name__=='__main__':raise SystemExit(main())
