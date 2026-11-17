"""Pure fail-closed pre-order release proposal. NOT installed into live executor.

The snapshot/proof must come from an independently authoritative, consistently
versioned exchange+central risk coordinator. A Redis count alone is not proof.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping

@dataclass(frozen=True)
class RiskRelease:
    allow: bool
    reason: str

def authorize_long_open(
    *, local_gate: bool, central_decision: Any,
    authoritative_snapshot: Mapping[str, Any] | None,
    expected_symbol: str, expected_side: str = "long",
    expected_strategy: str = "LONG1",
    expected_epoch: str | None = None,
) -> RiskRelease:
    if not local_gate:
        return RiskRelease(False,"local_execution_risk_rejected")
    if not isinstance(authoritative_snapshot, Mapping):
        return RiskRelease(False,"authoritative_positions_unknown")
    if authoritative_snapshot.get("complete") is not True:
        return RiskRelease(False,"authoritative_positions_incomplete")
    if authoritative_snapshot.get("fresh") is not True:
        return RiskRelease(False,"authoritative_positions_stale")
    epoch=authoritative_snapshot.get("epoch")
    if not isinstance(epoch,str) or not epoch:
        return RiskRelease(False,"authoritative_epoch_missing")
    if expected_epoch is not None and epoch!=expected_epoch:
        return RiskRelease(False,"authoritative_epoch_mismatch")
    pos=authoritative_snapshot.get("positions")
    if not isinstance(pos,list):
        return RiskRelease(False,"authoritative_positions_invalid")
    if any(not isinstance(row,Mapping) or not all(k in row for k in ("strategy_id","symbol","side","notional")) for row in pos):
        return RiskRelease(False,"authoritative_positions_invalid")
    if central_decision is None:
        return RiskRelease(False,"central_decision_unavailable")
    if getattr(central_decision,"production_ready",False) is not True:
        return RiskRelease(False,"central_production_not_authorized")
    if getattr(central_decision,"state","")!="READY":
        return RiskRelease(False,"central_rejected")
    if not isinstance(getattr(central_decision,"allowed_notional",None),(float,int)) or central_decision.allowed_notional<=0:
        return RiskRelease(False,"central_invalid_notional")
    expected=(expected_strategy.upper(),expected_symbol.upper(),expected_side.lower())
    got=(str(getattr(central_decision,"strategy_id","")).upper(),
         str(getattr(central_decision,"symbol","")).upper(),
         str(getattr(central_decision,"side","")).lower())
    if got!=expected:
        return RiskRelease(False,"central_decision_identity_mismatch")
    # Still not sufficient for actual atomic reservation, order lifecycle,
    # Binance fill/reconciliation or stop availability.
    return RiskRelease(True,"risk_release_candidate_only")
