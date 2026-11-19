"""Only GET official Binance USD-M public daily ZIP archives.

UTC 10-15 Nov 2026 covers 11-15 Nov in Europe/Istanbul.
Strict response size caps, in-memory ZIP CRC check, official SHA256
checksum comparison when available, no extraction to disk. Data stored
under research/local_market_data (gitignored separately), never secret
or userTrades/private API. Read-only relative to production services.
"""
from __future__ import annotations
from datetime import date,timedelta
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
from hashlib import sha256
import json,requests,time,re
ROOT=Path(__file__).resolve().parents[2]
DEST=ROOT/'research/local_market_data/near_usdm_20261110_15'
DEST.mkdir(parents=True,exist_ok=True)
assert DEST.resolve().is_relative_to(ROOT.resolve())
s=requests.Session()
catalog=[]
for k in range(6):
    day=(date(2026,11,10)+timedelta(days=k)).isoformat()
    for kind in ('klines','aggTrades'):
        rel=(f'data/futures/um/daily/klines/NEARUSDT/1m/NEARUSDT-1m-{day}.zip'
             if kind=='klines' else
             f'data/futures/um/daily/aggTrades/NEARUSDT/NEARUSDT-aggTrades-{day}.zip')
        url='https://data.binance.vision/'+rel
        fn=DEST/Path(rel).name
        cap=2_000_000 if kind=='klines' else 15_000_000
        if fn.exists():
            blob=fn.read_bytes()
        else:
            resp=s.get(url,timeout=35,stream=True)
            resp.raise_for_status()
            chunks=[];n=0
            for part in resp.iter_content(chunk_size=1024*512):
                if not part:continue
                n+=len(part)
                if n>cap:raise RuntimeError('compressed size cap exceeded '+day+kind)
                chunks.append(part)
            blob=b''.join(chunks)
        assert 0<len(blob)<cap,(kind,day,len(blob))
        with ZipFile(BytesIO(blob)) as z:
            assert len(z.namelist())==1
            info=z.infolist()[0]
            assert not info.filename.startswith(('/','..'))
            assert info.file_size<(250_000_000 if kind=='aggTrades' else 3_000_000)
            with z.open(info) as f:
                # Streaming extraction to count rows, CRC verified on read.
                rows=0;first=b'';last=b''
                for line in f:
                    rows+=1
                    if rows==1:first=line[:180]
                    last=line[:180]
            assert rows>=1400 if kind=='klines' else rows>20000,(kind,day,rows)
        sha=sha256(blob).hexdigest()
        checksum_url=url+'.CHECKSUM'
        checksum_verified=False;checksum_note='not_checked'
        try:
            chk=s.get(checksum_url,timeout=10)
            if chk.status_code==200:
                m=re.match(r'^([a-f0-9]{64})\b',chk.text.strip(),re.I)
                if m:
                    if m.group(1).lower()!=sha:raise RuntimeError('Binance archive checksum mismatch '+str(fn))
                    checksum_verified=True;checksum_note='official_sha256_match'
                else:checksum_note='checksum_file_unexpected_format'
            else:checksum_note='checksum_unavailable_'+str(chk.status_code)
        except requests.RequestException as ex:
            checksum_note='checksum_fetch_error_'+type(ex).__name__
        if not fn.exists():fn.write_bytes(blob)
        catalog.append({'kind':kind,'day_utc':day,'file':fn.name,
          'compressed_bytes':len(blob),'sha256':sha,'records_including_header_if_present':rows,
          'first_row_prefix':first.decode('utf-8','replace')[:90],
          'last_row_prefix':last.decode('utf-8','replace')[:90],
          'official_checksum_verified':checksum_verified,'checksum_note':checksum_note})
        print(json.dumps({'date':day,'type':kind,'bytes':len(blob),
            'rows':rows,'checksum':checksum_note},sort_keys=True),flush=True)
manifest={'schema':'binance_usdm_nearusdt_public_daily_archive_20261110_15_v1',
 'source':'https://data.binance.vision/data/futures/um/daily/',
 'symbol':'NEARUSDT','market':'USD-M_Futures','date_basis':'UTC',
 'period':['2026-11-10','2026-11-15'],'data_types':['klines_1m','aggTrades'],
 'binance_api_key_needed':False,'real_order_calls':0,
 'production_redis_writes':0,'services_started':0,
 'files':catalog}
(DEST/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print('ARCHIVE_DONE',json.dumps({
 'file_count':len(catalog),
 'compressed_total_bytes':sum(x['compressed_bytes'] for x in catalog),
 'klines_rows':sum(x['records_including_header_if_present'] for x in catalog if x['kind']=='klines'),
 'aggtrade_rows':sum(x['records_including_header_if_present'] for x in catalog if x['kind']=='aggTrades'),
 'official_checksums_verified':sum(x['official_checksum_verified'] for x in catalog),
 'local_data_only':True},sort_keys=True))
