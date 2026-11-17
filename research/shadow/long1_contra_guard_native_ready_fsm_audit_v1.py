#!/usr/bin/env python3
"""Read-only native-intent follow-up audit. Never fabricates orders or READY decisions."""
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
out=ROOT/'research/results'
ctx=pd.read_csv(out/'LONG1_REAL133_INTENT_CONTEXT_AUDIT.csv').sort_values('signal_ts_ms').reset_index(drop=True)
dec=pd.read_csv(out/'LONG1_REAL133_INTENT_DECISION_LOG_AUDIT.csv')
x=ctx.merge(dec[['intent_id','first_action','first_reason','first_shadow','dispatch_found']],left_on='signal_id',right_on='intent_id',how='left')
assert len(x)==133
rows=[]
for e in x.itertuples(index=False):
 t=int(e.signal_ts_ms);dual=bool(e.dual_contra)
 subsequent=x[(x.signal_ts_ms>t)&(x.signal_ts_ms<=t+30*60000)]
 def eligible(df):
  return df[(df.first_action=='open') & (df.first_reason=='entry_confirmation_ready') & (df.first_shadow==False)]
 native=eligible(subsequent)
 full=native[~native.dual_contra]
 rows.append(dict(signal_id=e.signal_id,signal_ms=t,dual=dual,original_action=e.first_action,original_reason=e.first_reason,original_real_open=bool(e.actually_open),following_intents_30m=len(subsequent),native_ready_30m=len(native),native_ready_nondual_30m=len(full),first_native_ready_delay_min=round((int(native.iloc[0].signal_ts_ms)-t)/60000,2) if len(native) else None,first_ready_nondual_delay_min=round((int(full.iloc[0].signal_ts_ms)-t)/60000,2) if len(full) else None,first_ready_nondual_id=full.iloc[0].signal_id if len(full) else None))
D=pd.DataFrame(rows);path=out/'LONG1_CONTRA_GUARD_REAL_READY_REVALIDATION_133_20261111.csv';D.to_csv(path,index=False)
print('TOTAL_CANDIDATES',len(D),'DUAL',D.dual.sum(),'NONDUAL',(~D.dual).sum())
print('DUAL_REAL_OPEN',sum(D.dual&D.original_real_open),'DUAL_NATIVE_READY_30M',sum(D.dual&(D.native_ready_30m>0)),'DUAL_NATIVE_READY_NONDUAL_30M',sum(D.dual&(D.native_ready_nondual_30m>0)))
print('DUAL_ACTION_DISTRIBUTION',D[D.dual].original_reason.value_counts().to_dict())
print('DUAL_ORIGINAL_READY',sum(D.dual&D.original_reason.eq('entry_confirmation_ready')))
print('DUAL_TO_NATIVE_READY_DETAIL');print(D[D.dual&(D.native_ready_30m>0)][['signal_id','original_reason','original_real_open','native_ready_30m','native_ready_nondual_30m','first_native_ready_delay_min']].to_string(index=False))
print('DUAL_ACTUAL_OPEN_NO_NONDUAL_NEXT',sum(D.dual&D.original_real_open&D.native_ready_nondual_30m.eq(0)))
print('FILE',path)
