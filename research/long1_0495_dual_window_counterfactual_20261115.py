"""Read-only model score and shadow context alignment, no order authorization."""
from datetime import datetime,timedelta,timezone
from collections import Counter
import json,re,csv,os
import redis
TZ=timezone(timedelta(hours=3))
wanted=[
('00:18-00:40','2026-11-15T00:18','2026-11-15T00:40'),
('01:38-01:43','2026-11-15T01:38','2026-11-15T01:43'),
('02:12-02:25','2026-11-15T02:12','2026-11-15T02:25'),
('02:40-03:15','2026-11-15T02:40','2026-11-15T03:15'),
('05:02-05:12','2026-11-15T05:02','2026-11-15T05:12'),
('06:42-06:48','2026-11-15T06:42','2026-11-15T06:48'),
('07:10-07:15','2026-11-15T07:10','2026-11-15T07:15'),
('08:06-08:22','2026-11-15T08:06','2026-11-15T08:22'),
('09:15-09:28','2026-11-15T09:15','2026-11-15T09:28')]
avoid=[
('14Kas23-15Kas00:15','2026-11-14T23:00','2026-11-15T00:15'),
('01:20-02:10','2026-11-15T01:20','2026-11-15T02:10'),
('03:40-04:55','2026-11-15T03:40','2026-11-15T04:55'),
('06:10-08:00','2026-11-15T06:10','2026-11-15T08:00'),
('09:26-11:20','2026-11-15T09:26','2026-11-15T11:20'),
('15:30-17:42','2026-11-15T15:30','2026-11-15T17:42')]
def load_windows(items):
 return [(label,datetime.fromisoformat(a).replace(tzinfo=TZ),
   datetime.fromisoformat(b).replace(tzinfo=TZ)) for label,a,b in items]
wg=load_windows(wanted);ag=load_windows(avoid)
r=redis.Redis(decode_responses=True,socket_timeout=4)
shadow={}
lo=int(datetime(2026,11,14,19,tzinfo=timezone.utc).timestamp()*1000)
hi=int(datetime(2026,11,15,16,tzinfo=timezone.utc).timestamp()*1000)
for sid,data in r.xrange('telemetry:long1:context_adaptive_gate:v1',f'{lo}-0',f'{hi}-9999'):
 try:
  z=json.loads(data['json'])
  cid=int(z.get('close_id',-1))
  shadow[cid]=z
 except Exception:pass
scores={}
for path in ('logs/main.log.2','logs/main.log.1','logs/main.log'):
 if not os.path.isfile(path):continue
 for line in open(path,errors='replace'):
  if '[MODEL-SCORE]' not in line:continue
  mt=re.search(r'close_id=(\d+) p_used=([\d.]+) long_thr=([\d.]+) side=(\w+)',line)
  if not mt:continue
  try:dt=datetime.strptime(line[:19],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).astimezone(TZ)
  except:continue
  cid=int(mt[1]); scores[cid]=dict(close_id=cid,local_ts=dt.isoformat(),
       score=float(mt[2]),live_threshold=float(mt[3]),live_model_long=(mt[4]=='long'))
rows=[]
for cid,z in sorted(scores.items()):
 dt=datetime.fromisoformat(z['local_ts'])
 w=[name for name,a,b in wg if a<=dt<=b]
 a=[name for name,l,h in ag if l<=dt<=h]
 if not (w or a):continue
 sh=shadow.get(cid,{})
 value=dict(z,wanted=','.join(w),avoid=','.join(a),overlap=bool(w and a),
    pass_0495=z['score']>=.495,pass_0500=z['score']>=.500,
    pass_0502=z['score']>=.502,
    shadow_record_present=bool(sh),shadow_pass=sh.get('pass'),
    shadow_reason=sh.get('reason'),
    flow15=sh.get('t15_signed_ratio'),oi_direction=sh.get('oi_direction'),
    one_min_support=sh.get('live1m_long_direction_support'),
    all_shadow_checks=sh.get('checks'),
    candidate_0495_context=(z['score']>=.495 and sh.get('pass') is True),
    needs_avoid_override=bool(a))
 rows.append(value)
fpath='research/results/LONG1_0495_DUAL_WINDOWS_SCORE_SHADOW_20261115.json'
with open(fpath,'w') as f:json.dump(rows,f,ensure_ascii=False,indent=2)
for label,entries in [('WANTED',wg),('AVOID',ag)]:
 print('\n'+label)
 for name,st,en in entries:
  c=[x for x in rows if st<=datetime.fromisoformat(x['local_ts'])<=en]
  print(name,'bars',len(c),'live',sum(x['live_model_long'] for x in c),
    'p495',sum(x['pass_0495'] for x in c),
    'p495_shpass',sum(x['candidate_0495_context'] for x in c),
    'shadow_pass',sum(x['shadow_pass'] is True for x in c),
    'shadow_missing',sum(not x['shadow_record_present'] for x in c),
    'p495_shpass_times',','.join(datetime.fromisoformat(x['local_ts']).strftime('%H:%M') for x in c if x['candidate_0495_context']))
print('\nPARTITION')
for name,fn in [('wanted_exclusive',lambda x:bool(x['wanted']) and not x['avoid']),
  ('avoid_exclusive',lambda x:bool(x['avoid']) and not x['wanted']),
  ('overlap',lambda x:bool(x['wanted']) and bool(x['avoid']))]:
 c=[x for x in rows if fn(x)]
 print(name,'n',len(c),
       'p495',sum(x['pass_0495'] for x in c),
       'p495_and_shadow_pass',sum(x['candidate_0495_context'] for x in c),
       'live',sum(x['live_model_long'] for x in c))
print('\nOUTPUT',fpath)
