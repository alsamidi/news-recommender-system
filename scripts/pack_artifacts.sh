#!/usr/bin/env bash
# Build the artifact archive for a GitHub Release.
#
#   bash scripts/pack_artifacts.sh [--serving]
#
# Produces, in dist/:
#   ta-news-rec-artifacts-<date>.tar.zst   (or .tar.gz without zstd)
#   SHA256SUMS
#
# The archive preserves paths relative to the repo root, so extracting it into a
# fresh clone puts every file exactly where the code expects it.
#
# --serving packs only what the web app loads (78.8 MB instead of 385.5 MB),
# which is enough to run and demo the site but not to re-run the IndoBERT
# comparison in the thesis.
set -euo pipefail
cd "$(dirname "$0")/.."

MANIFEST="docs/ARTIFACT_CHECKSUMS.txt"
ONLY_SERVING=0
[ "${1:-}" = "--serving" ] && ONLY_SERVING=1

[ -f "$MANIFEST" ] || { echo "manifest missing: $MANIFEST" >&2; exit 2; }

# Refuse to pack a tree that does not match its own manifest.
echo "=== verifying artifacts before packing ==="
if [ "$ONLY_SERVING" -eq 1 ]; then
  bash scripts/verify_artifacts.sh --serving || exit 1
else
  bash scripts/verify_artifacts.sh || exit 1
fi

FILES=()
current=""
while IFS= read -r line; do
  case "$line" in
    "# --- "*) current="${line#\# --- }"; current="${current% ---}"; continue ;;
    ""|\#*) continue ;;
  esac
  set -- $line
  path="$3"
  if [ "$ONLY_SERVING" -eq 1 ] && [ "$current" != "serving" ]; then continue; fi
  FILES+=("$path")
done < "$MANIFEST"

mkdir -p dist
STAMP=$(date +%Y-%m-%d)
if [ "$ONLY_SERVING" -eq 1 ]; then SUFFIX="serving"; else SUFFIX="full"; fi
BASE="ta-news-rec-artifacts-${SUFFIX}-${STAMP}"

echo
echo "=== packing ${#FILES[@]} files ==="
if command -v zstd >/dev/null 2>&1; then
  ARCHIVE="dist/${BASE}.tar.zst"
  tar --zstd -cf "$ARCHIVE" "${FILES[@]}"
else
  ARCHIVE="dist/${BASE}.tar.gz"
  tar -czf "$ARCHIVE" "${FILES[@]}"
fi

# Checksums of the archive itself, for the release notes.
(cd dist && sha256sum "$(basename "$ARCHIVE")" > SHA256SUMS)

SIZE=$(du -h "$ARCHIVE" | cut -f1)
echo
echo "archive : $ARCHIVE ($SIZE)"
echo "checksums: dist/SHA256SUMS"
echo
echo "Upload both to the GitHub release, then verify a fresh clone with:"
echo "  tar -xf $(basename "$ARCHIVE") -C ."
echo "  bash scripts/verify_artifacts.sh"
