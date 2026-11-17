"""LONG1+SHORT1 shared risk stage21 *offline* simulation.

This adapter binds snapshot evidence and a central risk decision, but it is
NOT a live broker proof provider, exchange writer, or trade authorization.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal,InvalidOperation
from typing import Any,Mapping

@dataclass(frozen=True)
class JointRiskCandidate:
    state:str
    reason:str
    max_notional:str="0"
    live_order_authorized:bool=False

def _positive(value:Any)->Decimal:
    val=Decimal(str(value))
    if not val.is_finite() or val<=0:raise ValueError("invalid amount")
    return val

def evaluate_joint_candidate(*, two_accounts:Mapping[str,Any],
    shared_identity:Mapping[str,Any]|None,
    portfolio_snapshot:Mapping[str,Any]|None,
    central_decision:Any,
    expected_epoch:int,
    strategy_id:str,
    symbol:str,
    side:str,
    now_ms:int,
    max_age_ms:int=5000)->JointRiskCandidate:
    def reject(reason:str):
        return JointRiskCandidate("REJECT",reason)
    if not isinstance(two_accounts,Mapping) or set(two_accounts)!={"LONG1","SHORT1"}:
        return reject("both_accounts_required")
    if not isinstance(shared_identity,Mapping) or shared_identity.get("verified") is not True:
        return reject("shared_account_identity_not_verified")
    account_id=shared_identity.get("account_id")
    if not isinstance(account_id,str) or not account_id:
        return reject("shared_account_identity_missing")
    if any(two_accounts.get(b)!=account_id for b in ("LONG1","SHORT1")):
        return reject("different_account_domain")
    if not isinstance(portfolio_snapshot,Mapping):
        return reject("portfolio_snapshot_missing")
    if portfolio_snapshot.get("account_id")!=account_id:
        return reject("snapshot_account_domain_mismatch")
    if portfolio_snapshot.get("complete") is not True:
        return reject("portfolio_not_complete")
    if portfolio_snapshot.get("positions_and_orders_verified") is not True:
        return reject("positions_or_orders_not_verified")
    if portfolio_snapshot.get("source_authenticated") is not True:
        return reject("source_not_authenticated")
    epoch=portfolio_snapshot.get("epoch")
    if type(epoch) is not int or epoch!=expected_epoch or epoch<=0:
        return reject("wrong_epoch")
    ms=portfolio_snapshot.get("timestamp_ms")
    if type(ms) is not int or now_ms<ms-1000 or now_ms-ms>max_age_ms:
        return reject("snapshot_not_fresh")
    if portfolio_snapshot.get("unknown_intents"):
        return reject("unresolved_intents")
    if central_decision is None:
        return reject("missing_central_decision")
    if getattr(central_decision,"state","")!="READY":
        return reject("central_rejected")
    if getattr(central_decision,"production_ready",False) is not True:
        return reject("central_not_production_authorized")
    if (getattr(central_decision,"strategy_id","")!=strategy_id or
        getattr(central_decision,"symbol","")!=symbol or
        getattr(central_decision,"side","")!=side):
        return reject("central_identity_mismatch")
    try:
        notional=_positive(getattr(central_decision,"allowed_notional",None))
        available=_positive(portfolio_snapshot.get("available_margin"))
    except (ValueError,InvalidOperation,TypeError):
        return reject("invalid_notional_or_margin")
    if notional>available:
        return reject("insufficient_available_margin")
    # Candidate ONLY: actual live needs independent broker attestation,
    # atomic reservation, order-ID and final-safety check in one runtime path.
    return JointRiskCandidate("READY_CANDIDATE_ONLY","simulation_passed",str(notional),False)
