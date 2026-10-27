"""CLI: fit ALS on train interactions and write the Gate C report.

  python -m src.phase2.run_als [--write]

Reads data/processed/indo/interactions.parquet + the cutoff draft computed
from it (Task 9 ordering: cutoff is LOCKED only after Gate C passes).
Writes docs/evidence/phase2/gate_c_report.json; with --write also persists
models/indo_als_model.pkl + *_factors.npy (gitignored; sha256 recorded in
the lock).
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.phase2 import config
from src.phase2.split import draft_q80, split_interactions
from src.phase2.train_als import (REPO, build_csr, fit_als, gate_c_report,
                                  save_artifacts)

GATE_C_OUT = REPO / "docs/evidence/phase2/gate_c_report.json"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m src.phase2.run_als")
    ap.add_argument("--write", action="store_true",
                    help="persist model + factor artifacts to models/")
    args = ap.parse_args(argv)

    inter = pd.read_parquet(REPO / config.INTERACTIONS_OUT)
    cutoff = draft_q80(inter)
    train, dev = split_interactions(inter, cutoff)
    if len(dev) < 200:
        raise SystemExit(
            f"dev interactions {len(dev)} < 200; raising the quantile requires "
            "a recorded lock decision (plan Task 9 rule)")
    mat, uidx, iidx = build_csr(train)
    print(f"cutoff draft: {cutoff} | train events {len(train)}, "
          f"dev events {len(dev)} | CSR {mat.shape[0]}x{mat.shape[1]} "
          f"nnz={mat.nnz}", flush=True)

    model = fit_als(mat)
    # effective catalog size from the locked Gate B rule (single source)
    gb = json.loads((REPO / "docs/evidence/phase2/gate_b_report.json")
                    .read_text())
    n_effective = int(gb["effective_catalog_rule"]["n_items"])

    rep = gate_c_report(model, mat, n_effective)
    rep["cutoff_draft"] = str(cutoff)
    rep["dev_events"] = int(len(dev))
    rep["train_events"] = int(len(train))
    rep["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    GATE_C_OUT.parent.mkdir(parents=True, exist_ok=True)
    GATE_C_OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))

    if args.write:
        import numpy as np
        paths = save_artifacts(model)
        shas = {name: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                for name, p in paths.items()}
        rep["artifact_sha256"] = shas
        GATE_C_OUT.write_text(json.dumps(rep, indent=2))
        print("artifacts:", json.dumps(shas, indent=2))


if __name__ == "__main__":
    main()
