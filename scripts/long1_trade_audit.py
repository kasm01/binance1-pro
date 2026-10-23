#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, re, subprocess, time
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
LOG=ROOT/'logs/main.log'; JOURNAL=ROOT/'logs/trade_journal.csv'
CENTRAL_KEY='telemetry:central_risk:shadow:current'
PREP=re.compile(r"\[EXEC\]\[ORDER\]\[PREP\] symbol=(\S+) side=(\S+).*?signal_score=([0-9.]+).*?lev_target=(\d+)")
ORDER=re.compile(r"\[EXEC\]\[ORDER\] OPEN OK .*?symbol=(\S+) side=(\S+) qty=([0-9.]+).*?lev=(\d+).*?summary=(\{.*\})")
COMMIT=re.compile(r"\[EXEC\]\[OPEN\]\[COMMIT\] symbol=(\S+) side=(\S+) source=(\S+) qty=([0-9.]+) price=([0-9.]+) notional=([0-9.]+)")
SCORE=re.compile(r"\[MODEL-SCORE\].*?symbol=(\S+).*?p_used=([0-9.]+).*?long_thr=([0-9.]+).*?side=(\S+).*?gate_reason=(\S+).*?atr_rank=([^\s]+)")

def lines() -> list[str]:
    if not LOG.exists(): return []
    return LOG.read_text(errors='replace').splitlines()

def latest_journal(symbol='NEARUSDT') -> dict[str,Any] | None:
    if not JOURNAL.exists() or JOURNAL.stat().st_size==0: return None
    with JOURNAL.open(newline='',encoding='utf-8') as f:
        rows=[r for r in csv.DictReader(f) if str(r.get('symbol','')).upper()==symbol]
    return rows[-1] if rows else None



def central_snapshot(refresh: bool=False) -> dict[str,Any] | None:
    if refresh:
        try:
            subprocess.run([str(ROOT/'venv/bin/python'), str(ROOT/'scripts/central_risk_shadow_observer.py')], cwd=str(ROOT), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except Exception as e:
            print(f'central_refresh_warning: {type(e).__name__}:{e}')
    try:
        raw=subprocess.check_output(['redis-cli','--raw','GET',CENTRAL_KEY], cwd=str(ROOT), text=True, timeout=3).strip()
        return json.loads(raw) if raw else None
    except Exception:
        return None

def print_central(report: dict[str,Any] | None) -> None:
    if not report:
        print('central_risk: no snapshot available')
        return
    age=max(0.0,time.time()-float(report.get('ts') or 0.0))
    acct=report.get('account') or {}; st=report.get('portfolio_state') or {}; h=report.get('exposure_health') or {}; caps=report.get('caps') or {}; sh=report.get('symbol_health') or {}
    print('central_risk:', f"authority={report.get('authority')} age_sec={age:.1f} status={h.get('status')} mode={st.get('mode')} equity={float(acct.get('mtm_equity') or 0):.8f} prod_ready={report.get('production_ready')}")
    print('central_exposure:', f"gross={float(h.get('gross_ratio') or 0):.4f}/{caps.get('gross')} long={float(h.get('long_ratio') or 0):.4f}/{caps.get('long')} short={float(h.get('short_ratio') or 0):.4f}/{caps.get('short')} abs_net={float(h.get('abs_net_ratio') or 0):.4f}/{caps.get('abs_net')} warnings={h.get('warning_caps') or []} breaches={h.get('breached_caps') or []}")
    near=(sh or {}).get('NEARUSDT')
    if isinstance(near,dict):
        print('central_near:', f"notional={float(near.get('notional') or 0):.4f} ratio={float(near.get('ratio') or 0):.4f}/{caps.get('symbol')} status={near.get('status')}")
    pos=report.get('positions') or []
    if pos:
        for r in pos:
            if str(r.get('symbol') or '').upper()=='NEARUSDT':
                print('central_position:', json.dumps(r,separators=(',',':'),default=str))

def main():
    ap=argparse.ArgumentParser(description='LONG1 first/last real trade audit')
    ap.add_argument('--refresh-central', action='store_true', help='refresh central-risk snapshot with one account REST call before reporting')
    args=ap.parse_args()
    central=central_snapshot(refresh=args.refresh_central)
    ls=lines(); commits=[]
    for i,line in enumerate(ls):
        m=COMMIT.search(line)
        if m and m.group(1).upper()=='NEARUSDT': commits.append((i,m))
    print('=== LONG1 TRADE AUDIT ===')
    if not commits:
        print('status: WAITING_FIRST_REAL_COMMIT')
        print('note: no [EXEC][OPEN][COMMIT] for NEARUSDT yet')
        print_central(central)
        return
    i,c=commits[-1]
    window=ls[max(0,i-250):i+1]
    prep=None; order=None; score=None
    for line in reversed(window):
        if prep is None:
            m=PREP.search(line)
            if m and m.group(1).upper()=='NEARUSDT': prep=m
        if order is None:
            m=ORDER.search(line)
            if m and m.group(1).upper()=='NEARUSDT': order=m
        if score is None:
            m=SCORE.search(line)
            if m and m.group(1).upper()=='NEARUSDT': score=m
    commit={'symbol':c.group(1),'side':c.group(2),'source':c.group(3),'qty':float(c.group(4)),'entry_price':float(c.group(5)),'notional':float(c.group(6))}
    print('commit:', json.dumps(commit,separators=(',',':')))
    if score:
        print('model:', f"score={float(score.group(2)):.6f} thr={float(score.group(3)):.4f} side={score.group(4)} gate={score.group(5)} atr_rank={score.group(6)}")
    else: print('model: not found in preceding log window')
    if prep:
        print('prep:', f"signal_score={float(prep.group(3)):.6f} leverage_target={prep.group(4)}")
    else: print('prep: not found')
    if order:
        summary_raw=order.group(5)
        try: summary=json.loads(summary_raw)
        except Exception: summary={'raw':summary_raw}
        print('order:', json.dumps({'qty_requested':float(order.group(3)),'leverage':int(order.group(4)),'summary':summary},separators=(',',':'),default=str))
        avg=None; exq=None
        if isinstance(summary,dict):
            try: avg=float(summary.get('avgPrice') or 0) or None
            except Exception: pass
            try: exq=float(summary.get('executedQty') or 0) or None
            except Exception: pass
        if avg and commit['entry_price']:
            slip=(commit['entry_price']/avg-1)*10000
            print(f'fill_vs_commit_bps={slip:.3f}')
    else: print('order: not found')
    print_central(central)
    j=latest_journal()
    if j:
        print('latest_close_journal:', json.dumps(j,separators=(',',':')))
    else:
        print('close_status: OPEN_OR_NO_JOURNAL_CLOSE_YET')

if __name__=='__main__': main()
