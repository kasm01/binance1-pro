from pathlib import Path
import pandas as pd, numpy as np
P=Path('research/results/NEAR_5M_TOP1_MAKER_EXEC_WF.csv')
d=pd.read_csv(P)
base=d[d.scenario.eq('TAKER_NOW')].iloc[0]
# Exact fee-only upper bounds holding timing/outcomes fixed.
# Standard fees: taker 5bps/side, maker 2bps/side. Baseline is 10bps RT.
tp=base.tp_pct/100.0
fee_only_mt = base.net_bps + 3.0  # maker entry, taker exit
fee_only_mm_tp = base.net_bps + 3.0 + tp*3.0 # maker entry; TP exits maker, non-TP taker
# Theoretical BNB discounted: taker 4.5, maker 1.8 bps/side; relative to 10bps baseline.
fee_only_bnb_mt = base.net_bps + (10.0-(1.8+4.5))
fee_only_bnb_mm_tp = base.net_bps + (10.0-(1.8+4.5)) + tp*(4.5-1.8)
print('BASE',base.net_bps,'TP%',base.tp_pct,'SL%',base.sl_pct,'TIMEOUT%',base.timeout_pct)
print('FEE_ONLY_CEILING standard maker-entry+taker-exit',fee_only_mt)
print('FEE_ONLY_CEILING standard maker-entry+maker-TP',fee_only_mm_tp)
print('FEE_ONLY_CEILING bnb maker-entry+taker-exit',fee_only_bnb_mt)
print('FEE_ONLY_CEILING bnb maker-entry+maker-TP',fee_only_bnb_mm_tp)
print('\nADVERSE_SELECTION_VS_FEE_ONLY')
for _,r in d[d.scenario.str.contains('TP_M')].iterrows():
    print(r.scenario,'actual',round(r.net_bps,4),'gap_to_fee_only',round(r.net_bps-fee_only_mm_tp,4),'fill',round(r.maker_fill_pct,2),'TP',round(r.tp_pct,2),'SL',round(r.sl_pct,2))
