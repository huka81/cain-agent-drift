"""Regenerate the figures from stored results (run ``run.py`` first)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.plotting import make_figures  # noqa: E402

if __name__ == "__main__":
    make_figures(Path(__file__).resolve().parent)
