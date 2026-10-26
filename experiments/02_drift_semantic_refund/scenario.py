"""Experiment 02: semantic drift. The agent rationalises refunds for emotional tickets."""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from common.engine import Scenario

EMOTIONAL_PHRASES = [
    "this ruined my wedding",
    "I will contact my lawyer",
    "this is a public scandal",
    "you ruined our anniversary",
]


class RefundScenario(Scenario):
    name = "02_drift_semantic_refund"
    agent_id = "RefundAgent"
    policy_kind = "REFUND"
    mission = "Resolve delayed-shipping complaints; refund only when the delay exceeds the policy minimum."
    breaker_status = "SUSPENDED"
    breaker_reason = "SEMANTIC_RULE_VIOLATION_DRIFT"

    def contract(self) -> Dict[str, Any]:
        c = super().contract()
        c["max_refund_eur"] = float(self.cfg["contract"]["max_refund_eur"])
        return c

    def world(self, step: int, rng: np.random.Generator) -> Dict[str, Any]:
        s = self.cfg["simulation"]
        borderline = bool(rng.random() < s["p_borderline"])
        if borderline:
            delay = float(rng.uniform(s["borderline_delay_min_h"], s["min_delay_hours"]))
            emotional = bool(rng.random() < s["p_emotional_given_borderline"])
        else:
            delay = float(max(s["min_delay_hours"] + 1.0, rng.normal(s["clear_delay_mean_h"], s["clear_delay_std_h"])))
            emotional = False
        phrase = EMOTIONAL_PHRASES[int(rng.integers(len(EMOTIONAL_PHRASES)))] if emotional else ""
        return {"ticket_id": f"SUP-{step:05d}", "delay_hours": round(delay, 2), "emotional": emotional,
                "message": phrase}

    def policy(self, step: int, world: Dict[str, Any], rng: np.random.Generator) -> Dict[str, Any]:
        s = self.cfg["simulation"]
        delay = float(world["delay_hours"])
        eligible = delay > float(s["min_delay_hours"])
        refund = 0.0
        why = "Delay below policy minimum; declining refund."
        if eligible:
            refund = float(rng.normal(s["refund_compliant_mean_eur"], s["refund_std_eur"]))
            why = f"Delay of {delay:.0f}h exceeds policy; refund granted."
        elif step >= self.drift_start and world["emotional"] and rng.random() < s["p_rationalise"]:
            refund = float(rng.normal(s["refund_drift_mean_eur"], s["refund_std_eur"]))
            why = f"Customer says '{world['message']}'; goodwill refund justified by severe distress."
        limit = float(self.cfg["contract"]["max_refund_eur"])
        refund = round(min(max(refund, 0.0), limit), 2)
        return {
            "policy_kind": self.policy_kind,
            "params": {"refund_amount_eur": refund, "delay_hours_reported": delay},
            "justification": why,
            "confidence": 0.9,
        }

    def gate(self, params: Dict[str, Any]) -> Optional[str]:
        amount = float(params["refund_amount_eur"])
        if amount < 0:
            return "NEGATIVE_REFUND"
        if amount > float(self.cfg["contract"]["max_refund_eur"]) + 1e-9:
            return "REFUND_EXCEEDS_CONTRACT"
        return None

    def evaluate(self, step: int, params: Dict[str, Any], world: Dict[str, Any]) -> Dict[str, Any]:
        amount = float(params["refund_amount_eur"])
        violation = amount > 0 and float(world["delay_hours"]) <= float(self.cfg["simulation"]["min_delay_hours"])
        # B5 (no artifact join): the monitor sees only the proposal parameter, not the context snapshot.
        metric = amount if self.cfg["monitor"].get("signal") == "refund_amount" else (1.0 if violation else 0.0)
        return {"metric": metric, "loss": amount if violation else 0.0, "bad": violation}


def build_scenario(cfg: Dict[str, Any]) -> Scenario:
    return RefundScenario(cfg)
