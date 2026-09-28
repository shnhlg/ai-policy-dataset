"""Run tests against the selected Docker release or the local index."""
import os
from pathlib import Path
import sys
from prepare_runtime import prepare

ROOT = Path(__file__).resolve().parents[1]
prepare()
os.execv(sys.executable, [sys.executable, '-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'), '-v'])
