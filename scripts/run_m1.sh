#!/bin/bash
# M1 in one command (inside WSL):  bash scripts/run_m1.sh
# Gentle mode throughout: nice 19, 4 math threads, no GPU, at most 4 concurrent candidate processes,
# 1 GiB address-space limit per securegrade child.
# Needs: ~/p9/at (shipped aligntune 0.1.28), ~/p9/at-patched (57e9a95 + patches/aligntune diff),
# ~/p9/tools (datasets), exploits/tasks_all.json (from scripts/sg_fn_rate.py; network once).
set -u
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
cd $P
mkdir -p results/m1
rm -rf ~/p9/tmp
I="bash scripts/inv.sh"
echo "== 1. Gate 1 matrix: shipped and patched AlignTune"
$I at         python -W ignore scripts/gate1_run.py --pkg aligntune --parallel 4 --out results/m1/raw_shipped.json 2>&1 | grep -E '^wrote'
$I at-patched python -W ignore scripts/gate1_run.py --pkg aligntune --parallel 4 --out results/m1/raw_patched.json 2>&1 | grep -E '^wrote'
echo "== 2. Gate 1 matrix: securegrade"
$I tools python -I scripts/m1_securegrade.py
echo "== 3. False negatives on all MBPP-sanitized + HumanEval references"
$I tools      python -I scripts/sg_fn_rate.py > results/m1/securegrade_fn.log 2>&1; tail -22 results/m1/securegrade_fn.log | grep -E 'reference|exploit' | head -20
cp results/securegrade_fn.json results/m1/securegrade_fn.json
$I at         python -W ignore scripts/m1_fn_rate.py shipped results/m1/fn_shipped.json 2>/dev/null | grep -E '^shipped'
$I at-patched python -W ignore scripts/m1_fn_rate.py patched results/m1/fn_patched.json 2>/dev/null | grep -E '^patched'
echo "== 4. Recipe simulation and SystemExit check on the patched tree"
$I at-patched python -W ignore scripts/recipe_sim.py results/m1/recipe_sim_patched.json > results/m1/recipe_sim_patched.log 2>&1; echo "recipe_sim exit $?"
OUT=results/m1/systemexit_trl_patched.txt $I at-patched bash scripts/systemexit_check.sh > /dev/null; echo "systemexit check done"
echo "== 5. Tests"
$I at         python -m pytest -q -p no:cacheprovider securegrade/tests 2>&1 | tail -1
$I at-patched python -W ignore -m pytest -q -p no:cacheprovider patches/aligntune/tests 2>&1 | tail -1
$I st         python -W ignore -m pytest -q -p no:cacheprovider patches/safetune/tests 2>&1 | tail -1
echo "== 6. Report"
$I tools python -I scripts/make_m1_report.py
