#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, statistics, subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / 'logs/main.log'
SCORE_RE = re.compile(r"\[MODEL-SCORE\].*?symbol=(\S+).*?p_used=([0-9.]+).*?long_thr=([0-9.]+).*?side=(\S+).*?gate_reason=(\S+).*?atr_rank=([^\s]+)")
GATE_RE = re.compile(r"\[MODEL\]\[LONG-DYNAMIC-GATE\].*?symbol=(\S+).*?base=([0-9.]+).*?final=([0-9.]+).*?reason=(\S+).*?atr_rank=([^\s]+).*?close_loc=([^\s]+).*?lower_wick_frac=([^\s]+)")

def tail_lines(path: Path, n: int = 12000) -> list[str]:
    if not path.exists(): return []
    try:
        out = subprocess.check_output(['tail','-n',str(n),str(path)], text=True, errors='replace')
        return out.splitlines()
    except Exception:
        return path.read_text(errors='replace').splitlines()[-n:]

def f(x: str):
    try: return float(x)
    except Exception: return None

def redis_xlen(name: str) -> int | None:
    try:
        return int(subprocess.check_output(['redis-cli','XLEN',name], text=True, timeout=2).strip())
    except Exception: return None

def svc(name: str) -> str:
    try: return subprocess.check_output(['systemctl','--user','is-active',name], text=True, timeout=2).strip()
    except Exception: return 'unknown'

def main() -> None:
    rows=[]; gates=[]
    for line in tail_lines(LOG):
        m=SCORE_RE.search(line)
        if m and m.group(1).upper()=='NEARUSDT':
            rows.append({'line':line,'score':f(m.group(2)),'thr':f(m.group(3)),'side':m.group(4),'reason':m.group(5),'atr':f(m.group(6))})
        g=GATE_RE.search(line)
        if g and g.group(1).upper()=='NEARUSDT':
            gates.append({'line':line,'base':f(g.group(2)),'final':f(g.group(3)),'reason':g.group(4),'atr':f(g.group(5)),'close_loc':f(g.group(6)),'lower_wick':f(g.group(7))})
    recent=rows[-20:]
    scores=[r['score'] for r in recent if r['score'] is not None]
    latest=recent[-1] if recent else None
    gate=gates[-1] if gates else None
    print('=== LONG1 LIVE TELEMETRY ===')
    print('services:', 'supervisor='+svc('binance1-long-supervisor.service'), 'orch='+svc('binance1-long-orch.service'))
    if scores:
        print(f'score_20: n={len(scores)} min={min(scores):.6f} mean={statistics.fmean(scores):.6f} max={max(scores):.6f}')
    else: print('score_20: no data')
    if latest:
        gap=(latest['thr']-latest['score']) if latest['thr'] is not None and latest['score'] is not None else None
        print(f"latest: score={latest['score']:.6f} thr={latest['thr']:.4f} gap={gap:.6f} side={latest['side']} gate={latest['reason']} atr_rank={latest['atr']}")
    if gate:
        print(f"gate: base={gate['base']:.4f} final={gate['final']:.4f} reason={gate['reason']} atr_rank={gate['atr']} close_loc={gate['close_loc']} lower_wick={gate['lower_wick']}")
    streams=['signals_stream_long1','candidates_stream_long1','top5_stream_long1','trade_intents_stream_long1','exec_events_stream_long1']
    print('streams:', ' '.join(f'{s}={redis_xlen(s)}' for s in streams))
    # Compact machine-readable tail for later comparison.
    payload={'latest':latest and {k:v for k,v in latest.items() if k!='line'},'gate':gate and {k:v for k,v in gate.items() if k!='line'},'score20':{'n':len(scores),'min':min(scores) if scores else None,'mean':statistics.fmean(scores) if scores else None,'max':max(scores) if scores else None}}
    print('json:', json.dumps(payload, separators=(',',':'), allow_nan=False))

if __name__=='__main__': main()
