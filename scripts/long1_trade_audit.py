#!/usr/bin/env python3
from __future__ import annotations
import csv, json, re, subprocess
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
LOG=ROOT/'logs/main.log'; JOURNAL=ROOT/'logs/trade_journal.csv'
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

def main():
    ls=lines(); commits=[]
    for i,line in enumerate(ls):
        m=COMMIT.search(line)
        if m and m.group(1).upper()=='NEARUSDT': commits.append((i,m))
    print('=== LONG1 TRADE AUDIT ===')
    if not commits:
        print('status: WAITING_FIRST_REAL_COMMIT')
        print('note: no [EXEC][OPEN][COMMIT] for NEARUSDT yet')
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
    j=latest_journal()
    if j:
        print('latest_close_journal:', json.dumps(j,separators=(',',':')))
    else:
        print('close_status: OPEN_OR_NO_JOURNAL_CLOSE_YET')

if __name__=='__main__': main()
