#!/usr/bin/env bash
# Verify the model artifacts against docs/ARTIFACT_CHECKSUMS.txt.
#
#   bash scripts/verify_artifacts.sh            # all artifacts
#   bash scripts/verify_artifacts.sh --serving  # only what the web app loads
#
# Exits 0 when every checked file matches, 1 when any is missing or corrupt.
# Run it after downloading the release archive and before starting the app:
# a wrong artifact silently changes recommendations rather than failing, so the
# checksum is the only thing standing between a bad download and a wrong demo.
set -uo pipefail
cd "$(dirname "$0")/.."

MANIFEST="docs/ARTIFACT_CHECKSUMS.txt"
GROUP="${1:-}"

[ -f "$MANIFEST" ] || { echo "manifest not found: $MANIFEST" >&2; exit 2; }

ok=0; bad=0; missing=0; skip=0
current=""
while IFS= read -r line; do
  # Blank and comment lines: track which group block we are inside, then skip.
  case "$line" in
    "# --- "*)
      current="${line#\# --- }"; current="${current% ---}"; continue ;;
    ""|\#*) continue ;;
  esac
  # shellcheck disable=SC2086
  set -- $line
  sha="$1"; bytes="$2"; path="$3"
  if [ "$GROUP" = "--serving" ] && [ "$current" != "serving" ]; then
    skip=$((skip+1)); continue
  fi

  if [ ! -f "$path" ]; then
    printf '  MISSING  %s\n' "$path"; missing=$((missing+1)); continue
  fi
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  size=$(wc -c < "$path" | tr -d ' ')
  if [ "$actual" = "$sha" ] && [ "$size" = "$bytes" ]; then
    printf '  ok       %s\n' "$path"; ok=$((ok+1))
  else
    printf '  CORRUPT  %s\n           expected %s (%s bytes)\n           actual   %s (%s bytes)\n' \
      "$path" "$sha" "$bytes" "$actual" "$size"
    bad=$((bad+1))
  fi
done < "$MANIFEST"

echo
echo "verified: $ok   corrupt: $bad   missing: $missing   skipped: $skip"
if [ "$bad" -ne 0 ] || [ "$missing" -ne 0 ]; then
  echo "FAILED — re-download the artifacts (see docs/ARTIFACTS.md)" >&2
  exit 1
fi
echo "OK — every checked artifact matches its recorded checksum."
