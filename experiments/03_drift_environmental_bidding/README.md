# Experiment 03: environmental drift (ad bidding)

**Scenario.** A bidding agent bids market CPC + 0.02 USD, bounded by a 2.00 USD contract ceiling.
The value of a click (LTV) is 1.80 USD.

**MockLLM.** Market CPC is 1.20 USD until decision 50, then rises linearly to 1.98 USD over 80
decisions (noise N(0, 0.02)). The agent always follows the market, so every bid passes the gate.

**Business loss.** `max(0, bid - 1.80) * 100 clicks` per decision.

**DIR circuit breaker.** Every 5 decisions a SQL rolling-window query computes `AVG(bid)` over the
last W=10 executed decisions. If it exceeds the LTV the agent is set to `DEGRADED`: its bids are
capped at the LTV (safe fallback), so it loses its authority to overpay.

Run: `python experiments/03_drift_environmental_bidding/run.py`. Outputs:
`experiments/results/03_drift_environmental_bidding/`.
