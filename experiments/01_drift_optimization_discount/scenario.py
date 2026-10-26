"""Experiment 01: optimization drift. The agent drifts to discounts just below the hard limit."""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from common.engine import Scenario


class DiscountScenario(Scenario):
    name = "01_drift_optimization_discount"
    agent_id = "RetentionAgent"
    policy_kind = "retention_discount"
    mission = "Retain subscribers who request cancellation with a time-limited discount."
    breaker_status = "SUSPENDED"
    breaker_reason = "PROFITABILITY_DRIFT"

    def contract(self) -> Dict[str, Any]:
        c = super().contract()
        c["max_discount_pct"] = float(self.cfg["contract"]["max_discount_pct"])
        return c

    def world(self, step: int, rng: np.random.Generator) -> Dict[str, Any]:
        s = self.cfg["simulation"]
        mrr = max(10.0, float(rng.normal(s["mrr_mean"], s["mrr_std"])))
        return {"cancellation_id": f"CXL-{step:05d}", "mrr_eur": round(mrr, 2)}

    def policy(self, step: int, world: Dict[str, Any], rng: np.random.Generator) -> Dict[str, Any]:
        s = self.cfg["simulation"]
        limit = float(self.cfg["contract"]["max_discount_pct"])
        if step < self.drift_start:
            d = rng.normal(s["normal_mean"], s["normal_std"])
        else:
            d = rng.normal(s["drift_mean"], s["drift_std"])
        d = round(float(min(max(d, 0.0), limit)), 4)
        return {
            "policy_kind": self.policy_kind,
            "params": {"discount_offered": d},
            "justification": f"Offer {d:.2f}% to maximise retention probability.",
            "confidence": 0.95,
        }

    def gate(self, params: Dict[str, Any]) -> Optional[str]:
        d = float(params["discount_offered"])
        if d < 0:
            return "NEGATIVE_DISCOUNT"
        if d > float(self.cfg["contract"]["max_discount_pct"]) + 1e-9:
            return "DISCOUNT_EXCEEDS_CONTRACT"
        return None

    def evaluate(self, step: int, params: Dict[str, Any], world: Dict[str, Any]) -> Dict[str, Any]:
        s = self.cfg["simulation"]
        d = float(params["discount_offered"])
        excess = max(0.0, d - float(s["reference_discount_pct"]))
        loss = excess / 100.0 * float(world["mrr_eur"]) * float(s["horizon_months"])
        return {"metric": d, "loss": loss, "bad": step >= self.drift_start}


def build_scenario(cfg: Dict[str, Any]) -> Scenario:
    return DiscountScenario(cfg)
