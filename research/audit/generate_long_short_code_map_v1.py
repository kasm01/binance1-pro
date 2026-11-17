#!/usr/bin/env python3
"""Read-only static inventory. Excludes credentials and source backups."""
import ast,csv,subprocess
from pathlib import Path
ROOTS={'LONG1':Path('/home/kasm920/binance1-pro'),'SHORT1':Path('/home/kasm920/binance1')}
FOCUS=['main.py','core/trade_executor.py','core/trade_executor_short.py','core/risk_manager.py',
       'core/long_contra_guard.py','core/short_native_algo_stop.py','core/binance_futures_v3.py',
       'core/short_entry_candle_service.py','orchestration/executor/master_executor.py',
       'orchestration/executor/intent_bridge.py','orchestration/risk/central_risk_master.py',
       'orchestration/risk/central_risk_client.py','orchestration/risk/risk_master.py',
       'scripts/long1_native_stop_guard.py','scripts/long1_native_stop_reconciler.py']
SAFE_KEYS={'DRY_RUN','ARMED','KILL_SWITCH','SYMBOL','SYMBOLS','STRATEGY_ID','REDIS_PREFIX','SIGNALS_STREAM',
'TOP5_STREAM','CANDIDATES_STREAM','TRADE_INTENTS_STREAM','EXEC_EVENTS_STREAM','MASTER_IN_STREAM',
'MAX_LEVERAGE','DEFAULT_ORDER_LEVERAGE','SHORT_SHADOW_LEVERAGE','SL_PCT','ROI_HARD_STOP_PCT',
'FIXED_ROI_TP_ENABLE','FIXED_ROI_TP_PCT','FIXED_ROI_TP_GIVEBACK','STALL_EXIT_ENABLE',
'LONG_CONTRA_GUARD_ENABLE','LONG1_NATIVE_STOP_AUTO_ENABLE','SHORT_NATIVE_STOP_ENABLE',
'SHORT_NATIVE_STOP_WORKING_TYPE','SHORT_NATIVE_STOP_PRICE_PROTECT','SHORT_DYNAMIC_STOP_ENABLE',
'SHORT_DYNAMIC_STOP_CONFIRM_SEC','SHORT_DYNAMIC_STOP_CATASTROPHIC_PCT',
'SNIPER_ENTRY_MIN_CANDLE_PROGRESS','SNIPER_ENTRY_MAX_CANDLE_PROGRESS',
'ENTRY_CONFIRM_MIN_QUALITY','SHORT_ENTRY_CONFIRM_MIN_QUALITY',
'SHORT_SIZING_MODE','SHORT_PENDING_MAX_CANDLE_AGE',
'LONG_SCALE_IN_ENABLE','SHORT1_V50_CONTEXT_RISK_ENABLE','SHORT1_V50_CONTEXT_RISK_MULTIPLIER',
'CENTRAL_RISK_ENFORCE_DRY_RUN','SHORT_ESTIMATED_ROUND_TRIP_FEE_PCT',
'SHORT_NORMAL_POSITION_EQUITY_PCT','SHORT_REDUCED_POSITION_EQUITY_PCT',
'SHORT_DD_REDUCE_TRIGGER_PCT','SHORT_DD_RECOVER_TRIGGER_PCT'}
B=chr(96)
for side,root in ROOTS.items():
 out=root/'research/results';out.mkdir(parents=True,exist_ok=True)
 files=[]
 for pth in ('main.py','core','orchestration','scripts'):
  p=root/pth
  if p.is_file():files.append(p)
  if p.is_dir():files.extend(x for x in p.rglob('*.py') if '__pycache__' not in x.parts)
 symbols=[]
 for p in sorted(set(files)):
  rel=p.relative_to(root).as_posix()
  try:tree=ast.parse(p.read_text(errors='replace'))
  except (SyntaxError,UnicodeError):continue
  class Walk(ast.NodeVisitor):
   def __init__(self):self.stack=[]
   def visit_ClassDef(self,node):
    symbols.append((rel,node.lineno,node.end_lineno or node.lineno,'class','.'.join(self.stack+[node.name])))
    self.stack.append(node.name);self.generic_visit(node);self.stack.pop()
   def visit_FunctionDef(self,node):
    symbols.append((rel,node.lineno,node.end_lineno or node.lineno,'def','.'.join(self.stack+[node.name])))
    self.stack.append(node.name);self.generic_visit(node);self.stack.pop()
   visit_AsyncFunctionDef=visit_FunctionDef
  Walk().visit(tree)
 index=out/f'{side}_ALL_PYTHON_SYMBOL_INDEX_20261113.csv'
 with index.open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['relative_file','line_start','line_end','kind','qualified_name']);w.writerows(symbols)
 grouped={}
 for rel,line,end,kind,name in symbols:
  if rel in FOCUS:grouped.setdefault(rel,[]).append((line,end,kind,name))
 safe=[]
 for l in (root/'.env').read_text(errors='replace').splitlines():
  x=l.strip()
  if not x or x.startswith('#') or '=' not in x:continue
  k,v=x.split('=',1)
  if k in SAFE_KEYS:safe.append((k,v))
 try:
  services=subprocess.check_output(['systemctl','--user','list-units','--type=service','--all','--no-pager'],text=True,timeout=10).splitlines()
 except:services=[]
 relevant=[l.strip() for l in services if 'binance1-' in l and
           (any(k in l for k in ('long','central','oi-context')) if side=='LONG1' else
            any(k in l for k in ('short','central','oi-context')))]
 lines=[
 f'# {side} — tüm Python fonksiyonları, kaynak konumları ve operasyon komutları',
 f'Kaynak dizin: {root}; tarih: 13 Kasım 2026.',
 '',
 '## Kapsam',
 'Bu otomatik statik envanter ana Python kaynaklarını, fonksiyon satır aralıklarını, servisleri ve gizli olmayan parametreleri listeler.',
 'Eski .bak dosyaları güncel çalışma kodu sayılmaz.',
 f'- Toplam taranan Python dosyası: {len(set(files))}',
 f'- Fonksiyon/sınıf sayısı: {len(symbols)}',
 f'- Tam fonksiyon ve sınıf dizini: {index}',
 '',
 '## İlgili systemd servisleri',
 B*3+'text',*(relevant or ['yok']),B*3,'',
 '## .env: güvenli parametreler',
 B*3+'ini',*[f'{k}={v}' for k,v in safe],B*3,'',
 '## Ana kaynaklar: eksiksiz fonksiyon/satır indeksi',
 ]
 for rel in FOCUS:
  p=root/rel
  if not p.is_file():continue
  lines+=['',f'### {rel} ({len(p.read_text(errors="replace").splitlines())} satır)']
  for start,end,kind,name in grouped.get(rel,[]):
   lines.append(f'- L{start}–L{end}: {B}{name}{B} ({kind})')
 lines+=['','## Kullanılabilir güvenli kontrol komutları',B*3+'bash']
 if side=='LONG1':
  lines+=['cd ~/binance1-pro',
  'systemctl --user status binance1-long-supervisor.service --no-pager',
  'systemctl --user status binance1-long-orch.service --no-pager',
  'systemctl --user status binance1-long1-native-stop.service --no-pager',
  'systemctl --user status binance1-long1-decision-shadow.service --no-pager',
  './venv/bin/python scripts/long1_native_stop_guard.py',
  './venv/bin/python scripts/long1_native_stop_reconciler.py',
  'journalctl --user -u binance1-long1-native-stop.service -n 50 --no-pager',
  'git status --short']
 else:
  lines+=['cd ~/binance1',
  "grep -E '^(DRY_RUN|ARMED|SYMBOL|SHORT_NATIVE_STOP_ENABLE)=' .env",
  'PYTHONPATH=. ./venv/bin/python research/tests/test_short_native_algo_stop_v1.py',
  './venv/bin/python -m py_compile core/trade_executor_short.py core/short_native_algo_stop.py',
  'systemctl --user list-units --all --type=service | grep -i short',
  'systemctl --user list-timers --all | grep -i short',
  'git status --short']
 lines+=[B*3,'','Canlı emir yetkisini değiştiren komutlar bu raporda otomatik uygulanmaz.']
 report=out/f'{side}_FULL_SOURCE_COMMAND_MAP_20261113.md'
 report.write_text('\n'.join(lines)+'\n')
 print(side,'report',report,'bytes',report.stat().st_size,'symbols',len(symbols),'files',len(set(files)))
