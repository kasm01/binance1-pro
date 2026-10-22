from pathlib import Path
import sys,pandas as pd
ROOT=Path('/home/kasm920/binance1-pro'); sys.path.insert(0,str(ROOT))
from orchestration.risk.central_risk_master import CentralRiskConfig
from research.portfolio.simulate_long1_short1_central_risk_v1 import run
OUT=ROOT/'research/results/LONG1_SHORT1_CENTRAL_DD_SWEEP_V1_20261021'; OUT.mkdir(parents=True,exist_ok=True)
configs=[('DD08_R04',.08,.04),('DD10_R05',.10,.05),('DD12_R06',.12,.06),('DD14_R07',.14,.07)]
rows=[]
for name,tr,rec in configs:
 cfg=CentralRiskConfig(dd_reduce_trigger=tr,dd_recover_trigger=rec,recovery_multiplier=.70,reduced_multiplier=.50,recovery_successes_required=2,max_open_positions=2,max_gross_exposure_ratio=1.0,max_long_exposure_ratio=.5,max_short_exposure_ratio=.5,max_abs_net_exposure_ratio=.5,max_symbol_exposure_ratio=.5)
 for seed in range(1,7):
  s=run(seed,name,cfg,use_state=True); rows.append(s); print('RESULT',s,flush=True)
R=pd.DataFrame(rows); R.to_csv(OUT/'summary_by_seed.csv',index=False)
A=R.groupby('scenario').agg(return_mean=('return_pct','mean'),return_min=('return_pct','min'),pf_mean=('pf','mean'),dd_mean=('maxdd_pct','mean'),dd_worst=('maxdd_pct','min'),worst_month_mean=('worst_month_pct','mean'),negative_months_mean=('negative_months','mean'),state_changes_mean=('state_changes','mean')).reset_index()
A.to_csv(OUT/'summary_aggregate.csv',index=False); print('\nAGG\n'+A.to_string(index=False),flush=True)
