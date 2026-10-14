# Research Freeze (P3.4 — final, Day 6)

Re-run: `bash scripts/audit_freeze.sh` (safe: probes only, pipelines never run).
Status at freeze: **RESEARCH FREEZE AUDIT PASSED** (26 tests green).

## Check 1 — Tables A/B/C/D == JSON

All 32 rows of `models/full_catalog_tables.md` + `models/stratified_tables.md`
match `models/full_catalog_eval.json` / `models/stratified_eval.json`
(NDCG@10 + n per row, checked per section). Meta consistent across files:
catalog 93.698, ALS space 3.394, warm 2.000/2.858 eligible,
cold 2.000/22.703 usable, seed 42, `2000 − 1164 = 836`.
Argmaxes: Table B α=0,4 (0,00208), Table A α=1,0 (0,00928).

## Check 2 — Cited numbers == sources

Hyperparameters match `configs/*.yaml` (TF-IDF 1–2/50k/min2/max0.95;
ALS 128/0.01/40/20 iter/min-5-3; hybrid α=0,4; K=5/10/20).
Dataset figures match `data/DATASET_LOCK.md`; 62,7% / 88,1% / median-1 match
`models/error_coverage.json`. Every Table A–D figure in README and
`docs/metrics_source_of_truth.md` matches its JSON row. Stale-claim grep
clean (no 0.8-as-final, no old test count). Contract examples match live
responses (`docs/API_CONTRACT.md` verified against real runs).

## Check 3 — Alpha 0.4 end-to-end

Experiment winner (Table B) == `configs/hybrid.yaml` (0.4) ==
`serving_alpha()` runtime (0.4), enforced by
`test_serving_alpha_matches_table_b_winner`. `weighted_hybrid.pkl` (0.8) is a
historical ALS-space record, unread by serving (grep-proven), documented in
README + source-of-truth caveat 4.

## Check 4 — Report-cited commands resolve

`build_locked --help` (guarded, see below), all three `train --help`,
both eval scripts present-but-frozen, every referenced dataset/artifact/
config file exists. Training/evaluation pipelines are deliberately NOT
re-executed: outputs are frozen records, and ALS retraining is not
bit-deterministic across runs.

## Incident during this audit (lesson)

The first version of this audit probed `build_locked --help`, which —
`main()` having no argparse — launched a full multiprocessing rebuild that
had to be SIGKILLed. Frozen artifacts verified untouched afterwards
(`git status` clean, pre-existing mtimes). Fixed with a `--help` usage guard
in `build_locked.py` (no other behavior change). Rule going forward: probes
must be side-effect free; the audit script encodes this.

## Freeze declaration

Numbers, configs, and commands above are locked for the thesis report.
Any future change to a cited number requires re-running this audit.
Core model/API changes only for real bugs (cf. `day6-final-application` tag).
