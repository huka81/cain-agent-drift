"""B5 for experiment 02: the same rolling-window monitor, but over a signal without the context join.

The full monitor reads the policy-violation flag, which needs the proposal joined with the context
snapshot (ticket delay). B5 reads only the refund amount of the executed proposal. Its threshold is
fixed before any run as the midpoint of the analytic drift-free and drifted mean refund per decision.
Writes ``results/02_drift_semantic_refund_nojoin/``.
"""

import copy
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.engine import reset_db, run_trial  # noqa: E402
from common.metrics import pair_metrics, summarize  # noqa: E402
from common.runner import RESULTS_ROOT, load_config, load_scenario  # noqa: E402


def main() -> None:
    exp_dir = Path(__file__).resolve().parent
    cfg = copy.deepcopy(load_config(exp_dir))
    sim = cfg["simulation"]
    pre = (1 - sim["p_borderline"]) * sim["refund_compliant_mean_eur"]
    post = pre + sim["p_borderline"] * sim["p_emotional_given_borderline"] * sim["p_rationalise"] * sim["refund_drift_mean_eur"]
    cfg["monitor"]["signal"] = "refund_amount"
    cfg["monitor"]["threshold"] = round((pre + post) / 2, 2)
    out = RESULTS_ROOT / f"{exp_dir.name}_nojoin"
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / "audit.db"
    reset_db(db_path)

    per_seed = []
    for i in range(int(sim["seeds"])):
        scn = load_scenario(exp_dir, cfg)
        seed = int(sim["base_seed"]) + i
        base = run_trial(scn, "baseline", seed, int(sim["steps"]), db_path=db_path)
        dirr = run_trial(scn, "dir", seed, int(sim["steps"]), db_path=db_path)
        per_seed.append(pair_metrics(base, dirr))

    summary = summarize(per_seed)
    summary.update(experiment=cfg["experiment"]["id"] + "_nojoin", window=cfg["monitor"]["window"],
                   threshold=cfg["monitor"]["threshold"], drift_free_mean=pre, drifted_mean=post)
    pd.DataFrame(per_seed).to_csv(out / "metrics_per_seed.csv", index=False)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"threshold={summary['threshold']} (drift-free mean {pre:.2f}, drifted mean {post:.2f})")
    print("detection (true) rate:", summary["detection_rate"], "| false-positive rate:", summary["false_positive_rate"])
    for key in ("detection_latency_steps", "bad_decisions_before_cutoff", "dir_loss", "loss_prevented_pct"):
        print(key, summary[key])


if __name__ == "__main__":
    main()
