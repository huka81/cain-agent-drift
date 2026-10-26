"""Robust figure saving (Windows-safe against transiently locked output files)."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import matplotlib.pyplot as plt

_RETRIES = 5
_RETRY_DELAY_S = 0.5


def _replace_with_retry(src: Path, dst: Path) -> None:
    # On Windows the target may be briefly held open by an image viewer,
    # antivirus or indexer, which surfaces as PermissionError or OSError(EINVAL).
    for attempt in range(_RETRIES):
        try:
            os.replace(src, dst)
            return
        except OSError:
            if attempt == _RETRIES - 1:
                raise
            time.sleep(_RETRY_DELAY_S * (attempt + 1))


def save_figure(fig, out: Path, stem: str) -> None:
    """Write ``<stem>.png`` and ``<stem>.pdf`` atomically, then close ``fig``."""
    out.mkdir(parents=True, exist_ok=True)
    try:
        for ext, kwargs in (("png", {"dpi": 200}), ("pdf", {})):
            fd, tmp_name = tempfile.mkstemp(prefix=f".{stem}.", suffix=f".{ext}", dir=out)
            os.close(fd)
            tmp = Path(tmp_name)
            try:
                fig.savefig(tmp, format=ext, bbox_inches="tight", **kwargs)
                _replace_with_retry(tmp, out / f"{stem}.{ext}")
            finally:
                if tmp.exists():
                    tmp.unlink()
    finally:
        plt.close(fig)