#!/usr/bin/env python3
"""Fail if the frozen API contract drifted.

Asserts the four published routes and that docs/openapi.json matches the app
exactly. Runs in CI without model artifacts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from api.main import app  # noqa: E402

EXPECTED = {"/health", "/recommend", "/similar/{nid}", "/article/{nid}"}


def main() -> int:
    spec = app.openapi()
    paths = set(spec["paths"])

    if paths != EXPECTED:
        print(f"FAIL: contract surface changed\n  got:      {sorted(paths)}\n"
              f"  expected: {sorted(EXPECTED)}", file=sys.stderr)
        return 1

    snapshot = json.loads((REPO / "docs/openapi.json").read_text())
    if spec != snapshot:
        print("FAIL: docs/openapi.json no longer matches app.openapi(). "
              "Regenerate only with a version bump.", file=sys.stderr)
        return 1

    print(f"OK: {len(paths)} routes, snapshot matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
