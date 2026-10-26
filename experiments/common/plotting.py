"""Figures for one experiment, written to ``experiments/results/<experiment>/``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402

from .figio import save_figure  # noqa: E402
from .runner import load_config, results_dir  # noqa: E402

RED = "#d62728"


def _trip_step(dir_tl: pd.DataFrame) -> Optional[int]:
    cut = dir_tl[dir_tl["agent_status"] != "ACTIVE"]
    return int(cut["step"].iloc[0]) - 1 if len(cut) else None


def _save(fig, out: Path, stem: str) -> None:
    save_figure(fig, out, stem)


def make_figures(exp_dir: Path) -> None:
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.2)
    cfg = load_config(exp_dir)
    plot = cfg["plot"]
    out = results_dir(exp_dir)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    window = int(summary["window"])
    drift_start = int(summary["drift_start_step"])
    base = pd.read_csv(out / "timeline_baseline.csv")
    dirr = pd.read_csv(out / "timeline_dir.csv")
    trip = _trip_step(dirr)
    title = cfg["experiment"]["title"]

    # Fig A: observed value and rolling window, Baseline vs DIR
    fig, axes = plt.subplots(2, 1, figsize=(9, 6.5), sharex=True, sharey=True)
    for ax, tl, label in ((axes[0], base, "Baseline (stateless gates only)"),
                          (axes[1], dirr, "DIR (DFID telemetry + SQL circuit breaker)")):
        ex = tl[tl["outcome"] == "EXECUTED"]
        ax.scatter(ex["step"], ex["metric"], s=9, alpha=0.5, color="#4c72b0", label=plot["metric_label"])
        roll = ex["metric"].rolling(window, min_periods=window).mean()
        ax.plot(ex["step"], roll, color="black", lw=1.6, label=f"rolling mean (W={window})")
        ax.axhline(cfg["monitor"]["threshold"], color="#ff7f0e", ls="--", lw=1.3, label=plot["threshold_label"])
        if plot.get("hard_limit") is not None:
            ax.axhline(plot["hard_limit"], color="#7f7f7f", ls=":", lw=1.5, label=plot["hard_limit_label"])
        ax.axvline(drift_start, color="#7f7f7f", ls="-.", lw=1.2, label="drift onset")
        if tl is dirr and trip is not None:
            ax.axvline(trip, color=RED, lw=2.2, label=f"circuit breaker cut-off (step {trip})")
        ax.set_title(label, loc="left")
        ax.set_ylabel(plot["metric_label"])
        ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8)
    axes[1].set_xlabel("iteration")
    fig.suptitle(title, y=1.0)
    fig.tight_layout()
    _save(fig, out, "fig_timeline")

    # Fig B: cumulative business impact
    fig, ax = plt.subplots(figsize=(8, 4.5))
    cb, cd = base["loss"].cumsum(), dirr["loss"].cumsum()
    ax.plot(base["step"], cb, color="#4c72b0", lw=2, label="Baseline")
    ax.plot(dirr["step"], cd, color="#2ca02c", lw=2, label="DIR")
    ax.fill_between(base["step"], cd, cb, color="#2ca02c", alpha=0.15, label="loss prevented")
    ax.axvline(drift_start, color="#7f7f7f", ls="-.", lw=1.2, label="drift onset")
    if trip is not None:
        ax.axvline(trip, color=RED, lw=2.2, label=f"circuit breaker cut-off (step {trip})")
    ax.set_xlabel("iteration")
    ax.set_ylabel(f"cumulative loss [{plot.get('loss_unit', '')}]")
    ax.set_title(f"Cumulative business impact: {title}", loc="left")
    ax.legend()
    fig.tight_layout()
    _save(fig, out, "fig_cumulative_loss")

    # Fig C: distributions over seeds
    per_seed = pd.read_csv(out / "metrics_per_seed.csv")
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    lat = per_seed["detection_latency_steps"].dropna()
    sns.histplot(lat, bins=min(15, max(5, lat.nunique())), color=RED, ax=axes[0])
    axes[0].set_xlabel("detection latency [steps after first bad decision]")
    axes[0].set_title(f"Detection latency (n={len(per_seed)} seeds)", loc="left")
    long = per_seed.melt(value_vars=["baseline_loss", "dir_loss"], var_name="group", value_name="loss")
    long["group"] = long["group"].map({"baseline_loss": "Baseline", "dir_loss": "DIR"})
    sns.boxplot(data=long, x="group", y="loss", hue="group", palette=["#4c72b0", "#2ca02c"], legend=False, ax=axes[1])
    axes[1].set_xlabel("")
    axes[1].set_ylabel(f"cumulative loss [{plot.get('loss_unit', '')}]")
    axes[1].set_title("Cumulative loss per seed", loc="left")
    fig.tight_layout()
    _save(fig, out, "fig_distributions")
