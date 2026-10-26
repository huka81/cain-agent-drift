"""Run all experiments sequentially: ``python experiments/run_all.py [--seeds N]``."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    for exp in sorted(p for p in ROOT.iterdir() if p.is_dir() and (p / "run.py").exists()):
        subprocess.run([sys.executable, str(exp / "run.py"), *sys.argv[1:]], check=True)
