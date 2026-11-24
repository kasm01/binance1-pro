import unittest
from scanner.context_entry_shadow_v1 import assess,MAX_BARS
from tests.test_extreme_momentum_40_v1 import START
from scanner.extreme_momentum_v1 import MS

ASOF=START+160*MS
def fixture(direction=1, move=.0015, last_opposite=False, high_volume=True):
    rows=[]
    close=10.
    for i in range(160):
        o=close
        step=direction*move
        if last_opposite and i==159:step=-direction*move*3
        close=o*(1+step)
        rows.append({'t':START+i*MS,'o':o,'h':max(o,close)*1.0003,
          'l':min(o,close)*.9997,'c':close,
          'quote_volume':1e6*(6 if high_volume and i>=155 else 1)})
    return rows
class ShadowTests(unittest.TestCase):
 def test_only_research_never_ready(self):
    for direction,label in ((1,'LONG'),(-1,'SHORT')):
        result=assess('TESTUSDT',label,fixture(direction),observed_at_ms=ASOF)
        assert result['state'] in {'COST_PENDING','ENTRY_PENDING','CONTEXT_PENDING','CONTEXT_REJECT'},result
        assert result['ready'] is False and result['telegram_ready'] is False
        assert result['order_authorized'] is False
 def test_insufficient_stale_partial_gapped_rejected(self):
    rows=fixture()
    assert assess('TESTUSDT','LONG',rows[:80],observed_at_ms=ASOF)['state']=='INSUFFICIENT_DATA'
    assert assess('TESTUSDT','LONG',rows,observed_at_ms=ASOF-1)['reason']=='future_or_stale_source'
    assert assess('TESTUSDT','LONG',rows,observed_at_ms=ASOF+3*MS)['reason']=='future_or_stale_source'
    bad=list(rows);bad[-14]=dict(bad[-14],t=bad[-14]['t']+MS)
    assert assess('TESTUSDT','LONG',bad,observed_at_ms=ASOF)['reason']=='source_gap_or_duplicate'
 def test_direction_and_last_candle(self):
    rows=fixture()
    assert assess('TESTUSDT','SHORT',rows,observed_at_ms=ASOF)['state']=='CONTEXT_REJECT'
    rows=fixture(last_opposite=True)
    r=assess('TESTUSDT','LONG',rows,observed_at_ms=ASOF)
    assert r['state'] in ('ENTRY_PENDING','CONTEXT_PENDING','CONTEXT_REJECT'),r
 def test_no_volume_no_watch(self):
    result=assess('TESTUSDT','LONG',fixture(high_volume=False),observed_at_ms=ASOF)
    assert result['state']=='CONTEXT_REJECT'
    assert not result['ready']
if __name__=='__main__':unittest.main()
