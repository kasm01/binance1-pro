"""Pure, causal LONG countertrend gate. No exchange access or orders."""
from __future__ import annotations
import math
from datetime import datetime, timezone
def _float(x):
    try:
        f=float(x)
        return f if math.isfinite(f) else None
    except (ValueError,TypeError):return None
def assess_1m(rows, now_ms):
    """Rows Binance 1m candles: open_time/o/h/l/c/close_time/quote/taker_buy_quote.
    Only contiguous, completed 1m bars; 3m/5m formed by exchange UTC bucketing.
    """
    a=[]
    for x in rows or []:
        try:
            if isinstance(x,dict):
                t=int(x['open_time']);end=int(x['close_time'])
                o=_float(x['open']);c=_float(x['close']);q=_float(x['quote_asset_volume']);b=_float(x['taker_buy_quote_volume'])
            else:
                t=int(x[0]);end=int(x[6]);o=_float(x[1]);c=_float(x[4]);q=_float(x[7]);b=_float(x[10])
            if t+59999!=end or end>=now_ms or any(z is None for z in [o,c,q,b]) or o<=0 or c<=0 or q<=0 or b<0 or b>q:
                continue
            a.append((t,o,c,q,b))
        except (KeyError,ValueError,TypeError,IndexError):continue
    a.sort(key=lambda z:z[0]);a=[x for i,x in enumerate(a) if i==0 or x[0]!=a[i-1][0]]
    if len(a)<65 or now_ms-(a[-1][0]+60000)>125000:
        return {'state':'UNKNOWN','reason':'missing_or_stale_completed_1m','bars':len(a)}
    a=a[-75:]
    if any(a[i][0]-a[i-1][0]!=60000 for i in range(1,len(a))):
        return {'state':'UNKNOWN','reason':'noncontiguous_1m'}
    def flow(n):
        z=a[-n:];q=sum(v[3] for v in z)
        return (2*sum(v[4] for v in z)-q)/q if q>0 else None
    def completed(n):
        d={}
        for x in a:
            k=x[0]//(n*60000);d.setdefault(k,[]).append(x)
        return [(k,v) for k,v in sorted(d.items()) if len(v)==n and v[0][0]==k*n*60000 and v[-1][0]==(k+1)*n*60000-60000]
    g3=completed(3);g5=completed(5)
    if len(g3)<4 or len(g5)<4:
        return {'state':'UNKNOWN','reason':'missing_completed_3m_5m'}
    def mret(gr):return [v[-1][2]/v[0][1]-1 for _,v in gr[-3:]]
    v3=mret(g3);v5=mret(g5)
    f15=flow(15);f60=flow(60)
    if f15 is None or f60 is None:return {'state':'UNKNOWN','reason':'missing_flow'}
    price_down_3m=sum(v3)/3<0 and sum(x>0 for x in v3)<=1
    price_down_5m=sum(v5)/3<0
    dual=price_down_3m and f15<0 and f60<0
    # Report 5m as explicit extra confirmation, but the trigger matches previously
    # studied 3m SHORT and dual flow. We do not loosen to a 1m-only signal.
    contra=bool(dual)
    return {'state':'CONTRA' if contra else 'CLEAR','reason':'3m_short_and_flow15_flow60_negative' if contra else 'no_joint_conflict',
       'price_down_3m':price_down_3m,'price_down_5m':price_down_5m,
       'm3_mean':sum(v3)/3,'m3_upfrac':sum(z>0 for z in v3)/3,
       'm5_mean':sum(v5)/3,'m3_latest_up':v3[-1]>0,'m5_latest_up':v5[-1]>0,
       'f15':f15,'f60':f60,
       'closed_3m_ms':g3[-1][1][-1][0]+60000,
       'closed_5m_ms':g5[-1][1][-1][0]+60000,
       'last_1m_close_ms':a[-1][0]+60000}
