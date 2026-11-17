#!/usr/bin/env python3
"""Research-only existing entry cohort classifier. No orders, Redis or API calls."""
from pathlib import Path
import csv
P=Path(__file__).resolve().parents[1]/'results/LONG1_NEAR_NOV12_13_WIN_LOSS_ENTRY_CONTEXT_COMPARISON.csv'
rows=list(csv.DictReader(P.open()))
assert len(rows)==7
for x in rows:
    market=(float(x['m3_ret_mean3_pct'])<0 and float(x['m3_upfrac3'])<=1/3)
    flow=(float(x['flow15'])<0 and float(x['flow60'])<0)
    flagged=market and flow
    assert flagged== (x['dual_contra']=='True'),x['utc']
    decision='SHADOW_ADVISORY_PENDING' if flagged else 'NO_NEW_GUARD_HOLD'
    print(x['utc'],x['result'],decision)
print('SAMPLE',len(rows),'SHADOW_FLAGGED',sum(x['dual_contra']=='True' for x in rows),'WINNERS_FLAGGED',sum(x['dual_contra']=='True' and x['result']=='WIN' for x in rows))
