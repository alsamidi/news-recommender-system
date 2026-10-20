#!/usr/bin/env python3
"""Fail if the alpha=0.4 chain breaks.

Winner of Table B == configs/hybrid.yaml == serving_alpha(). Runs in CI without
loading the model.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from models.hybrid.infer import serving_alpha  # noqa: E402

EXPECTED = 0.4


def main() -> int:
    rows = json.loads((REPO / "models/full_catalog_eval.json").read_text())[
        "table_b_full_catalog"]
    winner = max(rows, key=lambda r: r["ndcg@10"])["alpha"]
    cfg = yaml.safe_load((REPO / "configs/hybrid.yaml").read_text())[
        "model"]["content_weight"]
    serving = serving_alpha(str(REPO / "configs/hybrid.yaml"))

    if not (winner == cfg == serving == EXPECTED):
        print(f"FAIL: alpha chain broken\n  table B winner: {winner}\n"
              f"  config:         {cfg}\n  serving:        {serving}\n"
              f"  expected:       {EXPECTED}", file=sys.stderr)
        return 1

    print(f"OK: winner == config == serving == {EXPECTED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
