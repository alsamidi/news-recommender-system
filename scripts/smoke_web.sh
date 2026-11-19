#!/usr/bin/env bash
# Web MVP smoke test (TEST-AC-120/121).
#
#   bash scripts/smoke_web.sh [VENV_DIR=path/to/venv] [PORT=8100]
#
# Skenario A (user baru): register -> onboarding topik -> feed populer ->
#   buka detail -> cek event view -> feed dari riwayat -> histori.
# Skenario A2 (user 0-view dengan topik): feed topik -> handover ke riwayat.
#
# The dataset-persona scenario (former B) is gone: v1.3 removed the persona
# feature, so there is no seeded account and no warm label to assert.
#
# Fails non-zero on any broken step. Runs against a throwaway database so it
# never touches data/web.db. Server is always cleaned up (trap).
set -euo pipefail
cd "$(dirname "$0")/.."
VENV_DIR="${VENV_DIR:-venv}"
PORT="${1:-8100}"
OUT="${OUT_DIR:-/tmp/opencode/smoke_web}"
WORK="$(mktemp -d)"
DB="$WORK/web.db"

# Throwaway credentials for this run only. Generated, never committed, never
# printed. Avoids literal passwords in the repository (secret scanners flag them).
DEMO_PASSWORD="$(python -c 'import secrets;print(secrets.token_urlsafe(18))')"
USER_PASSWORD="$(python -c 'import secrets;print(secrets.token_urlsafe(18))')"

mkdir -p "$OUT"
source "$VENV_DIR/bin/activate"

cleanup() {
  if [ -n "${SERVER_PID:-}" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    for _ in $(seq 1 20); do
      curl -sf --max-time 1 "localhost:$PORT/health" >/dev/null 2>&1 || break
      sleep 1
    done
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

echo "=== [1] start web app (port $PORT, db $DB) ==="
WEB_DB_PATH="$DB" \
  uvicorn web.app:app --app-dir src --port "$PORT" > "$OUT/uvicorn.log" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 40); do
  curl -sf "localhost:$PORT/login" >/dev/null 2>&1 && break
  sleep 2
done

echo "=== [2] frozen API still reachable through the mount ==="
curl -sf "localhost:$PORT/health" | tee "$OUT/health.json" | python -m json.tool
python - <<'EOF'
import json
h = json.load(open('/tmp/opencode/smoke_web/health.json'))
assert h == {"status": "ok", "alpha": 0.8, "catalog_size": 67381, "als_items": 13881}, h
print("frozen contract intact: OK")
EOF

echo "=== [3] scenario A: new user ==="
python - "$PORT" "$DB" "$USER_PASSWORD" <<'EOF'
import re, sqlite3, sys, urllib.parse
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor, Request

port, db, user_password = sys.argv[1], sys.argv[2], sys.argv[3]
base = f"http://localhost:{port}"
jar = CookieJar()
op = build_opener(HTTPCookieProcessor(jar))

def get(path):
    return op.open(base + path).read().decode()

def post(path, data):
    body = urllib.parse.urlencode(data).encode()
    req = Request(base + path, data=body, method="POST")
    return op.open(req)

def csrf():
    return re.search(r'name="csrf_token" value="([^"]+)"', get("/register")).group(1)

post("/register", {"name": "Demo User", "email": "user@example.com",
                   "password": user_password, "password_confirm": user_password,
                   "csrf_token": csrf()})

# PRD addendum v1.2 / PRD-AC-62: onboarding is offered once, skipping works,
# and the topic feed is a slice of the frozen popularity list.
onb = get("/onboarding/topik")
assert "Pilih beberapa topik yang paling kamu sukai" in onb, \
    "onboarding screen missing after register"
chips = re.findall(r'name="topik" value="([^"]+)"', onb)
assert len(chips) == 12, f"expected 12 chips, got {len(chips)}"
tok = re.search(r'name="csrf_token" value="([^"]+)"', onb).group(1)
post("/onboarding/topik", {"csrf_token": tok, "lewati": "1"})
again = op.open(base + "/onboarding/topik")
assert "Pilih beberapa topik yang paling kamu sukai" not in again.read().decode(), \
    "onboarding repeated"
print(f"onboarding: 12 chip, skippable, sekali saja")

feed = get("/")
assert "Berita populer" in feed, "expected popular label on first feed"
nids = re.findall(r'/berita/([NI][0-9a-zA-Z]+)', feed)
assert len(nids) == 12, f"expected 12 cards, got {len(nids)}"
print(f"feed populer: {len(nids)} kartu, label OK")

get(f"/berita/{nids[0]}")
get(f"/berita/{nids[1]}")

con = sqlite3.connect(db)
views = con.execute("SELECT COUNT(*) FROM interactions WHERE event='view'").fetchone()[0]
assert views == 2, f"expected 2 view rows, got {views}"
print(f"event view tercatat: {views}")

feed2 = get("/")
assert "Rekomendasi dari riwayat bacaanmu" in feed2, "expected cold label"
nids2 = re.findall(r'/berita/([NI][0-9a-zA-Z]+)', feed2)
assert not (set(nids2) & set(nids[:2])), "already-read article reappeared"
assert len(nids2) <= 12
print(f"feed cold: {len(nids2)} kartu, tanpa artikel yang sudah dibaca")

hist = get("/histori")
assert nids[0] in hist and nids[1] in hist, "history missing viewed articles"
print("histori: OK")
EOF

echo "=== [3b] topic feed for a 0-view user ==="
python - "$PORT" "$USER_PASSWORD" <<'EOF'
import re, sys, urllib.parse
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor, Request

port, user_password = sys.argv[1], sys.argv[2]
base = f"http://localhost:{port}"
jar = CookieJar()
op = build_opener(HTTPCookieProcessor(jar))

def get(path):
    return op.open(base + path).read().decode()

def post(path, data):
    req = Request(base + path, data=urllib.parse.urlencode(data, doseq=True).encode(),
                  method="POST")
    return op.open(req)

tok = re.search(r'name="csrf_token" value="([^"]+)"', get("/register")).group(1)
post("/register", {"name": "Topic User", "email": "topic@example.com",
                   "password": user_password, "password_confirm": user_password,
                   "csrf_token": tok})
onb = get("/onboarding/topik")
tok = re.search(r'name="csrf_token" value="([^"]+)"', onb).group(1)
post("/onboarding/topik", {"csrf_token": tok,
                           "topik": ["Politik", "Hukum"]})

feed = get("/")
assert "Populer di topik pilihanmu" in feed, "topic label missing"
nids = re.findall(r'/berita/([NI][0-9a-zA-Z]+)', feed)
assert len(nids) == 12, f"expected 12 cards, got {len(nids)}"
assert len(set(nids)) == len(nids), "duplicate card in topic feed"
print(f"feed topik: {len(nids)} kartu unik, label OK")

get(f"/berita/{nids[0]}")
assert "Populer di topik pilihanmu" not in get("/"), "topic feed survived a view"
print("handover ke jalur riwayat: OK")
EOF

echo "=== [4] unauthenticated access is blocked ==="
code=$(curl -s -o /dev/null -w "%{http_code}" "localhost:$PORT/")
[ "$code" = "303" ] || { echo "FATAL: anonymous / returned $code"; exit 1; }
echo "anon / -> 303: OK"

echo "=== [5] no traceback leaked ==="
if grep -qi "traceback" "$OUT/uvicorn.log"; then
  echo "FATAL: traceback in server log"; tail -20 "$OUT/uvicorn.log"; exit 1
fi
echo "no traceback: OK"

echo "=== [6] shutdown ==="
kill "$SERVER_PID"
wait "$SERVER_PID" 2>/dev/null || true
SERVER_PID=""
for _ in $(seq 1 20); do
  curl -sf --max-time 1 "localhost:$PORT/health" >/dev/null 2>&1 || break
  sleep 1
done
curl -sf --max-time 2 "localhost:$PORT/health" >/dev/null 2>&1 && {
  echo "FATAL: port still open"; exit 1; }
echo "port $PORT closed"

echo "ALL WEB SMOKE CHECKS PASSED"
