#!/usr/bin/env bash
# Copy Ezra's eng_aiv USX export into this repo byte-for-byte and verify sha256 against his manifest.
# Usage: scripts/sync_from_ezra.sh [SRC_DIR]   (default /workspace/aiv-translations/aiv)
set -euo pipefail
SRC="${1:-/workspace/aiv-translations/aiv}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
test -f "$SRC/manifest.json" || { echo "no manifest at $SRC" >&2; exit 1; }
n=$(ls "$SRC"/usx/*.usx | wc -l); [ "$n" -eq 66 ] || { echo "expected 66 USX, found $n" >&2; exit 1; }
rm -f "$REPO"/usx/*.usx
cp -p "$SRC"/usx/*.usx "$REPO/usx/"
cp -p "$SRC/manifest.json" "$REPO/manifest.json"
python3 - "$REPO" <<'PY'
import hashlib, json, sys, pathlib
repo = pathlib.Path(sys.argv[1]); m = json.load(open(repo / "manifest.json"))
bad = [b["usfm"] for b in m["books"] if hashlib.sha256((repo / b["file"]).read_bytes()).hexdigest() != b["sha256"]]
extra = {p.name for p in (repo / "usx").glob("*.usx")} - {pathlib.Path(b["file"]).name for b in m["books"]}
print(f"books={len(m['books'])} sha_mismatch={bad} extra={sorted(extra)}")
sys.exit(1 if bad or extra or len(m["books"]) != 66 else 0)
PY
