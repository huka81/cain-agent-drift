# Replication package: structured decision telemetry for runtime governance of agent drift

Three controlled, synthetic experiments for a preliminary feasibility evaluation. Each shows that a
stateless validation gate passes a drifting trajectory when every decision is individually within
limits, and that a monitor over relational decision lineage (decisions keyed by a DFID in a SQL audit
log) can detect the pattern and change the agent's execution authority through a registry.

The evaluation is a demonstration on a MockLLM with hand-set thresholds. It is not a comparison with
other monitoring systems and does not test real LLMs.

| Experiment (directory) | Drift scenario | Stateless gate | Monitored signal and trip condition | Action |
|---|---|---|---|---|
| `01_drift_optimization_discount` | optimization | discount <= 15% | discount of the executed decision; mean over W=20 > 10% | `SUSPENDED` |
| `02_drift_semantic_refund` | contextual policy violation | refund <= 50 EUR | 1 if refund > 0 and delay <= 48 h, else 0; mean over W=20 > 0.15 | `SUSPENDED` |
| `03_drift_environmental_bidding` | environmental | bid <= 2.00 USD | executed bid in USD (not the market CPC); mean over W=10 > 1.80 (= LTV) | `DEGRADED` (bids capped at LTV) |

Exp. 02 tests a rise in the frequency of an event type computed from structured fields (ticket delay,
refund amount), not understanding of free text; the directory name keeps the original label "semantic".

Each experiment runs two trials per seed on identical inputs: **Baseline** (stateless gate only) and
**DIR** (same gate plus the audit log, the asynchronous monitor and the circuit breaker). Default: 200
steps, 30 seeds (1..30), drift onset at step 50, monitor polling every 5 decisions. The agent is a
deterministic **MockLLM** sampling from configured distributions: no API keys, no network, and random
streams depend only on (seed, step), so reruns give identical result files.

## Setup and reproduce

Run everything from the repository root (Python 3.12 was used).

```
pip install -r requirements.txt
python experiments/run_all.py                   # all three experiments, 30 seeds, with figures
python experiments/01_drift_optimization_discount/run.py   # one experiment
python experiments/02_drift_semantic_refund/run_no_join.py # B5 ablation (see below)
python experiments/01_drift_optimization_discount/plot_results.py  # redraw figures from stored results
```

`run.py` (and `run_all.py`, which forwards its arguments to every `run.py`) accepts `--seeds N`,
`--steps N` and `--no-plot`. **Results are overwritten in place**, so a run with `--seeds 5` replaces
the 30-seed results in `experiments/results/<experiment>/`; rerun without arguments to restore them.

### B5: no-join ablation (Exp. 02 only)

`02_drift_semantic_refund/run_no_join.py` uses the same monitor, window and polling, but the signal is
the refund amount of the executed proposal, without joining the context snapshot (ticket delay) that
defines a violation. The threshold is set before the run as the midpoint of the analytic drift-free and
drifted mean refund per decision (25.8 EUR). It is not part of `run_all.py` and writes no figures.

## Where results are written

`experiments/results/<experiment>/` (created on the first run):

| File | Content |
|---|---|
| `summary.json` | mean, std, 95% bootstrap CI (2000 resamples), min, max of every metric over seeds; detection and false-positive rate |
| `metrics_per_seed.csv` | one row per seed: first bad step, trip step, latency, bad decisions, losses |
| `timeline_baseline.csv`, `timeline_dir.csv` | step-level trace of the first seed only (seed 1) |
| `fig_timeline`, `fig_cumulative_loss`, `fig_distributions` (`.png`, `.pdf`) | figures; the timeline and cumulative-loss figures show seed 1, the distributions all seeds |
| `audit.db` | SQLite audit database of the whole run, all trials (see below); git-ignored |

The B5 ablation writes `summary.json`, `metrics_per_seed.csv` and `audit.db` to
`experiments/results/02_drift_semantic_refund_nojoin/`.

## The audit database

Each experiment run writes one SQLite audit database, kept next to the figures:
`experiments/results/<experiment>/audit.db` (about 10 MB). All 60 trials of the run (30 seeds, Baseline
and DIR) share it and stay separate through their own agent id (`<agent>:<mode>:<seed>`), their own
`run_id` (`<experiment>:<mode>:<seed>`, stored in `detail_json`) and DFIDs derived from
(experiment, mode, seed, step), so each DFID is unique in the file. The schema is
`src/dir_core/storage/schema.sql`; the engine opens the file with `synchronous=OFF` and
`journal_mode=MEMORY` for speed. A rerun deletes and recreates the file. `*.db` is listed in
`.gitignore`, so the databases are not committed. Calling `run_trial` without `db_path` falls back to a
throw-away database in a temporary `dir_exp_*` directory, deleted after the trial.

The monitor reads the relation `decision_audit_events`, where each executed decision is an event keyed
by its DFID with the monitored value in `detail_json`:

```sql
SELECT n, value FROM (
  SELECT id,
         COUNT(*) OVER w AS n,
         AVG(CAST(json_extract(detail_json, '$.metric') AS REAL)) OVER w AS value
  FROM decision_audit_events
  WHERE event_type = 'DECISION_EXECUTED' AND json_extract(detail_json, '$.run_id') = ?
  WINDOW w AS (ORDER BY id ROWS BETWEEN ? PRECEDING AND CURRENT ROW))   -- ? = W-1
ORDER BY id DESC LIMIT 1
```

This is a SQL window function: for every executed decision of the run it returns the window size `n` and
the windowed mean over the last `W` executed decisions; the newest row is the current state (without
`LIMIT 1` it returns the whole series, usable for audit). It needs SQLite 3.25 or newer (3.45 was used).
The breaker trips when `n >= W` and `value > threshold`, then calls `AgentRegistry.set_agent_status` and
records a `CIRCUIT_BREAKER_TRIPPED` event (with the window value and threshold). The experiments therefore
use one audit relation, not the full multi-relation lineage model, and the monitor runs as a
synchronous poll between steps. Example inspection:

```sql
-- sqlite3 experiments/results/01_drift_optimization_discount/audit.db
SELECT json_extract(detail_json, '$.run_id') AS run, event_type, COUNT(*)
FROM decision_audit_events GROUP BY run, event_type;
```

## Metrics

- **Detection latency:** `trip step - first bad step + 1`, in decisions, where the first bad step is
  the first executed bad decision of the Baseline trial (in Exp. 03 a bid above the LTV, 56-61 steps
  after onset, not the drift onset itself). Reported for true detections only.
- **Bad decisions before cut-off:** bad decisions executed in the DIR trial.
- **Loss prevented:** `(Baseline loss - DIR loss) / Baseline loss` per seed, gross: losses of executed
  decisions only. After a suspension the agent yields neither loss nor value; the value of legitimate
  decisions blocked, and the cost of false suspensions, are not modelled.
- **Detection rate / false-positive rate:** the breaker tripped / tripped before the first bad decision.

Reference results with the default configuration (30 seeds): latency 10.0, 18.0 and 7.3 decisions,
loss prevented 91.6%, 85.7% and 98.6% for Exp. 01, 02 and 03, detected in 30/30 seeds with no
false positives.

## Layout

- `src/dir_core/`: DIR runtime primitives. The experiments use the agent registry, the stateless
  validation (`dim.py`), the storage layer with the SQLite audit log (`storage/`) and the proposal types.
- `experiments/common/`: `engine.py` (trial loop, monitor query), `mock_llm.py`, `metrics.py`,
  `runner.py` (driver, results writing), `plotting.py`, `figio.py`.
- `experiments/0X_*/`: `config.yaml` (all parameters), `scenario.py` (world, agent distributions, gate,
  loss, degradation rule), `run.py`, `plot_results.py`, `README.md`.
- `experiments/experiments-description.md`: full technical description of the experiments.
- `paper/`: the CAIN short paper (`cain_shortpaper_agent_drift.tex`, built with `convert_to_pdf.cmd`);
  `paper/figures/make_paper_figures.py` redraws the paper figures from `experiments/results/`.

There is no automated test suite in this package.