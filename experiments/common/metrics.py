"""Evaluation metrics: Detection Latency and Cumulative Business Impact."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from .engine import TrialResult


def _first_bad_step(trial: TrialResult) -> Optional[int]:
    for r in trial.timeline:
        if r["outcome"] == "EXECUTED" and r["bad"]:
            return int(r["step"])
    return None


def pair_metrics(baseline: TrialResult, dir_: TrialResult) -> Dict[str, Any]:
    base_loss = float(sum(r["loss"] for r in baseline.timeline))
    dir_loss = float(sum(r["loss"] for r in dir_.timeline))
    first_bad = _first_bad_step(baseline)
    trip = dir_.trip_step
    detected = trip is not None
    false_positive = detected and (first_bad is None or trip < first_bad)
    latency_steps = (trip - first_bad + 1) if (detected and not false_positive) else None
    return {
        "seed": baseline.seed,
        "first_bad_step": first_bad,
        "trip_step": trip,
        "detected": detected,
        "false_positive": bool(false_positive),
        "detection_latency_steps": latency_steps,
        "bad_decisions_baseline": sum(1 for r in baseline.timeline if r["outcome"] == "EXECUTED" and r["bad"]),
        "bad_decisions_before_cutoff": sum(1 for r in dir_.timeline if r["outcome"] == "EXECUTED" and r["bad"]),
        "baseline_loss": base_loss,
        "dir_loss": dir_loss,
        "loss_prevented": base_loss - dir_loss,
        "loss_prevented_pct": 100.0 * (base_loss - dir_loss) / base_loss if base_loss > 0 else 0.0,
    }


def _bootstrap_ci(values: Sequence[float], n_boot: int = 2000) -> List[float]:
    arr = np.asarray(values, dtype=float)
    rng = np.random.default_rng(0)
    means = rng.choice(arr, size=(n_boot, arr.size), replace=True).mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def _stat(values: Sequence[Optional[float]]) -> Dict[str, Any]:
    v = [float(x) for x in values if x is not None]
    if not v:
        return {"n": 0, "mean": None, "std": None, "ci95": None, "min": None, "max": None}
    return {
        "n": len(v), "mean": float(np.mean(v)), "std": float(np.std(v, ddof=1)) if len(v) > 1 else 0.0,
        "ci95": _bootstrap_ci(v), "min": float(min(v)), "max": float(max(v)),
    }


def summarize(per_seed: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(per_seed)
    return {
        "n_seeds": n,
        "detection_rate": sum(1 for m in per_seed if m["detected"] and not m["false_positive"]) / n,
        "false_positive_rate": sum(1 for m in per_seed if m["false_positive"]) / n,
        "detection_latency_steps": _stat([m["detection_latency_steps"] for m in per_seed]),
        "bad_decisions_before_cutoff": _stat([m["bad_decisions_before_cutoff"] for m in per_seed]),
        "bad_decisions_baseline": _stat([m["bad_decisions_baseline"] for m in per_seed]),
        "baseline_loss": _stat([m["baseline_loss"] for m in per_seed]),
        "dir_loss": _stat([m["dir_loss"] for m in per_seed]),
        "loss_prevented": _stat([m["loss_prevented"] for m in per_seed]),
        "loss_prevented_pct": _stat([m["loss_prevented_pct"] for m in per_seed]),
    }
