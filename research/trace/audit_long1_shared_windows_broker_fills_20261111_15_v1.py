"""LONG1 11-15 Nov, exact-source audit with signed Binance Futures GET only.

ZERO exchange writes, service starts, production Redis writes, or threshold
changes. Historical user windows are retrospective annotations, not a live
time-of-day trading gate. Amounts in public output are aggregated and omit
order/intent IDs. Costs converted from BNB using *hourly futures BNBUSDT
close* are indicative, not exchange-provided USDT-valued commission.
"""
from __future__ import annotations
import json,os,re,requests
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import redis
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[2]
TZ=ZoneInfo("Europe/Istanbul")
START=datetime(2026,11,11,tzinfo=TZ)
END=datetime(2026,11,16,tzinfo=TZ)
load_dotenv(ROOT/".env")
from core.binance_futures_v3 import signed_get

def iso(ms):
    return datetime.fromtimestamp(int(ms)/1000,TZ)
def d(x):
    return Decimal(str(x))
def money(v, places=6):
    return round(float(v),places)

reference=json.loads((ROOT/'research/shared_reference/BINANCE1_LONG_SHORT_WINDOWS_20261111_15_V1.json').read_text())
assert reference['research_only'] and not reference['production_order_authority']
intervals=[(datetime.fromisoformat(q['start_tr']),datetime.fromisoformat(q['end_tr']),q['user_label'])
           for q in reference['user_intervals']]
assert len(intervals)==70
def label(dt):
    names={name for lo,hi,name in intervals if lo<=dt<hi}
    if {'LONG_WANTED','LONG_AVOID'}.issubset(names):return 'CONFLICT_NO_TRADE'
    if 'LONG_WANTED' in names:return 'LONG_TARGET'
    if 'LONG_AVOID' in names:return 'LONG_AVOID'
    return 'UNLABELLED'
def active(dt,desired):
    return [i for i,(lo,hi,name) in enumerate(intervals)
            if name==desired and lo<=dt<hi]
def safe_stream(r,key):
    result={}
    for sid,v in r.xrange(key):
        try:
            obj=json.loads(v.get('json') or '{}')
            if isinstance(obj,dict):result[sid]=obj
        except (ValueError,TypeError):continue
    return result

def main():
    r=redis.Redis(host="127.0.0.1",port=6379,decode_responses=True,
                  socket_connect_timeout=2,socket_timeout=6)
    candidates=safe_stream(r,'candidates_stream_long1')
    top5=safe_stream(r,'top5_stream_long1')
    batches=safe_stream(r,'trade_intents_stream_long1')
    executions=safe_stream(r,'exec_events_stream_long1')
    opens=safe_stream(r,'shadow:telemetry:position_open')
    outcomes=safe_stream(r,'shadow:telemetry:position_outcome')
    intent_by_id={};intent_batch_id={}
    for sid,b in batches.items():
        for it in b.get('items') or []:
            if not isinstance(it,dict) or it.get('symbol')!='NEARUSDT':continue
            dt=datetime.fromisoformat(str(it.get('ts_utc') or b['ts_utc']).replace('Z','+00:00')).astimezone(TZ)
            if not START<=dt<END:continue
            iid=it.get('intent_id')
            assert isinstance(iid,str) and iid and iid not in intent_by_id
            intent_by_id[iid]=(dt,it)
            intent_batch_id[iid]=sid
    assert len(intent_by_id)==112,len(intent_by_id)
    intent_labels=Counter(label(dt) for dt,_ in intent_by_id.values())
    # Verify literal candidate->top5->intent->exec pairs before assigning
    # signal to stage. Different streams CAN share numeric XADD IDs.
    exec_pairs=set()
    for b in executions.values():
        for it in b.get('items') or []:
            if isinstance(it,dict) and it.get('symbol')=='NEARUSDT':
                exec_pairs.add((b.get('source_intents_id'),it.get('intent_id')))
    for iid,(dt,it) in intent_by_id.items():
        raw=it.get('raw') or {}
        assert isinstance(raw,dict)
        cid=raw.get('candidate_id');cstreamid=raw.get('_source_stream_id')
        c=candidates.get(cstreamid)
        assert c and c.get('candidate_id')==cid
        batch=batches[intent_batch_id[iid]]
        t=top5.get(batch.get('source_top5_id'))
        assert t is not None
        selected=[z for z in t.get('items') or [] if z.get('candidate_id')==cid and
                  z.get('_source_stream_id')==cstreamid]
        assert len(selected)==1
        assert (intent_batch_id[iid],iid) in exec_pairs

    # Parse only source log dispatch blocks, assign ENTRY-DECISION reason to
    # its observed EXEC-EVENTS recv intent. Not an order fill proof by itself.
    logpaths=[ROOT/'logs'/('main.log'+suffix) for suffix in ('.5','.4','.3','.2','.1','')]
    dispatch={};current=None
    dates={f'2026-11-{n:02}' for n in range(11,16)}
    for file in logpaths:
        if not file.is_file():continue
        with file.open(errors='replace') as fh:
            for line in fh:
                if line[:10] not in dates:continue
                msg=line.split(' | ',3)[-1]
                m=re.search(r'\[EXEC-EVENTS\] recv intent=([0-9a-f-]+) side=long symbol=NEARUSDT',msg)
                if m:
                    current=m.group(1)
                    assert current not in dispatch
                    dispatch[current]={'entry':None,'pending_recheck':None,
                                       'risk':None,'contra':None,'finished':False}
                    continue
                if current is None:continue
                entry=dispatch[current]
                if '[EXEC][ENTRY-DECISION]' in msg:
                    mm=re.search(r'action=(\w+) reason=([\w-]+)',msg)
                    if mm:entry['entry']=(mm.group(1),mm.group(2))
                elif '[EXEC][PENDING-RECHECK]' in msg:
                    mm=re.search(r'status=(\w+)',msg)
                    if mm:entry['pending_recheck']=mm.group(1)
                elif '[EXEC][NOTIONAL][REJECT]' in msg:
                    mm=re.search(r'reason=([\w-]+)',msg)
                    entry['risk']=mm.group(1) if mm else 'notional_reject'
                elif '[EXEC][CONTRA-GUARD]' in msg:
                    mm=re.search(r'action=(\w+)',msg)
                    entry['contra']=mm.group(1) if mm else 'unknown'
                if '[EXEC-EVENTS] decision dispatched' in msg and f'intent={current}' in msg:
                    entry['finished']=True
                    current=None
    assert len(dispatch)==112 and set(dispatch)==set(intent_by_id)
    assert all(x['finished'] for x in dispatch.values())

    model=json.loads((ROOT/'research/results/LONG1_MARKET_CONTEXT_V2_103_ASOF_20261111_15.json').read_text())['full_results']
    assert len(model)==103
    model_labels=Counter()
    model_dates=defaultdict(Counter)
    for x in model:
        dt=datetime.fromisoformat(x['ts_tr']).astimezone(TZ)
        assert START<=dt<END
        category=label(dt)
        assert category==x['reference_label'],(dt,category,x['reference_label'])
        model_labels[category]+=1
        model_dates[dt.date().isoformat()][category]+=1

    utc_start=int(START.timestamp()*1000)
    utc_end=int(END.timestamp()*1000)-1
    param={'symbol':'NEARUSDT','startTime':utc_start,'endTime':utc_end,'limit':1000}
    trades=signed_get('/fapi/v1/userTrades',param,timeout=12)
    orders=signed_get('/fapi/v1/allOrders',param,timeout=12)
    income=signed_get('/fapi/v1/income',param,timeout=12)
    assert all(isinstance(rows,list) and len(rows)<1000 for rows in (trades,orders,income))
    assert all(x.get('symbol')=='NEARUSDT' and
               x.get('positionSide')=='LONG' for x in trades)
    assert len(trades)==27 and len(orders)==20,len(trades)
    order_fills=defaultdict(list)
    for row in trades:
        assert START<=iso(row['time'])<END
        order_fills[str(row['orderId'])].append(row)
    orders_by_id={str(v['orderId']):v for v in orders}
    assert len(order_fills)==len(orders_by_id)==20 and set(order_fills)==set(orders_by_id)
    assert all(o['status']=='FILLED' and o['type']=='MARKET' for o in orders)
    ordered=sorted(order_fills,key=lambda oid:min(int(x['time']) for x in order_fills[oid]))
    all_pairs=[];current=None
    for oid in ordered:
        rows=order_fills[oid]
        side=rows[0]['side']
        assert all(x['side']==side for x in rows)
        total_qty=sum((d(x['qty']) for x in rows),Decimal(0))
        px=(sum((d(x['price'])*d(x['qty']) for x in rows),Decimal(0))/total_qty)
        t=min(int(x['time']) for x in rows)
        payload={'oid':oid,'side':side,'qty':total_qty,'price':px,'time_ms':t,
                 'rows':rows}
        if side=='BUY':
            assert current is None,('overlapping_positions_not_supported',t)
            current=payload
        elif side=='SELL':
            assert current is not None
            assert total_qty==current['qty']
            all_pairs.append((current,payload))
            current=None
        else:raise AssertionError('unexpected_side')
    assert current is None and len(all_pairs)==10

    # Match by exact exchange open orderId and intent_id, NOT timestamp.
    open_by_order={}
    for row in opens.values():
        if row.get('symbol')!='NEARUSDT':continue
        ms=row.get('position_open_at_ms')
        if ms is None or not START<=iso(ms)<END:continue
        key=str(row.get('open_order_id') or '')
        assert key and key not in open_by_order
        open_by_order[key]=row
    outcome_by_order={}
    for row in outcomes.values():
        if row.get('symbol')!='NEARUSDT':continue
        ms=row.get('position_open_at_ms')
        if ms is None or not START<=iso(ms)<END:continue
        key=str(row.get('open_order_id') or '')
        assert key and key not in outcome_by_order
        outcome_by_order[key]=row
    assert len(open_by_order)==10 and len(outcome_by_order)==9
    assert set(open_by_order)=={a['oid'] for a,b in all_pairs}

    # Indicative BNBUSDT 1h futures close for BNB fee equivalent, public GET.
    klines=requests.get('https://fapi.binance.com/fapi/v1/klines',
        params={'symbol':'BNBUSDT','interval':'1h','startTime':utc_start,
                'endTime':utc_end,'limit':150},
        timeout=10,allow_redirects=False)
    klines.raise_for_status()
    candles=klines.json()
    assert isinstance(candles,list) and len(candles)>=120
    hourly_bnbrate={int(k[0]):d(k[4]) for k in candles}
    def bnbrate(t):
        hour=(int(t)//3600000)*3600000
        assert hour in hourly_bnbrate,('hour_price_missing',hour)
        return hourly_bnbrate[hour]
    assert all(x.get('commissionAsset')=='BNB' for x in trades)
    income_sum=defaultdict(lambda:Decimal(0))
    for row in income:
        assert START<=iso(row['time'])<END
        income_sum[(row['incomeType'],row['asset'])]+=d(row['income'])
    gross=sum((d(z['realizedPnl']) for z in trades),Decimal(0))
    sum_income_realized=income_sum[('REALIZED_PNL','USDT')]
    assert gross==sum_income_realized
    commission_bnb=sum((d(z['commission']) for z in trades),Decimal(0))
    assert commission_bnb == -income_sum[('COMMISSION','BNB')]
    funding_all=income_sum[('FUNDING_FEE','USDT')]
    assert all(x[0] in ('COMMISSION','REALIZED_PNL','FUNDING_FEE') for x in income_sum)

    per_trade=[]
    trade_open_ids=set()
    reasons=Counter()
    reasons_by_label=defaultdict(Counter)
    intent_by_label=defaultdict(Counter)
    daily=defaultdict(lambda:Counter())
    for iid,(t,it) in intent_by_id.items():
        cat=label(t)
        intent_by_label[cat]['received']+=1
        daily[t.date().isoformat()]['intent_'+cat]+=1
    for n,(opening,closing) in enumerate(all_pairs,1):
        oid=opening['oid']
        shadow=open_by_order[oid]
        assert str(shadow.get('open_order_id'))==oid
        assert abs(int(shadow['position_open_at_ms'])-opening['time_ms'])<=15000
        intent_id=str(shadow.get('intent_id') or '')
        assert intent_id in intent_by_id
        assert intent_id not in trade_open_ids
        trade_open_ids.add(intent_id)
        assert d(shadow['position_qty'])==opening['qty']
        assert abs(d(shadow['position_entry_price'])-opening['price'])<Decimal('0.002')
        op_dt=iso(opening['time_ms']);cl_dt=iso(closing['time_ms'])
        cat=label(op_dt)
        assert cat==label(iso(shadow['position_open_at_ms']))
        daily[op_dt.date().isoformat()]['open_'+cat]+=1
        intent_by_label[cat]['opened']+=1
        if oid in outcome_by_order:
            assert str(outcome_by_order[oid].get('close_order_id'))==closing['oid']
        pnl=sum((d(x['realizedPnl']) for x in closing['rows']),Decimal(0))
        assert abs(pnl-(closing['price']-opening['price'])*opening['qty'])<=Decimal('0.01')
        fees=opening['rows']+closing['rows']
        fees_bnb=sum((d(x['commission']) for x in fees),Decimal(0))
        fees_usdt=sum((d(x['commission'])*bnbrate(x['time']) for x in fees),Decimal(0))
        funding=sum((d(x['income']) for x in income if
             x['incomeType']=='FUNDING_FEE' and x['asset']=='USDT'
             and opening['time_ms']<=int(x['time'])<=closing['time_ms']),Decimal(0))
        lev=d(shadow.get('position_leverage') or 3)
        margin=opening['qty']*opening['price']/lev
        assert margin>0
        net=pnl+funding-fees_usdt
        per_trade.append({
          'index':n,'open_tr':op_dt.isoformat(timespec='seconds'),
          'close_tr':cl_dt.isoformat(timespec='seconds'),
          'reference_label':cat,'exchange_fill_verified':True,
          'exact_redis_open_order_and_intent_match':True,
          'shadow_outcome_present':oid in outcome_by_order,
          'entry_qty_near':money(opening['qty']),
          'entry_price':money(opening['price']),
          'exit_price':money(closing['price']),
          'leverage':money(lev,2),
          'realized_price_pnl_usdt':money(pnl),
          'bnb_commission':money(fees_bnb,8),
          'commission_usdt_indicative_hourly_bnb':money(fees_usdt),
          'funding_usdt':money(funding,8),
          'net_usdt_indicative':money(net),
          'gross_roi_pct':money(pnl/margin*100,3),
          'net_roi_pct_indicative':money(net/margin*100,3),
          'exit_reason_shadow':str(outcome_by_order[oid].get('close_reason') or '')
             if oid in outcome_by_order else 'MISSING_SHADOW_OUTCOME_UNKNOWN_EXIT_REASON',
        })

    for iid,(dt,it) in intent_by_id.items():
        if iid in trade_open_ids:continue
        x=dispatch[iid];entry=x['entry']
        if entry:
            action,reason=entry
            if action=='open':
                if x['risk']=='no_available_balance':
                    why='execution_risk_no_available_balance'
                elif x['contra']=='PENDING':
                    why='contra_trend_pending_after_entry_ready'
                else:
                    why='entry_ready_but_no_order_unexplained'
            else:why=reason
        elif x['pending_recheck']=='wait':why='pending_recheck_wait_no_fresh_entry_decision'
        else:why='no_documented_entry_decision'
        reasons[why]+=1
        reasons_by_label[label(dt)][why]+=1
        intent_by_label[label(dt)]['not_opened']+=1
    assert len(trade_open_ids)==10 and sum(reasons.values())==102
    assert not reasons['entry_ready_but_no_order_unexplained']
    assert not reasons['no_documented_entry_decision']
    assert all(r['reference_label']!='CONFLICT_NO_TRADE' for r in per_trade)

    # Different stages are not equivalent. Count user windows with ANY event,
    # without double-counting overlapping windows as independent signals.
    model_times=[datetime.fromisoformat(x['ts_tr']) for x in model]
    intent_times=[dt for dt,_ in intent_by_id.values()]
    open_times=[iso(p['time_ms']) for p,_ in all_pairs]
    window_coverage=[]
    for i,(lo,hi,which) in enumerate(intervals):
        window_coverage.append({'index':i+1,'start_tr':lo.isoformat(timespec='minutes'),
           'end_tr':hi.isoformat(timespec='minutes'),'requested':which,
           'model_long_count':sum(lo<=t<hi for t in model_times),
           'intent_count':sum(lo<=t<hi for t in intent_times),
           'real_open_count':sum(lo<=t<hi for t in open_times)})
    wanted=[v for v in window_coverage if v['requested']=='LONG_WANTED']
    avoidance=[v for v in window_coverage if v['requested']=='LONG_AVOID']
    assert len(wanted)==44 and len(avoidance)==26
    assert not any(v['real_open_count'] for v in wanted)
    conflict_segments=[]
    for z in reference['derived_disjoint_segments']:
        if 'CONFLICT_NO_TRADE' not in z['labels']:continue
        lo=datetime.fromisoformat(z['start_tr']);hi=datetime.fromisoformat(z['end_tr'])
        c={'start_tr':lo.isoformat(timespec='minutes'),
           'end_tr':hi.isoformat(timespec='minutes'),
           'model_long_count':sum(lo<=t<hi for t in model_times),
           'intent_count':sum(lo<=t<hi for t in intent_times),
           'real_open_count':sum(lo<=t<hi for t in open_times),
           'offline_window_policy':'REJECT'}
        assert c['real_open_count']==0
        conflict_segments.append(c)
    assert len(conflict_segments)==7
    # Summation by label, not window, avoids duplicating same event.
    assert model_labels=={'LONG_TARGET':11,'LONG_AVOID':70,
                          'UNLABELLED':21,'CONFLICT_NO_TRADE':1},model_labels
    assert intent_labels=={'LONG_TARGET':9,'LONG_AVOID':72,'UNLABELLED':31},intent_labels
    assert Counter(row['reference_label'] for row in per_trade)=={
        'LONG_AVOID':4,'UNLABELLED':6}
    assert sum(row['realized_price_pnl_usdt']>0 for row in per_trade)==8
    assert sum(row['realized_price_pnl_usdt']<0 for row in per_trade)==2
    assert len([x for x in per_trade if not x['shadow_outcome_present']])==1

    fee_usdt_all=sum((d(z['commission'])*bnbrate(z['time']) for z in trades),Decimal(0))
    assert abs(fee_usdt_all-sum((d(row['commission_usdt_indicative_hourly_bnb'])
         for row in per_trade),Decimal(0)))<Decimal('0.00002')
    net_indicative=gross+funding_all-fee_usdt_all
    summary={
      'schema':'long1_20261111_15_actual_broker_and_window_audit_v1',
      'date_start_tr':'2026-11-11','date_end_tr_inclusive':'2026-11-15',
      'reference_intervals':70,'wanted_intervals':len(wanted),
      'avoid_intervals':len(avoidance),'conflict_segments':len(conflict_segments),
      'model_long_scores':len(model),
      'model_long_reference_counts':dict(model_labels),
      'trade_intents':len(intent_by_id),
      'trade_intent_reference_counts':dict(intent_labels),
      'opened_positions':len(all_pairs),'not_opened_intents':sum(reasons.values()),
      'open_by_reference':dict(Counter(x['reference_label'] for x in per_trade)),
      'not_opened_reasons':dict(reasons),
      'not_opened_reasons_by_reference':{k:dict(v) for k,v in reasons_by_label.items()},
      'intent_funnel_by_reference':{k:dict(v) for k,v in intent_by_label.items()},
      'daily_funnel':{k:dict(v) for k,v in sorted(daily.items())},
      'window_coverage':window_coverage,'conflict_coverage':conflict_segments,
      'wanted_windows_without_real_open':sum(x['real_open_count']==0 for x in wanted),
      'wanted_windows_with_model_long':sum(x['model_long_count']>0 for x in wanted),
      'wanted_windows_with_trade_intent':sum(x['intent_count']>0 for x in wanted),
      'avoidable_windows_with_real_open':sum(x['real_open_count']>0 for x in avoidance),
      'exchange_usertrade_fills':len(trades),
      'exchange_market_orders':len(orders),'exchange_filled_round_trips':len(all_pairs),
      'actual_broker_wins':sum(x['realized_price_pnl_usdt']>0 for x in per_trade),
      'actual_broker_losses':sum(x['realized_price_pnl_usdt']<0 for x in per_trade),
      'realized_pnl_usdt_exact':money(gross,6),
      'total_funding_usdt_exact':money(funding_all,8),
      'commission_bnb_exact':money(commission_bnb,8),
      'commission_usdt_hourly_estimate':money(fee_usdt_all,6),
      'indicative_total_after_funding_and_commissions_usdt':money(net_indicative,6),
      'bnb_fee_conversion_source':'BNBUSDT perpetual 1h candle CLOSE (estimate, not original execution conversion)',
      'shadow_open_events_matched_exact_order_id':len(open_by_order),
      'shadow_outcomes_matched_exact_close_order_id':len(outcome_by_order),
      'shadow_outcome_missing':1,
      'trades':per_trade,
      'all_windows_conflict_reject_in_offline_test':True,
      'live_clock_restriction_installed':False,
      'old_model_to_trade_intent_exact_trace_verified':False,
      'exchange_api_signed_GET_only':True,
      'new_production_redis_writes':0,'actual_exchange_orders_sent':0,
    }
    path=ROOT/'research/results/LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json'
    path.write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({
      'status':'PASS','model_longs':len(model),'intents':len(intent_by_id),
      'opened':len(all_pairs),'not_opened':sum(reasons.values()),
      'opened_by_label':summary['open_by_reference'],
      'reasons':dict(reasons),'gross_usdt':summary['realized_pnl_usdt_exact'],
      'funding_usdt':summary['total_funding_usdt_exact'],
      'fees_bnb':summary['commission_bnb_exact'],
      'fees_usdt_indicative':summary['commission_usdt_hourly_estimate'],
      'net_usdt_indicative':summary['indicative_total_after_funding_and_commissions_usdt'],
      'wanted_windows_with_any_open':len(wanted)-summary['wanted_windows_without_real_open'],
      'conflicts_with_open':sum(x['real_open_count']>0 for x in conflict_segments),
      'shadow_outcome_missing':1,'no_orders_sent':True
    },sort_keys=True))

if __name__=='__main__':
    main()
