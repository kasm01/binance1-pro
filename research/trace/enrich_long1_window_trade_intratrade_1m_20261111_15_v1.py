"""Conservative public 1m OHLC excursions for verified Binance order pairs.

Only FULL one-minute bars strictly after entry minute and before exit minute
are considered. No assumption about within-minute high/low sequence or
execution ability. Excludes entry+exit minutes; may understate excursions.
No exchange private API, orders, portfolio metrics or strategy changes.
"""
from __future__ import annotations
import json,requests
from pathlib import Path
from datetime import datetime,timedelta
from decimal import Decimal

ROOT=Path(__file__).resolve().parents[2]
file=ROOT/'research/results/LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json'
a=json.loads(file.read_text())
assert len(a['trades'])==10 and a['exchange_filled_round_trips']==10
LIMITS=[.6,.95,1.2,1.65,2.0,2.5]
for item in a['trades']:
    entry=datetime.fromisoformat(item['open_tr'])
    close=datetime.fromisoformat(item['close_tr'])
    # First FULL bar start after the current (entry) minute.
    start=entry.replace(second=0,microsecond=0)+timedelta(minutes=1)
    # Last FULL bar ends by beginning of close minute.
    last_close_minute=close.replace(second=0,microsecond=0)
    if start>=last_close_minute:
        item['intratrade_public_1m']={
            'fully_enclosed_bars':0,'data_status':'NO_FULL_BARS',
            'gross_3x_max_favorable_roi_pct':None,
            'gross_3x_max_adverse_roi_pct':None,
            'arm_levels_touched':[]}
        continue
    startms=int(start.timestamp()*1000)
    endms=int(last_close_minute.timestamp()*1000)-1
    assert endms-startms<=1000*60000
    response=requests.get('https://fapi.binance.com/fapi/v1/klines',
        params={'symbol':'NEARUSDT','interval':'1m','startTime':startms,
                'endTime':endms,'limit':1000},timeout=12,allow_redirects=False)
    response.raise_for_status()
    rows=response.json()
    expected=(int(last_close_minute.timestamp()*1000)-startms)//60000
    assert isinstance(rows,list) and len(rows)==expected,(item['index'],len(rows),expected)
    assert all(int(row[0])==startms+60000*i for i,row in enumerate(rows))
    high=max(Decimal(str(row[2])) for row in rows)
    low=min(Decimal(str(row[3])) for row in rows)
    entryprice=Decimal(str(item['entry_price']))
    leverage=Decimal(str(item['leverage']))
    mfe=(high/entryprice-1)*leverage*100
    mae=(low/entryprice-1)*leverage*100
    levels=[n for n in LIMITS if mfe>=Decimal(str(n))]
    item['intratrade_public_1m']={
        'fully_enclosed_bars':len(rows),
        'data_status':'FULL_MINUTE_OHLC_ONLY_NO_TICK_SEQUENCE',
        'gross_3x_max_favorable_roi_pct':round(float(mfe),3),
        'gross_3x_max_adverse_roi_pct':round(float(mae),3),
        'arm_levels_touched':levels,
        'arm_levels_not_proven_executable':True,
        'entry_and_exit_minute_excluded':True,
    }
a['intratrade_ohlc_research_only']=True
a['arm_level_touch_does_not_prove_net_lock_profit']=True
a['intratrade_ohlc_source']='Binance Futures public 1m fully enclosed bars'
a['intratrade_model_cannot_resolve_high_low_order']=True
file.write_text(json.dumps(a,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','analysed':len(a['trades']),
 'losers':[{ 'time':x['open_tr'],'mfe_roi_pct':x['intratrade_public_1m']['gross_3x_max_favorable_roi_pct'],
              'mae_roi_pct':x['intratrade_public_1m']['gross_3x_max_adverse_roi_pct'],
              'arm_levels_touched':x['intratrade_public_1m']['arm_levels_touched']}
           for x in a['trades'] if x['realized_price_pnl_usdt']<0],
 'total_arm_touch_by_level':{str(t):sum(t in x['intratrade_public_1m']['arm_levels_touched']
                             for x in a['trades']) for t in LIMITS},
 'no_orders':True,'no_production_redis_writes':True},sort_keys=True))
