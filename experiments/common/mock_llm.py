"""Deterministic MockLLM: samples agent decisions from controlled distributions.

No network access and no API keys. The randomness of every call is derived only from
``(seed, step)``, so a decision does not depend on how many other calls were made.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Optional

import numpy as np

PolicyFn = Callable[[int, Dict[str, Any], np.random.Generator], Dict[str, Any]]

_STEP_RE = re.compile(r"STEP=(\d+)")
_WORLD_RE = re.compile(r"WORLD=(\{.*\})", re.S)


class MockLLM:
    """Exposes ``generate(prompt, system)`` like a text LLM and returns a JSON string."""

    def __init__(self, seed: int, policy_fn: PolicyFn) -> None:
        self._seed = int(seed)
        self._policy_fn = policy_fn

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        step = int(_STEP_RE.search(prompt).group(1))  # type: ignore[union-attr]
        world = json.loads(_WORLD_RE.search(prompt).group(1))  # type: ignore[union-attr]
        rng = np.random.default_rng([self._seed, 1, step])
        return json.dumps(self._policy_fn(step, world, rng))
