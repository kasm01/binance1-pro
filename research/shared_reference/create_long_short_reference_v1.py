"""Versioned user-labelled research dataset. Not a live trading policy."""
import json,hashlib
from datetime import datetime,timedelta,timezone
from pathlib import Path
TR=timezone(timedelta(hours=3))
# 11-15 November, user-supplied intervals. End exclusive to resolve boundaries.
LONG_WANTED={
'2026-11-11': [('12:40','15:00'),('15:36','17:00'),('18:25','18:35'),('19:06','19:30'),('22:40','23:00')],
'2026-11-12': [('02:20','02:55'),('03:10','03:45'),('04:51','05:12'),('12:15','13:25'),('17:22','17:42'),('18:33','19:10'),('21:20','22:18')],
'2026-11-13': [('00:06','00:33'),('01:18','02:10'),('02:39','03:06'),('03:42','04:27'),('08:00','10:20'),('11:24','11:42'),('12:57','13:06'),('13:33','14:45'),('15:15','15:36'),('16:03','16:42'),('18:36','18:51'),('19:15','19:26'),('20:21','20:45'),('21:18','22:42')],
'2026-11-14': [('01:18','01:36'),('02:15','03:06'),('05:30','05:50'),('07:36','09:18'),('10:21','10:33'),('11:36','12:57'),('14:33','15:48'),('16:06','16:45'),('20:21','20:38')],
'2026-11-15': [('00:18','00:40'),('01:38','01:43'),('02:12','02:25'),('02:40','03:15'),('05:02','05:12'),('06:42','06:48'),('07:10','07:15'),('08:06','08:22'),('09:15','09:28')]}
LONG_AVOID={
'2026-11-12': [('00:15','02:20'),('05:18','07:33'),('07:54','09:15'),('10:33','12:18'),('13:27','14:54'),('15:15','16:12'),('19:10','20:18')],
'2026-11-13': [('00:33','01:18'),('03:06','03:42'),('05:00','08:00'),('11:50','12:54'),('13:06','13:33'),('16:42','18:38'),('22:40','01:16')],
'2026-11-14': [('03:06','04:27'),('04:45','05:27'),('05:51','07:09'),('09:18','10:20'),('16:48','20:21'),('20:39','22:24'),('23:00','00:15')],
'2026-11-15': [('01:20','02:10'),('03:40','04:55'),('06:10','08:00'),('09:26','11:20'),('15:30','17:42')]}
def dt(day,clock):return datetime.fromisoformat(f'{day}T{clock}').replace(tzinfo=TR)
def convert(dic,label):
 result=[]
 for day,periods in dic.items():
  for st,en in periods:
   a=dt(day,st);b=dt(day,en)
   if b<=a:b+=timedelta(days=1)
   result.append(dict(start_tr=a.isoformat(),end_tr=b.isoformat(),user_label=label))
 return result
items=convert(LONG_WANTED,'LONG_WANTED')+convert(LONG_AVOID,'LONG_AVOID')
assert len(items)==70,(len(items),len(convert(LONG_WANTED,'LONG_WANTED')),len(convert(LONG_AVOID,'LONG_AVOID')))
timeline={}
for item in items:
 a=datetime.fromisoformat(item['start_tr']);b=datetime.fromisoformat(item['end_tr'])
 while a<b:
  slot=a.isoformat()
  timeline.setdefault(slot,set()).add(item['user_label'])
  a+=timedelta(minutes=1)
classified=[]
for t,labels in sorted(timeline.items()):
 # THESE ARE SUBJECTIVE RESEARCH LABELS, NOT A LIVE RULE.
 # In overlaps both sides are suppressed for this reference dataset.
 long_code='CONFLICT_NO_TRADE' if len(labels)>1 else ('LONG_TARGET' if 'LONG_WANTED' in labels else 'LONG_AVOID')
 short_code='CONFLICT_NO_TRADE' if len(labels)>1 else ('SHORT_AVOID' if 'LONG_WANTED' in labels else 'SHORT_RESEARCH_CANDIDATE')
 key=(long_code,short_code)
 if classified and classified[-1]['labels']==list(key) and datetime.fromisoformat(classified[-1]['end_tr'])==datetime.fromisoformat(t):
  classified[-1]['end_tr']=(datetime.fromisoformat(t)+timedelta(minutes=1)).isoformat()
 else:
  classified.append(dict(start_tr=t,end_tr=(datetime.fromisoformat(t)+timedelta(minutes=1)).isoformat(),labels=list(key)))
assert any(s['labels'][0]=='CONFLICT_NO_TRADE' for s in classified)
assert sum(1 for x in items if x['user_label']=='LONG_WANTED')==44
assert sum(1 for x in items if x['user_label']=='LONG_AVOID')==26
payload=dict(schema='binance1_long_short_user_window_reference_v1',
  market_symbol_note='Research labels for LONG1 NEARUSDT; SHORT1 may use INJUSDT or NEARUSDT, so opposite-direction transfer is a hypothesis, NOT market-specific ground truth.',
  timezone='Europe/Istanbul',date_min='2026-11-11',date_max='2026-11-15',
  interpretation='Half-open intervals [start,end), timezone UTC+3; spans midnight when end<=start; overlaps flagged CONFLICT_NO_TRADE. 14 Nov 23:00–15 Nov 00:15 is union of two user-reported negative windows (23:00 earlier,23:27 latest), not two duplicates.',
  provenance='user messages in project: Nov 11/12, Nov 13/14, Nov 15 long wanted and avoidance windows; earliest 14 Nov 23:00 supersedes nested latest 23:27 in union.',
  research_only=True,production_order_authority=False,not_training_target_for_live_by_clock=True,
  short_policy='LONG_WANTED -> SHORT_AVOID candidate label; LONG_AVOID -> SHORT_RESEARCH_CANDIDATE ONLY, requires independent SHORT1 evidence; conflicts -> NO_TRADE both; unlabelled -> UNLABELLED.',
  long_wanted_count=44,long_avoid_count=26,user_intervals=items,derived_disjoint_segments=classified)
dest=Path('research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json')
dest.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
manifest=Path('research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1_README.md')
manifest.write_text('''# binance1 common LONG/SHORT research labels v1
Canonical source: BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json.
Turkey time UTC+3, start inclusive/end exclusive; overnight intervals carry next date.
44 original LONG_WANTED and 26 original LONG_AVOID intervals.
Conflict labels: NO TRADE for BOTH sides. LONG_AVOID does NOT equal authorized SHORT. SHORT1 may use a different coin; test actual symbol independently. Unlabelled time is unlabelled, not bearish or bullish.
The windows are human-annotated historical market regimes, never literal scheduled production trading windows or hardcoded post-hoc signals.
Other files: selected market context and historical shadow logs; no production environment or service changes.
For separate holdout, compare only frozen model candidates as-of their source time and full risk chain; calculate net PnL with fees, slippage, mark price and lifecycle.
''')
print('SAVED',dest,'size',dest.stat().st_size,'sha256',hashlib.sha256(dest.read_bytes()).hexdigest())
print('WANTED',44,'AVOID',26,'DERIVED',len(classified),'CONFLICT_SEGMENTS',[(s['start_tr'],s['end_tr']) for s in classified if s['labels'][0]=='CONFLICT_NO_TRADE'])
