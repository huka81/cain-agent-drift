"""Experiment 03: environmental drift. Market CPC rises above the value of a click (LTV)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from common.engine import Scenario


class BiddingScenario(Scenario):
    name = "03_drift_environmental_bidding"
    agent_id = "BiddingAgent"
    policy_kind = "cpc_bid"
    mission = "Keep top-3 ad placement by bidding slightly above the market CPC, within the contract ceiling."
    breaker_status = "DEGRADED"
    breaker_reason = "NEGATIVE_ROI_ENVIRONMENTAL_DRIFT"

    def contract(self) -> Dict[str, Any]:
        c = super().contract()
        c["max_cpc_usd"] = float(self.cfg["contract"]["max_cpc_usd"])
        return c

    def world(self, step: int, rng: np.random.Generator) -> Dict[str, Any]:
        s = self.cfg["simulation"]
        t = min(1.0, max(0.0, (step - self.drift_start + 1) / float(s["ramp_steps"])))
        cpc = s["market_cpc_start"] + (s["market_cpc_end"] - s["market_cpc_start"]) * t
        cpc += float(rng.normal(0.0, s["market_cpc_noise"]))
        return {"cycle_id": step, "market_cpc_to_win": round(max(0.05, cpc), 4)}

    def policy(self, step: int, world: Dict[str, Any], rng: np.random.Generator) -> Dict[str, Any]:
        ceiling = float(self.cfg["contract"]["max_cpc_usd"])
        bid = min(ceiling, float(world["market_cpc_to_win"]) + float(self.cfg["simulation"]["bid_margin"]))
        return {
            "policy_kind": self.policy_kind,
            "params": {"cpc_bid_usd": round(bid, 4)},
            "justification": f"Bid {bid:.2f} USD to stay in top-3 (market CPC {world['market_cpc_to_win']:.2f}).",
            "confidence": 0.9,
        }

    def gate(self, params: Dict[str, Any]) -> Optional[str]:
        bid = float(params["cpc_bid_usd"])
        if bid <= 0:
            return "NON_POSITIVE_BID"
        if bid > float(self.cfg["contract"]["max_cpc_usd"]) + 1e-9:
            return "CPC_EXCEEDS_CONTRACT"
        return None

    def degrade(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """DEGRADED mode: bids are capped at the value of a click (LTV)."""
        out = dict(params)
        out["cpc_bid_usd"] = min(float(params["cpc_bid_usd"]), float(self.cfg["monitor"]["threshold"]))
        return out

    def evaluate(self, step: int, params: Dict[str, Any], world: Dict[str, Any]) -> Dict[str, Any]:
        bid = float(params["cpc_bid_usd"])
        ltv = float(self.cfg["monitor"]["threshold"])
        clicks = float(self.cfg["simulation"]["clicks_per_cycle"])
        loss = max(0.0, bid - ltv) * clicks
        return {"metric": bid, "loss": loss, "bad": bid > ltv + 1e-9}


def build_scenario(cfg: Dict[str, Any]) -> Scenario:
    return BiddingScenario(cfg)
