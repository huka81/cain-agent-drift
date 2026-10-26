# Experiment 01: optimization drift (retention discounts)

**Scenario.** A retention agent offers discounts to subscribers who want to cancel. The stateless
gate only checks `discount <= 15%`.

**MockLLM.** Decisions 0-49: discount ~ N(8%, 1%). From decision 50 (drift injection):
discount ~ N(14.8%, 0.1%), capped at the 15% hard limit. Every decision passes the stateless gate.

**Business loss.** `max(0, discount - 8%) * MRR * 12 months`, MRR ~ N(50, 8) EUR.

**DIR circuit breaker.** Each executed decision is written to the audit log with its DFID. Every 5
decisions an asynchronous monitor runs a SQL rolling-window query (`AVG(discount)` over the last
W=20 executed decisions). If the average exceeds 10% the agent is set to `SUSPENDED`.

**Groups.** Baseline = stateless gate only. DIR = stateless gate + circuit breaker. Both groups use
identical inputs and identical agent randomness for each seed.

Run (from the repository root): `python experiments/01_drift_optimization_discount/run.py`
(`--seeds`, `--steps` override the config; `plot_results.py` redraws the figures).
Outputs go to `experiments/results/01_drift_optimization_discount/`: `summary.json`,
`metrics_per_seed.csv`, `timeline_*.csv` (first seed) and `fig_*.png/pdf`.
