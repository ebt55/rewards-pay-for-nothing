#!/bin/bash
# Rebuild the patched AlignTune tree from a clean 57e9a95 checkout and write the unified diff.
# Usage: bash patches/aligntune/apply.sh   (inside WSL)
# The small edits were made by hand in ~/p9/src/aligntune-patched; this script only re-applies the
# block edits (idempotence is not supported: run on a tree that has the small edits only).
set -e
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # repo root
T=~/p9/src/aligntune-patched
cd $T
for f in src/aligntune/rewards/core.py src/aligntune/rewards/verifiable.py src/aligntune/rewards/_code_sandbox.py; do
  /usr/bin/python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' $f && echo "parse ok $f"
done
git add -N src/aligntune/rewards/_code_sandbox.py 2>/dev/null || true
git diff --stat
git diff > $P/patches/aligntune/aligntune-57e9a95-securegrade-fixes.diff
echo "diff written: $(wc -l < $P/patches/aligntune/aligntune-57e9a95-securegrade-fixes.diff) lines"
