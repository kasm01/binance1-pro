import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
POLICY=ROOT/'research/results/NEAR_SHADOW_ADAPTIVE_TIMEOUT_POLICY.json'
REG=ROOT/'research/results/NEAR_SHADOW_EXECUTION_REGIME_ANCHORS.csv'
QUEUE=ROOT/'research/results/NEAR_SHADOW_EXECUTION_QUEUE.csv'
OUT=ROOT/'research/results/NEAR_SHADOW_ADAPTIVE_TIMEOUT_OOS.csv'
BLOCK_MS=6*60*60*1000


def main():
    if not POLICY.exists() or not REG.exists() or not QUEUE.exists():
        print('MISSING_INPUT'); return
    policy=json.loads(POLICY.read_text())
    low=float(policy['rv30_low_max_bps'])
    train_block=int(policy['discovery_validation_block_id'])
    reg=pd.read_csv(REG)[['anchor_ms','rv30_bps']].drop_duplicates('anchor_ms')
    q=pd.read_csv(QUEUE)
    d=q.merge(reg,on='anchor_ms',how='left')
    d['validation_block_id']=(pd.to_numeric(d.anchor_ms,errors='coerce')//BLOCK_MS).astype('Int64')
    d=d[d.validation_block_id>train_block].copy()
    if d.empty:
        print('NO_FUTURE_VALIDATION_BLOCKS'); return
    d=d[(d.side=='long') & (d.queue_mult==1.0) & (d.maker_fee_bps==2.0)].copy()
    d['policy_wait_s']=d.rv30_bps.apply(lambda x: 2 if pd.notna(x) and x<=low else 1)
    d=d[d.wait_s==d.policy_wait_s]
    rows=[]
    for vb,g in d.groupby('validation_block_id'):
        z=g.groupby('notional_usdt').agg(
            advantage=('advantage_vs_market_bps','mean'),
            maker_incremental=('maker_incremental_bps','mean'),
            markout5=('maker_weighted_markout_5s_bps','mean'),
            markout15=('maker_weighted_markout_15s_bps','mean'),
            anchors=('anchor_ms','nunique')).reset_index()
        if len(z)<3: continue
        n=int(z.anchors.min()); adv=float(z.advantage.min()); mk=float(z.maker_incremental.min())
        m5=float(z.markout5.min()); m15=float(z.markout15.min())
        if n<10: status='INCONCLUSIVE'
        elif adv>0 and mk>0 and m5>=0 and m15>=0: status='PASS'
        else: status='FAIL'
        rows.append({'validation_block_id':int(vb),'n_min':n,'worst_advantage_bps':adv,
                     'worst_maker_incremental_bps':mk,'worst_markout5_bps':m5,
                     'worst_markout15_bps':m15,'status':status})
    out=pd.DataFrame(rows)
    out.to_csv(OUT,index=False)
    print('NO_COMPLETE_FUTURE_BLOCKS' if out.empty else out.to_string(index=False))
    print('out',OUT)

if __name__=='__main__': main()
