"""Build 1m historical trade-flow from official authenticated-checksum ZIPs.

All trade rows are public futures aggTrades, not live order book, whale
identity, funding or account records. By convention is_buyer_maker=true
means sell taker; false means buy taker. Signal use must include only
fully closed minutes (no future lookahead). Data stays local, uncommitted.
"""
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from zipfile import ZipFile
from io import TextIOWrapper
from pathlib import Path
import json,csv,gzip,math
ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/'research/local_market_data/near_usdm_20261110_15'
M=json.loads((DIR/'manifest.json').read_text())
assert len(M['files'])==12 and all(z['official_checksum_verified'] for z in M['files'])
daykeys=sorted({z['day_utc'] for z in M['files']})
assert len(daykeys)==6
out=[];issues=[]
for day in daykeys:
    kline=DIR/f'NEARUSDT-1m-{day}.zip'
    agg=DIR/f'NEARUSDT-aggTrades-{day}.zip'
    with ZipFile(kline) as archive:
        with archive.open(archive.namelist()[0]) as z:
            candles=list(csv.DictReader(TextIOWrapper(z,encoding='utf-8')))
    assert len(candles)==1440,(day,len(candles))
    stats=defaultdict(lambda:[0.,0.,0.,0])
    count=0
    with ZipFile(agg) as archive:
        with archive.open(archive.namelist()[0]) as z:
            for row in csv.DictReader(TextIOWrapper(z,encoding='utf-8')):
                t=int(row['transact_time'])
                bucket=t//60000*60000
                quote=float(row['price'])*float(row['quantity'])
                assert math.isfinite(quote) and quote>0
                value=stats[bucket]
                if row['is_buyer_maker'].lower()=='true':
                    value[1]+=quote
                elif row['is_buyer_maker'].lower()=='false':
                    value[0]+=quote
                else:raise AssertionError('unknown maker flag')
                value[2]+=quote;value[3]+=1
                count+=1
    prev=-1
    for c in candles:
        ts=int(c['open_time'])
        assert ts==prev+60000 if prev>=0 else ts%60000==0
        prev=ts
        a=stats.pop(ts,[0.,0.,0.,0])
        quote=float(c['quote_volume'])
        taker=float(c['taker_buy_quote_volume'])
        flow=(a[0]-a[1])/a[2] if a[2]>0 else None
        # Kline taker-buy/sell quote is canonical on exact 1m bins,
        # whereas aggregated trade timestamp may shift across boundaries.
        kline_flow=(2*taker-quote)/quote if quote>0 else None
        # Binance aggTrades are consolidated grouped executions; compare
        # taker-direction *quote*, allowing small rounding on price and qty.
        delta=a[2]-quote
        buy_delta=a[0]-taker
        alignment_ok=(abs(delta)<=max(1.0,quote*.002)
                      and abs(buy_delta)<=max(1.0,quote*.002))
        if not alignment_ok:
            issues.append({'minute_utc':datetime.fromtimestamp(ts/1000,timezone.utc).isoformat(),
               'agg_quote_delta':round(delta,3),
               'agg_buy_quote_delta':round(buy_delta,3)})
        out.append({'open_time_ms':ts,'open':c['open'],'high':c['high'],
           'low':c['low'],'close':c['close'],'quote_volume':c['quote_volume'],
           'taker_buy_quote_volume':c['taker_buy_quote_volume'],
           'agg_buy_taker_quote':f'{a[0]:.4f}',
           'agg_sell_taker_quote':f'{a[1]:.4f}',
           'agg_trade_count':int(a[3]),
           'agg_signed_imbalance':f'{flow:.8f}' if flow is not None else '',
           'agg_vs_kline_minute_aligned':int(alignment_ok),
           'canonical_kline_taker_imbalance':
                f'{kline_flow:.8f}' if kline_flow is not None else '',
           'fully_closed_1m_required':1})
    assert not stats,(day,len(stats))
    print('DAY_VALIDATED',day,'trades',count,'minutes',len(candles),flush=True)
assert len(out)==8640
# Compare historical records, but never claim signed flow is full whale state
end=DIR/'near_1m_asof_signed_aggtrade_flow_20261110_15.csv.gz'
with gzip.open(end,'wt',newline='',encoding='utf-8',compresslevel=6) as f:
    w=csv.DictWriter(f,fieldnames=list(out[0]),lineterminator='\n')
    w.writeheader();w.writerows(out)
summary={
 'schema':'near_usdm_1m_aggtrade_archive_rebuild_v1',
 'source_manifest':'manifest.json','market':'USD-M_NEARUSDT',
 'utc_days':daykeys,'one_minute_bars':len(out),
 'agg_trades':sum(x['records_including_header_if_present']-1 for x in M['files'] if x['kind']=='aggTrades'),
 'flow_definition':'canonical 1m: (2 * kline_taker_buy_quote_volume - kline_quote_volume)/kline_quote_volume',
 'agg_trade_imbalance_is_diagnostic_when_misaligned':True,
 'num_canonical_kline_flow_minutes':sum(bool(x['canonical_kline_taker_imbalance']) for x in out),
 'num_agg_minute_alignment_ok':sum(x['agg_vs_kline_minute_aligned'] for x in out),
 'is_buyer_maker_true':'sell_market_taker',
 'flow_is_whale_ownership_or_depth':False,
 'asof_replay_must_use_closed_minutes_only':True,
 'num_large_quote_mismatch_minutes':len(issues),
 'first_mismatch_examples':issues[:4],
 'output_file':end.name,'output_compressed_bytes':end.stat().st_size,
 'production_redis_writes':0,'private_api_calls':0,'orders_sent':0}
(DIR/'derived_manifest.json').write_text(json.dumps(summary,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print('RESULT',json.dumps(summary,sort_keys=True))
