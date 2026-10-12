import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
QUEUE=ROOT/'research/results/NEAR_SHADOW_EXECUTION_QUEUE.csv'
ANCH=ROOT/'research/results/NEAR_SHADOW_EXECUTION_REGIME_ANCHORS.csv'
OUT=ROOT/'research/results/NEAR_SHADOW_ADAPTIVE_TIMEOUT.csv'
POLICY=ROOT/'research/results/NEAR_SHADOW_ADAPTIVE_TIMEOUT_POLICY.json'

# Frozen after exploratory sample on 2026-10-12. Research only.
RV30_LOW_MAX_BPS=6.059917300053492
RV30_HIGH_MIN_BPS=7.930891479172919


def main():
    q=pd.read_csv(QUEUE); a=pd.read_csv(ANCH)
    x=q.merge(a[['anchor_ms','rv30_bps']],on='anchor_ms',how='inner')
    x=x[(x.side=='long')&(x.queue_mult==1.0)&(x.maker_fee_bps==2.0)].copy()
    x['adaptive_wait_s']=np.where(x.rv30_bps<=RV30_LOW_MAX_BPS,2,1)
    rows=[]
    policies={'FIXED_1S':lambda d:d.wait_s==1,'FIXED_2S':lambda d:d.wait_s==2,'FIXED_3S':lambda d:d.wait_s==3,
              'ADAPT_LOW2_ELSE1':lambda d:d.wait_s==d.adaptive_wait_s}
    for name,fn in policies.items():
        g=x[fn(x)].copy()
        per=[]
        for notion,gn in g.groupby('notional_usdt'):
            per.append({'notional':float(notion),'n':int(gn.anchor_ms.nunique()),
                        'adv':float(gn.advantage_vs_market_bps.mean()),
                        'maker':float(gn.maker_incremental_bps.mean()),
                        'timing':float(gn.wait_timing_bps.mean()),
                        'fill':float(gn.fill_fraction.mean()),
                        'm5':float(gn.maker_weighted_markout_5s_bps.mean()),
                        'm15':float(gn.maker_weighted_markout_15s_bps.mean())})
        p=pd.DataFrame(per)
        rows.append({'policy':name,'n_min':int(p.n.min()),'notional_count':int(p.notional.nunique()),
                     'worst_advantage_bps':float(p.adv.min()),'worst_maker_incremental_bps':float(p.maker.min()),
                     'worst_wait_timing_bps':float(p.timing.min()),'min_fill_fraction':float(p.fill.min()),
                     'worst_markout5_bps':float(p.m5.min()),'worst_markout15_bps':float(p.m15.min())})
    out=pd.DataFrame(rows)
    out.to_csv(OUT,index=False)
    policy={'research_only':True,'frozen_from':'2026-10-12 exploratory block','rv30_low_max_bps':RV30_LOW_MAX_BPS,
            'rv30_high_min_bps':RV30_HIGH_MIN_BPS,'adaptive_rule':'if rv30_bps <= low_max: wait 2s else wait 1s',
            'production_action':'NO_CHANGE','validation_requirement':'future validation blocks only; do not retune thresholds on each block'}
    POLICY.write_text(json.dumps(policy,indent=2),encoding='utf-8')
    print(out.to_string(index=False)); print('out',OUT); print('policy',POLICY)

if __name__=='__main__':main()
