"""Experiment driver: runs Baseline and DIR for many seeds, stores results, logs metrics."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import yaml

from .engine import reset_db, run_trial
from .metrics import pair_metrics, summarize

logger = logging.getLogger("dir.experiment")
RESULTS_ROOT = Path(__file__).resolve().parents[1] / "results"


def load_config(exp_dir: Path) -> Dict[str, Any]:
    with open(exp_dir / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_scenario(exp_dir: Path, cfg: Dict[str, Any]):
    spec = importlib.util.spec_from_file_location(f"scenario_{exp_dir.name}", exp_dir / "scenario.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.build_scenario(cfg)


def results_dir(exp_dir: Path) -> Path:
    return RESULTS_ROOT / exp_dir.name


def _fmt(stat: Dict[str, Any], digits: int = 2) -> str:
    if stat["mean"] is None:
        return "n/a"
    lo, hi = stat["ci95"]
    return f"{stat['mean']:.{digits}f} (95% CI {lo:.{digits}f}..{hi:.{digits}f})"


def run_experiment(exp_dir: Path, n_seeds: int | None = None, steps: int | None = None) -> Dict[str, Any]:
    cfg = load_config(exp_dir)
    sim = cfg["simulation"]
    n_seeds = int(n_seeds if n_seeds is not None else sim["seeds"])
    steps = int(steps if steps is not None else sim["steps"])
    base_seed = int(sim["base_seed"])
    out = results_dir(exp_dir)
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / "audit.db"
    reset_db(db_path)  # one audit database per experiment run, shared by all trials

    per_seed = []
    for i in range(n_seeds):
        seed = base_seed + i
        scn = load_scenario(exp_dir, cfg)
        base = run_trial(scn, "baseline", seed, steps, db_path=db_path)
        dirr = run_trial(scn, "dir", seed, steps, db_path=db_path)
        per_seed.append(pair_metrics(base, dirr))
        if i == 0:
            pd.DataFrame(base.timeline).to_csv(out / "timeline_baseline.csv", index=False)
            pd.DataFrame(dirr.timeline).to_csv(out / "timeline_dir.csv", index=False)

    summary = summarize(per_seed)
    summary.update(experiment=cfg["experiment"]["id"], steps=steps, window=cfg["monitor"]["window"],
                   poll_interval=cfg["monitor"].get("poll_interval", 1),
                   drift_start_step=sim["drift_start_step"], representative_seed=base_seed)
    pd.DataFrame(per_seed).to_csv(out / "metrics_per_seed.csv", index=False)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log_summary(cfg, summary)
    return summary


def log_summary(cfg: Dict[str, Any], s: Dict[str, Any]) -> None:
    logger.info("=" * 72)
    logger.info("Experiment %s | steps=%d W=%d poll=%d seeds=%d", s["experiment"], s["steps"],
                s["window"], s["poll_interval"], s["n_seeds"])
    logger.info("Detection rate: %.1f%% | false-positive rate: %.1f%%",
                100 * s["detection_rate"], 100 * s["false_positive_rate"])
    logger.info("Detection Latency (steps after first bad decision): %s", _fmt(s["detection_latency_steps"], 1))
    logger.info("Bad decisions executed before cutoff: %s  (Baseline: %s)",
                _fmt(s["bad_decisions_before_cutoff"], 1), _fmt(s["bad_decisions_baseline"], 1))
    unit = cfg["plot"].get("loss_unit", "")
    logger.info("Cumulative loss, Baseline: %s %s", _fmt(s["baseline_loss"]), unit)
    logger.info("Cumulative loss, DIR:      %s %s", _fmt(s["dir_loss"]), unit)
    logger.info("Loss prevented by DIR:     %s %s  = %s%%", _fmt(s["loss_prevented"]), unit,
                _fmt(s["loss_prevented_pct"], 1))
    logger.info("=" * 72)


def main(exp_file: str) -> None:
    exp_dir = Path(exp_file).resolve().parent
    parser = argparse.ArgumentParser(description=f"Run experiment {exp_dir.name}")
    parser.add_argument("--seeds", type=int, default=None, help="number of seeds (default: config)")
    parser.add_argument("--steps", type=int, default=None, help="steps per run (default: config)")
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout)
    logger.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(h)
    logger.propagate = False
    run_experiment(exp_dir, args.seeds, args.steps)
    if not args.no_plot:
        from .plotting import make_figures

        make_figures(exp_dir)
