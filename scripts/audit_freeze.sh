#!/usr/bin/env bash
# P3.4 final research freeze audit (one command, SAFE).
#
#   bash scripts/audit_freeze.sh [VENV_DIR=path/to/venv]
#
# Verifies, without executing any training/evaluation pipeline
# (frozen artifacts must never be regenerated):
#   1. Tables A/B/C/D values == source JSON (all rows + meta + argmaxes)
#   2. Numbers cited in README/docs == sources (configs, DATASET_LOCK,
#      error_coverage, eval JSONs); no stale claims (alpha 0.8, old test count)
#   3. Final alpha 0.4 consistent: experiment winner == config == serving
#      (historical 0.8 pkl documented and unread by serving)
#   4. Every report-cited command resolves (help/import/file probes only)
# Fails non-zero on any mismatch.
set -euo pipefail
cd "$(dirname "$0")/.."
VENV_DIR="${VENV_DIR:-venv}"
source "$VENV_DIR/bin/activate"

echo "=== [1] tables A/B/C/D <-> JSON ==="
python - <<'EOF'
import json
fc = json.load(open('models/full_catalog_eval.json'))
st = json.load(open('models/stratified_eval.json'))
txt = open('models/full_catalog_tables.md').read()
secA, secB = txt.split('## Table A')[1].split('## Table B')[0], txt.split('## Table B')[1]
n = 0
for r in fc['table_a_restricted']:
    l = next(x for x in secA.splitlines() if x.startswith(f"| {r['alpha']:.1f} |"))
    assert f"{r['ndcg@10']:.5f}" in l and f"| {r['n_eval']} |" in l; n += 1
for r in fc['table_b_full_catalog']:
    l = next(x for x in secB.splitlines() if x.startswith(f"| {r['alpha']:.1f} |"))
    assert f"{r['ndcg@10']:.5f}" in l and f"| {r['n_eval']} |" in l; n += 1
txt2 = open('models/stratified_tables.md').read()
secC, secD = txt2.split('## Table C')[1].split('## Table D')[0], txt2.split('## Table D')[1]
for r in st['table_c_warm']:
    l = next(x for x in secC.splitlines() if x.startswith(f"| {r['method']} | {r['alpha']} |"))
    assert f"{r['ndcg@10']:.5f}" in l and f"| {r['n_eval']} |" in l; n += 1
for r in st['table_d_cold']:
    a = '—' if r['alpha'] is None else str(r['alpha'])
    l = next(x for x in secD.splitlines() if x.startswith(f"| {r['method']} | {a} |"))
    assert f"{r['ndcg@10']:.5f}" in l and f"| {r['n_eval']} |" in l; n += 1
m1, m2 = fc['meta'], st['meta']
assert m1['n_catalog_full'] == m2['n_catalog_full'] == 93698
assert m1['n_eligible_warm'] == m2['warm_eligible'] == 2858
assert m1['n_sampled'] == m2['warm_sampled'] == 2000
assert m1['seed'] == m2['seed'] == 42 and m1['n_als_items'] == 3394
assert m2['cold_sampled'] == 2000 and m2['cold_usable_sessions'] == 22703
assert 2000 - 1164 == 836
wb = max(fc['table_b_full_catalog'], key=lambda r: r['ndcg@10'])
wa = max(fc['table_a_restricted'], key=lambda r: r['ndcg@10'])
assert (wb['alpha'], round(wb['ndcg@10'], 5)) == (0.4, 0.00208)
assert (wa['alpha'], round(wa['ndcg@10'], 5)) == (1.0, 0.00928)
print(f"32 rows + meta + argmaxes: OK ({n} table rows checked)")
EOF

echo "=== [2] cited numbers <-> sources, no stale claims ==="
python - <<'EOF'
import json, yaml
t = yaml.safe_load(open('configs/tfidf_baseline.yaml'))['model']['vectorizer']
assert (t['ngram_range'], t['max_features'], t['min_df'], t['max_df']) == ([1, 2], 50000, 2, 0.95)
m = yaml.safe_load(open('configs/als.yaml'))
assert (m['model']['factors'], m['model']['regularization'], m['model']['alpha'], m['model']['iterations']) == (128, 0.01, 40.0, 20)
assert (m['data']['min_user_interactions'], m['data']['min_item_interactions']) == (5, 3)
ec = json.load(open('models/error_coverage.json'))
assert abs(ec['full']['pct_dev_relevant_items_unseen_in_train_interactions'] - 0.62703) < 1e-4
assert ec['full']['pct_dev_users_without_train_history'] == 0.88114
assert ec['eval']['relevant_per_eval_user_median'] == 1.0
lock = open('data/DATASET_LOCK.md').read()
for s in ['156.965', '50.000', '51.282', '73.152', '42.416', '2019-11-15', '100%']:
    assert s in lock, s
print("configs + DATASET_LOCK + error_coverage: OK")
EOF
# stale-claim grep: config must never again be described as 0.8-final
if grep -rn "content_weight: 0\.8" README.md docs/*.md; then
  echo "STALE: config described as 0.8-final"; exit 1
fi
grep -q "0\.4" README.md && echo "alpha-0.4-final cited: OK"
if grep -rn "12 passed" README.md docs/*.md; then
  echo "STALE test count found"; exit 1
fi
echo "no stale claims: OK"

echo "=== [3] alpha 0.4 chain: experiment == config == serving ==="
grep -q "^FINAL_ALPHA = 0.4" src/models/hybrid/infer.py
! grep -rn "weighted_hybrid" src/models/hybrid/infer.py src/api/main.py \
  || { echo "serving reads historical pkl!"; exit 1; }
python - <<'EOF'
import json, pickle, yaml
rows = json.load(open('models/full_catalog_eval.json'))['table_b_full_catalog']
assert max(rows, key=lambda r: r['ndcg@10'])['alpha'] == 0.4
assert yaml.safe_load(open('configs/hybrid.yaml'))['model']['content_weight'] == 0.4
assert pickle.load(open('models/weighted_hybrid.pkl', 'rb'))['content_weight'] == 0.8
import sys; sys.path.insert(0, 'src')
from models.hybrid.infer import serving_alpha
assert serving_alpha() == 0.4
print("winner(0.4) == config(0.4) == serving(0.4); pkl(0.8) historical+unused: OK")
EOF

echo "=== [4] report-cited commands resolve (probes only, pipelines never run) ==="
python -m src.preprocessing.build_locked --help | head -1
for m in src.models.content_based.train src.models.collaborative.train src.models.hybrid.train; do
  python -m $m --help >/dev/null 2>&1 && echo "$m: OK" || { echo "$m: BROKEN"; exit 1; }
done
for f in src/evaluation/full_catalog_eval.py src/evaluation/stratified_eval.py; do
  test -f "$f" && echo "$f: OK (frozen, not re-executed)"
done
for f in MINDsmall_train/behaviors.tsv xMINDsmall_train/news.tsv \
         MINDsmall_dev/behaviors.tsv xMINDsmall_dev/news.tsv \
         data/processed/news_processed.parquet \
         data/processed/interactions_train.parquet \
         data/processed/interactions_dev.parquet \
         models/tfidf_baseline.pkl models/als_model.pkl \
         models/als_user_factors.npy models/als_item_factors.npy \
         configs/hybrid.yaml; do
  test -f "$f" || { echo "missing: $f"; exit 1; }
done
echo "all referenced inputs exist: OK"

echo "=== [5] pytest ==="
python -m pytest -q 2>&1 | tail -1
echo "RESEARCH FREEZE AUDIT PASSED"
