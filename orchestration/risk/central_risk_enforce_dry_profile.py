from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from orchestration.risk.central_risk_master import CentralRiskConfig, CentralRiskMaster

PROFILE_ID = "central_risk_enforce_dry.v1_h046_dd12_r06"
PROFILE_STAGE = "ENFORCE_DRY_RUN"
VALIDATED_STRATEGIES = ("LONG1", "SHORT1")
TARGET_STRATEGIES = (
    "LONG1", "LONG2", "LONG3", "LONG4",
    "SHORT1", "SHORT2", "SHORT3", "SHORT4",
)
BASE_REQUEST_BUDGET_RATIO = 0.50

# Production-matched LONG1+SHORT1 marked-notional replay, six LONG seeds.
VALIDATION = {
    "replay_scope": "LONG1+SHORT1_V50_marked_1m_6seed",
    "operational_headroom_multiplier": 0.92,
    "effective_normal_budget_ratio": 0.46,
    "return_mean_pct": 173.8221572575236,
    "return_min_pct": 159.0624549457155,
    "return_max_pct": 185.6969219846599,
    "pf_mean": 1.2684670363690775,
    "mtm_dd_mean_pct": -10.65741105006133,
    "mtm_dd_worst_pct": -11.00014279985474,
    "gross_max_ratio": 0.9521276172558235,
    "abs_net_max_ratio": 0.494416879704767,
    "breach_minutes_total": 0,
    "entry_freezes_total": 0,
    "cap_limited_total": 0,
    "rejected_total": 0,
}


def build_enforce_dry_config() -> CentralRiskConfig:
    """Validated two-engine dry-run enforcement profile; never live-authorized."""
    return CentralRiskConfig(
        dd_reduce_trigger=0.12,
        dd_recover_trigger=0.06,
        normal_multiplier=1.00,
        recovery_multiplier=0.70,
        reduced_multiplier=0.50,
        recovery_successes_required=2,
        operational_headroom_multiplier=0.92,
        max_open_positions=2,
        min_order_notional=10.0,
        max_gross_exposure_ratio=1.00,
        max_long_exposure_ratio=0.50,
        max_short_exposure_ratio=0.50,
        max_abs_net_exposure_ratio=0.50,
        max_symbol_exposure_ratio=0.50,
        exposure_warning_fraction=0.95,
        production_authorized=False,
    )


def build_enforce_dry_master() -> CentralRiskMaster:
    return CentralRiskMaster(build_enforce_dry_config())


def describe_profile() -> Dict[str, Any]:
    cfg = build_enforce_dry_config()
    production_ready, issues = cfg.validate_for_production()
    return {
        "schema_version": "central_risk_enforce_dry_profile.v1",
        "profile_id": PROFILE_ID,
        "stage": PROFILE_STAGE,
        "validated_strategies": list(VALIDATED_STRATEGIES),
        "target_strategies": list(TARGET_STRATEGIES),
        "base_request_budget_ratio": BASE_REQUEST_BUDGET_RATIO,
        "config": asdict(cfg),
        "validation": dict(VALIDATION),
        "production_ready": bool(production_ready),
        "production_issues": list(issues),
        "authority": {
            "dry_run_entry_veto": True,
            "dry_run_reservation": True,
            "portfolio_mtm_dd": True,
            "gross_exposure": True,
            "side_exposure": True,
            "abs_net_exposure": True,
            "symbol_exposure": True,
            "strategy_single_slot": True,
            "live_order_authority": False,
        },
        "notes": [
            "0.50 base request x 0.92 operational headroom = 0.46 normal budget.",
            "H046 was breach-free across six marked-notional LONG1+SHORT1 seeds.",
            "DD 10/5 materially reduced return without improving seed-1 max DD; 12/6 remains reserve protection.",
            "This profile must reject LIVE requests until a separately authorized production profile exists.",
        ],
    }
