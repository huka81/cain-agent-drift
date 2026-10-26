"""Run Baseline vs DIR for this experiment and write results and figures."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.runner import main  # noqa: E402

if __name__ == "__main__":
    main(__file__)
