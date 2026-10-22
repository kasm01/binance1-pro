from pathlib import Path
import pandas as pd, numpy as np, json
ROOT=Path("/home/kasm920/binance1-pro")
LONG=ROOT/"research/results/LONG1_FINAL_CANDIDATE_1Y_TRADES_BY_SEED"
SHORT=Path("/home/kasm920/binance1/research/short/results/SHORT1_V49B_TRADE_CONFIRM/V49B_R70_W2/closed_positions.csv")
OUT=ROOT/"research/results/LONG1_SHORT1_V49B_INTEGRATION"; OUT.mkdir(parents=True,exist_ok=True)
START=pd.Timestamp("2025-10-13 18:53:00",tz="UTC")
END=pd.Timestamp("2026-10-11 21:36:00",tz="UTC")

def short_events():
    s=pd.read_csv(SHORT); s["ts"]=pd.to_datetime(s.close_ts,utc=True); s=s.sort_values("ts").copy()
    # closed-equity approximation; difference to minute equity is <1 USDT over whole year due entry-fee timing
    s["before_side"]=1000.0+s.pnl_net.cumsum().shift(fill_value=0.0)
    s["r"]=s.pnl_net/s.before_side
    s["side"]="SHORT"; return s[(s.ts>=START)&(s.ts<=END)][["ts","side","r","pnl_net"]]

def long_events(seed):
    x=pd.read_csv(LONG/f"seed{seed}.csv"); x["ts"]=pd.to_datetime(x.exit_ts,utc=True); x["r"]=x.net/x.before; x["side"]="LONG"
    return x[(x.ts>=START)&(x.ts<=END)][["ts","side","r","net"]].rename(columns={"net":"pnl_net"})

def simulate(seed,weight=0.5,overlay=False):
    ev=pd.concat([long_events(seed),short_events()],ignore_index=True).sort_values(["ts","side"]).reset_index(drop=True)
    eq=1000.0; peak=eq; mode="NORMAL"; rec_wins=0; rows=[]
    for r in ev.itertuples(index=False):
        mult=1.0
        if overlay: mult={"NORMAL":1.0,"RECOVERY":0.70,"REDUCED":0.50}[mode]
        pnl=eq*weight*float(r.r)*mult
        before=eq; eq+=pnl; peak=max(peak,eq); dd=eq/peak-1
        if overlay:
            if mode in ("NORMAL","RECOVERY") and dd<=-0.08:
                mode="REDUCED"; rec_wins=0
            elif mode=="REDUCED" and dd>=-0.04:
                mode="RECOVERY"; rec_wins=0
            elif mode=="RECOVERY":
                if pnl<0:
                    mode="REDUCED"; rec_wins=0
                elif pnl>0:
                    rec_wins+=1
                    if rec_wins>=2: mode="NORMAL"; rec_wins=0
        rows.append((r.ts,r.side,before,pnl,eq,dd*100,mode,mult))
    q=pd.DataFrame(rows,columns=["ts","side","before","pnl","equity","dd_pct","mode","risk_mult"])
    gp=q.loc[q.pnl>0,"pnl"].sum(); gl=-q.loc[q.pnl<0,"pnl"].sum(); pf=gp/gl if gl else np.nan
    d=q.set_index("ts")["equity"].resample("D").last().ffill(); dret=d.pct_change().fillna(d.iloc[0]/1000-1)*100
    m=q.set_index("ts")["equity"].resample("ME").last().ffill(); mret=m.pct_change().fillna(m.iloc[0]/1000-1)*100
    summary={"seed":seed,"weight_each":weight,"overlay":overlay,"return_pct":(eq/1000-1)*100,"pf":pf,"maxdd_pct":q.dd_pct.min(),"events":len(q),"long_events":int((q.side=="LONG").sum()),"short_events":int((q.side=="SHORT").sum()),"negative_days":int((dret<0).sum()),"positive_days":int((dret>0).sum()),"negative_months":int((mret<0).sum()),"worst_month_pct":float(mret.min()),"best_month_pct":float(mret.max()),"reduced_event_share_pct":float((q.risk_mult<1).mean()*100) if overlay else 0.0}
    return q,dret,mret,summary

def daily_corr(seed):
    L=long_events(seed).copy(); S=short_events().copy()
    def daily(x):
        # sum log-like event returns is close enough at daily scale; compound exactly
        return x.assign(one=1+x.r).set_index("ts")["one"].resample("D").prod()-1
    z=pd.concat([daily(L).rename("long"),daily(S).rename("short")],axis=1).fillna(0)
    active=z[(z.long!=0)|(z.short!=0)]
    return float(active.long.corr(active.short)), int(((active.long*active.short)<0).sum()), len(active)

rows=[]
for seed in range(1,7):
    corr,opp,active=daily_corr(seed)
    for name,w,ov in [("EQ50_NATIVE",.5,False),("EQ50_CENTRAL_OVERLAY",.5,True),("FULL100_STRESS",1.0,False)]:
        q,d,m,s=simulate(seed,w,ov); s["scenario"]=name; s["daily_corr_active"]=corr; s["opposite_sign_active_days"]=opp; s["active_days"]=active; rows.append(s)
        q.to_csv(OUT/f"{name}_seed{seed}_events.csv",index=False)
        pd.DataFrame({"return_pct":d}).to_csv(OUT/f"{name}_seed{seed}_daily.csv")
        pd.DataFrame({"return_pct":m}).to_csv(OUT/f"{name}_seed{seed}_monthly.csv")
R=pd.DataFrame(rows); R.to_csv(OUT/"summary_by_seed.csv",index=False)
A=R.groupby("scenario").agg(return_mean=("return_pct","mean"),return_min=("return_pct","min"),return_max=("return_pct","max"),pf_mean=("pf","mean"),maxdd_mean=("maxdd_pct","mean"),maxdd_worst=("maxdd_pct","min"),worst_month_mean=("worst_month_pct","mean"),neg_months_mean=("negative_months","mean"),corr_mean=("daily_corr_active","mean"),opposite_days_mean=("opposite_sign_active_days","mean"),overlay_reduced_share=("reduced_event_share_pct","mean")).reset_index()
A.to_csv(OUT/"summary_aggregate.csv",index=False)
print("COMMON",START,END)
print(A.to_string(index=False))
print("\nBY SEED EQ50_NATIVE")
print(R[R.scenario=="EQ50_NATIVE"][["seed","return_pct","pf","maxdd_pct","negative_months","worst_month_pct","daily_corr_active","opposite_sign_active_days"]].to_string(index=False))
print("\nBY SEED CENTRAL")
print(R[R.scenario=="EQ50_CENTRAL_OVERLAY"][["seed","return_pct","pf","maxdd_pct","negative_months","worst_month_pct","reduced_event_share_pct"]].to_string(index=False))
