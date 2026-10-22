#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REG=ROOT/'config/strategy_isolation_registry.json'

def norm(s: str) -> str:
    return ''.join(ch for ch in str(s).lower() if ch.isalnum())

def main() -> int:
    obj=json.loads(REG.read_text())
    strategies=obj.get('strategies') or {}
    seen={}
    errors=[]
    for sid,cfg in strategies.items():
        token=norm(sid)
        if not token:
            errors.append(f'{sid}: invalid strategy id')
            continue
        for section in ('redis_owned','pid_files','logs','services'):
            for raw in cfg.get(section) or []:
                val=str(raw).strip()
                if not val:
                    errors.append(f'{sid}:{section}: empty identifier')
                    continue
                if token not in norm(val):
                    errors.append(f'{sid}:{section}: strategy id missing from {val!r}')
                prior=seen.get(val)
                if prior and prior != sid:
                    errors.append(f'collision: {val!r} owned by {prior} and {sid}')
                seen[val]=sid
    if errors:
        print('STRATEGY_ISOLATION_FAIL')
        for e in errors: print(' -',e)
        return 1
    print(f'STRATEGY_ISOLATION_OK strategies={len(strategies)} owned_identifiers={len(seen)} shared_patterns={len((obj.get("shared") or {}).get("redis_patterns") or [])}')
    for sid,cfg in strategies.items():
        print(f' {sid}: side={cfg.get("side")} symbol={cfg.get("symbol")} redis={len(cfg.get("redis_owned") or [])} services={len(cfg.get("services") or [])}')
    return 0

if __name__=='__main__': raise SystemExit(main())
