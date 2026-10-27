"""Sys.path bootstrap for phase2 tests (mirrors tests/web/conftest.py)."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
for p in (str(SRC), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)
