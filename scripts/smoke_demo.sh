#!/usr/bin/env bash
# P2 final smoke test (one command): pytest + live API demo.
#
#   bash scripts/smoke_demo.sh
#
# Proof produced: unit/parity tests green, then a booted server answering
# /health, /recommend warm (Top-10), /recommend cold (Top-10),
# /recommend cold-no-ALS (content-only fallback), /similar, /article.
# Fails non-zero on any broken step. Server is always cleaned up (trap).
set -euo pipefail
cd "$(dirname "$0")/.."
PORT=8000
OUT=/tmp/opencode/smoke_demo
mkdir -p "$OUT"

echo "=== [1/4] pytest ==="
source venv/bin/activate
python -m pytest -q 2>&1 | tail -1

echo "=== [2/4] resolve demo fixtures (frozen artifacts, deterministic) ==="
eval "$(python - <<'EOF'
import sys; sys.path.insert(0, 'src')
import json
import pandas as pd
from evaluation.full_catalog_eval import load_all
from evaluation.stratified_eval import pseudo_user_factor
from models.hybrid.infer import HybridRecommender
d = load_all()
elig = sorted(u for u in d["train_full"]
              if u in d["dev_full"] and (d["dev_full"][u] - d["train_full"][u]))
warm = elig[0]
train_nids = sorted(d["full_nids"][i] for i in d["train_full"][warm])
dv = pd.read_parquet("data/processed/interactions_dev.parquet").sort_values(["user_id", "time"])
cold = dv[~dv["user_id"].isin(set(d["user_map"]))]
sess = next(nids[:-1] for _, g in cold.groupby("user_id")
            for nids in [g["nid"].tolist()]
            if len(nids) >= 2 and nids[-1] in d["nid_to_full"]
            and any(n in d["item_map"] for n in nids[:-1]))
noals = [n for n in d["full_nids"] if n not in d["item_map"]][:3]
assert pseudo_user_factor(noals, d["item_map"], d["item_factors"]) is None
top1 = HybridRecommender(d).recommend_user(warm, top_k=1)[0]["nid"]
print(f"WARM={warm}")
print(f"TRAIN='{json.dumps(train_nids)}'")
print(f"SESS='{json.dumps(sess)}'")
print(f"NOALS='{json.dumps(noals)}'")
print(f"TOP1={top1}")
EOF
)"
echo "warm=$WARM session_items=$(python -c "import json;print(len(json.loads('$SESS')))") top1=$TOP1"

echo "=== [3/4] boot API (port $PORT) ==="
uvicorn src.api.main:app --port "$PORT" > "$OUT/uvicorn.log" 2>&1 &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  for _ in $(seq 1 20); do
    curl -sf --max-time 1 "localhost:$PORT/health" >/dev/null 2>&1 || return 0
    sleep 1
  done
}
trap cleanup EXIT
for _ in $(seq 1 40); do
  curl -sf "localhost:$PORT/health" > "$OUT/health.json" && break || sleep 2
done
python -m json.tool "$OUT/health.json"

echo "=== [4/4] demo requests ==="
curl -sf -X POST "localhost:$PORT/recommend" -H 'Content-Type: application/json' \
  -d "{\"user_id\":\"$WARM\",\"top_k\":10}" > "$OUT/warm.json"
curl -sf -X POST "localhost:$PORT/recommend" -H 'Content-Type: application/json' \
  -d "{\"history\":$SESS,\"top_k\":10}" > "$OUT/cold.json"
curl -sf -X POST "localhost:$PORT/recommend" -H 'Content-Type: application/json' \
  -d "{\"history\":$NOALS,\"top_k\":10}" > "$OUT/fallback.json"
curl -sf "localhost:$PORT/similar/$TOP1?top_k=5" > "$OUT/similar.json"
curl -sf "localhost:$PORT/article/$TOP1" > "$OUT/article.json"

WARM="$WARM" SESS="$SESS" NOALS="$NOALS" TRAIN="$TRAIN" TOP1="$TOP1" OUT="$OUT" \
python - <<'EOF'
import json, os
out, top1 = os.environ["OUT"], os.environ["TOP1"]
warm = json.load(open(f"{out}/warm.json"))
cold = json.load(open(f"{out}/cold.json"))
fb = json.load(open(f"{out}/fallback.json"))
sim = json.load(open(f"{out}/similar.json"))
art = json.load(open(f"{out}/article.json"))
train = set(json.loads(os.environ["TRAIN"]))

def check_top10(resp, mode):
    assert resp["mode"] == mode, resp["mode"]
    assert resp["alpha"] == 0.4 and resp["model_used"] == "hybrid"
    recs = resp["recommendations"]
    assert len(recs) == 10, len(recs)
    assert len({r["nid"] for r in recs}) == 10, "duplicate nids"
    for r in recs:
        assert {"nid", "title", "category", "subcategory", "score"} <= set(r), r
    return recs

w = check_top10(warm, "warm")
assert not ({r["nid"] for r in w} & train), "seen article recommended"
c = check_top10(cold, "cold-session")
f = check_top10(fb, "cold-session")  # content-only fallback, same contract
assert len(sim["similar"]) == 5 and top1 not in {r["nid"] for r in sim["similar"]}
assert art["nid"] == top1 and art["title"] and art["category"]

def table(name, recs):
    print(f"--- {name} ---")
    for i, r in enumerate(recs, 1):
        print(f"{i:2d}. {r['nid']:8s} [{r['category'] or '-':12s}] {r['score']:.4f}  {r['title'][:70]}")
table("WARM Top-10 (user history -> TF-IDF + ALS)", w)
table("COLD Top-10 (session -> TF-IDF + pseudo-CF)", c)
table("COLD FALLBACK Top-10 (no ALS item -> content-only)", f)
print("ALL SMOKE CHECKS PASSED")
EOF
