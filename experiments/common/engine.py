"""Simulation engine: one trial = one agent, N steps, one mode (baseline | dir).

Baseline: agent -> stateless gate -> execution.
DIR:      same path, plus every outcome is written to a relational audit log keyed by DFID and
          an asynchronous monitor polls a SQL rolling window over that log. When the window
          aggregate crosses the threshold the circuit breaker changes the agent status
          (SUSPENDED / DEGRADED) and removes its execution authority.
Both modes use the DIR audit store so that the only difference is the circuit breaker. All trials of
one experiment run share one SQLite audit database, ``results/<experiment>/audit.db``.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dir_core import PolicyProposal  # noqa: E402
from dir_core.agent_registry import AgentRegistry  # noqa: E402
from dir_core.data_types import ValidationVerdict  # noqa: E402
from dir_core.dim import validate_proposal  # noqa: E402
from dir_core.storage import SqliteConnectionOptions, sqlite_storage  # noqa: E402

from .mock_llm import MockLLM  # noqa: E402

MODES = ("baseline", "dir")
_EPHEMERAL_STORAGE_OPTIONS = SqliteConnectionOptions(
    synchronous="OFF",
    journal_mode="MEMORY",
)


class Scenario:
    """Experiment definition. Subclasses implement the domain-specific parts."""

    name = "scenario"
    agent_id = "Agent"
    policy_kind = "policy"
    mission = ""
    breaker_status = "SUSPENDED"
    breaker_reason = "SEMANTIC_DRIFT"
    metric_label = "metric"
    threshold_label = "threshold"
    loss_label = "business loss"

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg
        self.drift_start = int(cfg["simulation"]["drift_start_step"])

    @property
    def threshold(self) -> float:
        return float(self.cfg["monitor"]["threshold"])

    def contract(self) -> Dict[str, Any]:
        return {"mission": self.mission, "allowed_policy_types": [self.policy_kind]}

    def world(self, step: int, rng: np.random.Generator) -> Dict[str, Any]:
        raise NotImplementedError

    def policy(self, step: int, world: Dict[str, Any], rng: np.random.Generator) -> Dict[str, Any]:
        raise NotImplementedError

    def gate(self, params: Dict[str, Any]) -> Optional[str]:
        """Stateless hard limit; returns a rejection reason or None."""
        raise NotImplementedError

    def evaluate(self, step: int, params: Dict[str, Any], world: Dict[str, Any]) -> Dict[str, Any]:
        """Returns ``metric`` (monitored value), ``loss`` (business loss) and ``bad`` (bool)."""
        raise NotImplementedError

    def degrade(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Safe fallback applied while the agent is DEGRADED."""
        return params


@dataclass
class TrialResult:
    mode: str
    seed: int
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    trip_step: Optional[int] = None


def dfid_for(name: str, seed: int, step: int, mode: str = "") -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"{name}/{mode}/{seed}/{step}"))


def reset_db(db_path: Path) -> None:
    """Delete a previous audit database (and SQLite side files) before a new experiment run."""
    for p in (str(db_path), f"{db_path}-journal", f"{db_path}-wal", f"{db_path}-shm"):
        if os.path.exists(p):
            os.remove(p)


def rolling_window_query(db_path: str, run_id: str, window: int) -> Dict[str, Any]:
    """Asynchronous monitor query: aggregate of the last ``window`` executed decisions."""
    sql = """
        SELECT COUNT(*) AS n, AVG(m) AS value FROM (
            SELECT CAST(json_extract(detail_json, '$.metric') AS REAL) AS m
            FROM decision_audit_events
            WHERE event_type = 'DECISION_EXECUTED'
              AND json_extract(detail_json, '$.run_id') = ?
            ORDER BY id DESC
            LIMIT ?
        )
    """
    conn = sqlite3.connect(db_path)
    try:
        n, value = conn.execute(sql, (run_id, window)).fetchone()
    finally:
        conn.close()
    return {"n": int(n), "value": None if value is None else float(value)}


def run_trial(scn: Scenario, mode: str, seed: int, steps: int, db_path: Optional[Path] = None) -> TrialResult:
    """Run one trial. With ``db_path`` the trial writes to that shared audit database (the caller owns
    it, see ``reset_db``); trials stay separate through their own agent id, ``run_id`` and DFIDs.
    Without it a throw-away database in a temporary directory is used and deleted afterwards."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    mon = scn.cfg["monitor"]
    window = int(mon["window"])
    poll_interval = int(mon.get("poll_interval", 1))
    run_id = f"{scn.name}:{mode}:{seed}"
    agent = f"{scn.agent_id}:{mode}:{seed}"  # own registry row per trial: a SUSPENDED status never leaks

    if db_path is not None:
        tmp = None
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        db_path = str(db_path)
    else:
        tmp = tempfile.mkdtemp(prefix="dir_exp_")
        db_path = os.path.join(tmp, "audit.db")
    try:
        bundle = sqlite_storage(db_path, connection_options=_EPHEMERAL_STORAGE_OPTIONS)
        audit = bundle.decision_audit
        registry = AgentRegistry(storage=bundle.agent_registry, supported_versions="1.x")
        hs = registry.handshake(agent, scn.contract(), "1.0.0")
        if not hs.accepted:
            raise RuntimeError(f"handshake rejected: {hs.reason}")

        llm = MockLLM(seed, scn.policy)
        ctx = {"state": {"risk_score": 0.1}}
        result = TrialResult(mode=mode, seed=seed)

        for step in range(steps):
            dfid = dfid_for(scn.name, seed, step, mode)
            status = (registry.get_agent_status(agent) or ("ACTIVE", None))[0]
            row: Dict[str, Any] = {
                "step": step, "mode": mode, "agent_status": status, "outcome": "",
                "metric": None, "loss": 0.0, "bad": False, "window_value": None,
                "drift_phase": step >= scn.drift_start,
            }

            if status == "SUSPENDED":
                row["outcome"] = "BLOCKED"
                audit.record(dfid, "DECISION_BLOCKED", agent_id=agent, state=status,
                             details={"run_id": run_id, "step": step})
                result.timeline.append(row)
                continue

            world = scn.world(step, np.random.default_rng([seed, 0, step]))
            raw = llm.generate(f"STEP={step}\nWORLD={json.dumps(world)}", system=scn.mission)
            pol = json.loads(raw)
            params = dict(pol["params"])
            if status == "DEGRADED":
                params = scn.degrade(params)

            proposal = PolicyProposal(
                dfid=dfid, agent_id=agent, policy_kind=pol["policy_kind"], params=params,
                confidence=float(pol.get("confidence", 0.9)), justification=pol.get("justification"),
            )
            verdict, reason = validate_proposal(proposal, ctx, None, contract=None)
            gate_reason = None if verdict == ValidationVerdict.ACCEPT else str(reason)
            gate_reason = gate_reason or scn.gate(params)

            if gate_reason:
                row["outcome"] = "REJECTED"
                audit.record(dfid, "DECISION_REJECTED", agent_id=agent, state=status,
                             details={"run_id": run_id, "step": step, "reason": gate_reason})
                result.timeline.append(row)
                continue

            ev = scn.evaluate(step, params, world)
            row.update(outcome="EXECUTED", metric=ev["metric"], loss=float(ev["loss"]), bad=bool(ev["bad"]))
            audit.record(dfid, "DECISION_EXECUTED", agent_id=agent, state=status, details={
                "run_id": run_id, "step": step, "mode": mode, "metric": ev["metric"],
                "loss": row["loss"], "bad": row["bad"], "params": params,
            })

            if mode == "dir" and (step + 1) % poll_interval == 0 and result.trip_step is None:
                agg = rolling_window_query(db_path, run_id, window)
                if agg["n"] >= window and agg["value"] is not None:
                    row["window_value"] = agg["value"]
                    if agg["value"] > scn.threshold + 1e-9:
                        registry.set_agent_status(agent, scn.breaker_status, scn.breaker_reason)
                        audit.record(dfid, "CIRCUIT_BREAKER_TRIPPED", agent_id=agent,
                                     state=scn.breaker_status, severity="WARNING", details={
                                         "run_id": run_id, "step": step, "window": window,
                                         "window_value": agg["value"], "threshold": scn.threshold,
                                         "reason": scn.breaker_reason})
                        result.trip_step = step
            result.timeline.append(row)
        return result
    finally:
        if tmp is not None:
            shutil.rmtree(tmp)
