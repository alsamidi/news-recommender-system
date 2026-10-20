#!/usr/bin/env bash
# Web MVP smoke test (TEST-AC-120/121).
#
#   bash scripts/smoke_web.sh [VENV_DIR=path/to/venv] [PORT=8100]
#
# Skenario A (user baru): register -> feed populer -> buka detail ->
#   cek event view -> feed dari riwayat -> histori.
# Skenario B (persona) : seed persona -> login -> feed warm -> buka detail.
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
WEB_DEMO_PERSONA_USER_ID=U10045 \
WEB_DEMO_PERSONA_EMAIL=demo@example.com \
WEB_DEMO_PERSONA_PASSWORD="$DEMO_PASSWORD" \
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
assert h == {"status": "ok", "alpha": 0.4, "catalog_size": 93698, "als_items": 3394}, h
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

feed = get("/")
assert "Berita populer" in feed, "expected popular label on first feed"
nids = re.findall(r'/berita/(N\d+)', feed)
assert len(nids) == 10, f"expected 10 cards, got {len(nids)}"
print(f"feed populer: {len(nids)} kartu, label OK")

get(f"/berita/{nids[0]}")
get(f"/berita/{nids[1]}")

con = sqlite3.connect(db)
views = con.execute("SELECT COUNT(*) FROM interactions WHERE event='view'").fetchone()[0]
assert views == 2, f"expected 2 view rows, got {views}"
print(f"event view tercatat: {views}")

feed2 = get("/")
assert "Rekomendasi dari riwayat bacaanmu" in feed2, "expected cold label"
nids2 = re.findall(r'/berita/(N\d+)', feed2)
assert not (set(nids2) & set(nids[:2])), "already-read article reappeared"
assert len(nids2) <= 10
print(f"feed cold: {len(nids2)} kartu, tanpa artikel yang sudah dibaca")

hist = get("/histori")
assert nids[0] in hist and nids[1] in hist, "history missing viewed articles"
print("histori: OK")
EOF

echo "=== [4] scenario B: dataset persona ==="
WEB_DB_PATH="$DB" \
WEB_DEMO_PERSONA_USER_ID=U10045 \
WEB_DEMO_PERSONA_EMAIL=demo@example.com \
WEB_DEMO_PERSONA_PASSWORD="$DEMO_PASSWORD" \
  python -m src.web.seed_persona | tee "$OUT/seed.txt"

python - "$PORT" "$DEMO_PASSWORD" <<'EOF'
import re, sys, urllib.parse
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor, Request

port, demo_password = sys.argv[1], sys.argv[2]
base = f"http://localhost:{port}"
op = build_opener(HTTPCookieProcessor(CookieJar()))

def get(path):
    return op.open(base + path).read().decode()

def post(path, data):
    req = Request(base + path, data=urllib.parse.urlencode(data).encode(), method="POST")
    return op.open(req)

token = re.search(r'name="csrf_token" value="([^"]+)"', get("/login")).group(1)
post("/login", {"email": "demo@example.com", "password": demo_password,
                "csrf_token": token})
feed = get("/")
assert "Rekomendasi berdasarkan profil dataset demo" in feed, "expected warm label"
nids = re.findall(r'/berita/(N\d+)', feed)
assert len(nids) == 10, f"expected 10 warm cards, got {len(nids)}"
print(f"feed warm: {len(nids)} kartu, label OK")

get(f"/berita/{nids[0]}")
print("detail persona: OK")
EOF

echo "=== [5] unauthenticated access is blocked ==="
code=$(curl -s -o /dev/null -w "%{http_code}" "localhost:$PORT/")
[ "$code" = "303" ] || { echo "FATAL: anonymous / returned $code"; exit 1; }
echo "anon / -> 303: OK"

echo "=== [6] no traceback leaked ==="
if grep -qi "traceback" "$OUT/uvicorn.log"; then
  echo "FATAL: traceback in server log"; tail -20 "$OUT/uvicorn.log"; exit 1
fi
echo "no traceback: OK"

echo "=== [7] shutdown ==="
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
