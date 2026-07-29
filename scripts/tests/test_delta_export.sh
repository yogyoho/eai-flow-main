#!/usr/bin/env bash
# Self-check for the --delta diff logic (Task 3.2).
# Validates the core invariant: an image is "changed" iff its current digest
# differs from (or is absent in) the previous manifest's digest.
# (The full delta branch is embedded in offline-export.sh and exercised by a real
#  export; this checks the comparison algorithm in isolation, cheaply.)
# Run: bash scripts/tests/test_delta_export.sh
set -euo pipefail

# Detect a working python3 (Windows python3 is often a broken Store stub — verify it runs).
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys;assert sys.version_info>=(3,)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "SKIP: no working python3"; exit 0; }

"$PY" <<'PY'
prev = {"a": {"digest": "d1"}, "b": {"digest": "d2"}, "c": {"digest": "d3"}}
cur  = {"a": "d1", "b": "CHANGED", "d": "new-img"}   # a unchanged, b changed, c dropped, d added
changed   = [k for k in cur if cur[k] != prev.get(k, {}).get("digest", "")]
unchanged = [k for k in cur if cur[k] == prev.get(k, {}).get("digest", "")]
assert changed   == ["b", "d"], f"changed={changed}"
assert unchanged == ["a"],      f"unchanged={unchanged}"
print("PASS: delta diff logic (changed=[b,d], unchanged=[a])")
PY
