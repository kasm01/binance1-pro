"""Official Binance daily 1m public ZIP, checksum + CRC. No other API."""
from pathlib import Path
from io import BytesIO,TextIOWrapper
from zipfile import ZipFile
from hashlib import sha256
import requests,csv,json,re
R=Path(__file__).resolve().parents[2]
p=R/'research/local_market_data/near_usdm_20261110_16_holdout'
p.mkdir(parents=True,exist_ok=True)
fn='NEARUSDT-1m-2026-11-16.zip'
url='https://data.binance.vision/data/futures/um/daily/klines/NEARUSDT/1m/'+fn
blob=requests.get(url,timeout=15).content
assert 10000<len(blob)<2000000
r=requests.get(url+'.CHECKSUM',timeout=12);r.raise_for_status()
expect=re.match(r'^([a-f0-9]{64})\b',r.text.strip(),re.I)
assert expect and sha256(blob).hexdigest().lower()==expect.group(1).lower()
with ZipFile(BytesIO(blob)) as z:
 assert len(z.namelist())==1
 with z.open(z.namelist()[0]) as f:
  rows=list(csv.DictReader(TextIOWrapper(f,encoding='utf8')))
 assert len(rows)==1440
 assert rows[0]['open_time'].isdigit()
(p/fn).write_bytes(blob)
(p/'manifest.json').write_text(json.dumps({
 'date_utc':'2026-11-16','kind':'USD-M_NEARUSDT_1m',
 'file':fn,'official_sha256_verified':True,
 'sha256':sha256(blob).hexdigest(),'minute_bars':len(rows),
 'public_api_only':True,'production_redis_writes':0,'order_calls':0
},indent=2)+'\n')
print(json.dumps({'status':'PASS','day':'2026-11-16',
 'bars':len(rows),'bytes':len(blob),'official_sha256':True,
 'orders':0},sort_keys=True))
