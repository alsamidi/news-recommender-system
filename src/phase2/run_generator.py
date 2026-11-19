"""CLI driver: run the view-only generator on the real Indo catalog (Gate B).

  python -m src.phase2.run_generator --n 300 --reads-min 40 --reads-max 120 \
      --s 1.1 --recency-days 180 --drift 0.2 --seed 42 \
      [--since 2025-01-01] [--categories Berita,Politik,...] [--iterate]

Effective catalog: optional date-window (`--since`) + category-set
(`--categories`) filters shrink the 67,381-item corpus to a denser
simulation population; the exact rule is printed and written to the Gate B
JSON so it can be locked (never a silent filter). Without flags the FULL
catalog is used.

Writes:
  data/processed/indo/interactions.parquet   (dummy_user_id, nid, event,
                                              occurred_at)  [gitignored]
  docs/evidence/phase2/gate_b_report.json    (params + effective-catalog
                                              rule + Gate B statistics)
`--iterate` loops parameter presets (growing N) until the Gate B density
targets are met or the presets are exhausted (each attempt recorded).
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.phase2 import config
from src.phase2.generator import gate_b_report, generate_interactions
from src.phase2.split import draft_q80  # early import: fail fast (task 9 hook)

REPO = Path(__file__).resolve().parents[2]
GATE_B_OUT = REPO / "docs/evidence/phase2/gate_b_report.json"

# Gate B density targets (plan framework): frame-relative item coverage and
# per-account minimum reads.
TARGETS = {"items_ge1": 0.60, "items_ge3": 0.30}

ITERATE_PRESETS = [
    # (n_accounts, reads_min, reads_max, note)
    (300, 40, 120, "thin"),
    (600, 60, 180, "medium"),
    (1000, 80, 250, "dense"),
    (1500, 100, 350, "densest"),
]


def load_meta(since: str | None, categories: list[str] | None) -> pd.DataFrame:
    """Load catalog METADATA columns; apply the effective-catalog filters."""
    cols = ["nid", "category", "source", "published_at"]
    meta = pd.read_parquet(REPO / config.CATALOG_OUT, columns=cols)
    rule = {"date_since": since, "categories": categories, "full": True}
    if since:
        ts = pd.Timestamp(since, tz="UTC")
        meta = meta[meta["published_at"] >= ts]
        rule["full"] = False
    if categories:
        meta = meta[meta["category"].isin(categories)]
        rule["full"] = False
    meta = meta.reset_index(drop=True)
    rule["n_items"] = int(len(meta))
    return meta, rule


def attempt(meta: pd.DataFrame, n: int, reads_min: int, reads_max: int,
            s: float, recency_days: int, drift: float, seed: int) -> tuple:
    cfg = config.GeneratorConfig(
        n_accounts=n, reads_per_account=(reads_min, reads_max),
        powerlaw_s=s, recency_days=recency_days, category_drift=drift,
        seed=seed)
    inter = generate_interactions(meta, cfg)
    report = gate_b_report(inter, meta)
    report["config"] = {
        "n_accounts": n, "reads_per_account": [reads_min, reads_max],
        "powerlaw_s": s, "recency_days": recency_days,
        "category_drift": drift, "seed": seed}
    return inter, report


def meets_targets(report: dict, n_accounts: int) -> bool:
    cov = report["item_coverage"]
    return (cov["items_ge1_view"] >= TARGETS["items_ge1"]
            and cov["items_ge3_views"] >= TARGETS["items_ge3"]
            and report["accounts"]["pct_accounts_ge10_reads"] == 1.0)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python -m src.phase2.run_generator",
        description="Run the view-only interaction generator (Gate B).")
    ap.add_argument("--n", type=int, default=None,
                    help="number of dummy accounts")
    ap.add_argument("--reads-min", type=int, default=40)
    ap.add_argument("--reads-max", type=int, default=120)
    ap.add_argument("--s", type=float, default=1.1,
                    help="power-law popularity exponent")
    ap.add_argument("--recency-days", type=int, default=180)
    ap.add_argument("--drift", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--since", type=str, default=None,
                    help="effective catalog: only items published on/after "
                         "this UTC date (e.g. 2025-01-01)")
    ap.add_argument("--categories", type=str, default=None,
                    help="effective catalog: comma-separated category set")
    ap.add_argument("--iterate", action="store_true",
                    help="loop preset account counts until Gate B targets "
                         "pass (params otherwise as given)")
    ap.add_argument("--no-write", action="store_true",
                    help="do not persist interactions (probe)")
    args = ap.parse_args(argv)

    cats = args.categories.split(",") if args.categories else None
    meta, rule = load_meta(args.since, cats)
    print(f"effective catalog: {len(meta)} items (rule={rule})")

    attempts = []
    if args.iterate:
        presets = ITERATE_PRESETS
    else:
        presets = [(args.n, args.reads_min, args.reads_max, "given")]
    inter = report = None
    for n, rmin, rmax, note in presets:
        inter, report = attempt(meta, n, rmin, rmax, args.s,
                                args.recency_days, args.drift, args.seed)
        cov = report["item_coverage"]
        ok = meets_targets(report, n)
        print(f"n={n} [{note}]: events={len(inter)} "
              f"ge1={cov['items_ge1_view']:.3f} ge3={cov['items_ge3_views']:.3f} "
              f"acc>=10={report['accounts']['pct_accounts_ge10_reads']:.2f} "
              f"-> {'PASS' if ok else 'try next'}", flush=True)
        attempts.append(report)
        if ok:
            break
    if inter is None or not meets_targets(report, len(meta)):
        raise SystemExit("Gate B targets not met with any preset; "
                         "widen effective catalog or raise N (see attempts)")

    report["gate_b_decision"] = {
        "targets": TARGETS,
        "accepted": report["config"],
        # every attempt with its coverage numbers (one row per preset tried)
        "attempts": [
            {**a["config"],
             "items_ge1_view": a["item_coverage"]["items_ge1_view"],
             "items_ge3_views": a["item_coverage"]["items_ge3_views"],
             "acc_ge10": a["accounts"]["pct_accounts_ge10_reads"]}
            for a in attempts],
    }
    report["effective_catalog_rule"] = rule
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()

    out = REPO / "docs/evidence/phase2/gate_b_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    if not args.no_write:
        path = REPO / config.INTERACTIONS_OUT
        path.parent.mkdir(parents=True, exist_ok=True)
        inter.to_parquet(path, index=False)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"interactions: {len(inter)} events -> {path}")
        print(f"interactions sha256: {sha}")
    print(f"gate B report -> {out}")


if __name__ == "__main__":
    main()
