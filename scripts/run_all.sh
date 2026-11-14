#!/bin/bash
# One command for Gate 1 (run inside WSL Ubuntu after notes/INSTALL.md):
#   bash scripts/run_all.sh
# The venv must be ACTIVATED (inv.sh does it): several rewards run tests with subprocess ['python', ...],
# which only resolves when the venv's bin is on PATH (see results/path_check.jsonl).
# Needs network only for the recipe simulation (it loads openai/openai_humaneval and tries openai/humaneval).
set -u
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
cd $P
export CUDA_VISIBLE_DEVICES=""          # no GPU work
rm -rf ~/p9/tmp                         # rewards' own temp files go here, outside the repo
~/p9/tools/bin/python scripts/make_exploits.py
[ -f exploits/tasks.json ] || ~/p9/tools/bin/python -I scripts/fetch_tasks.py
bash scripts/inv.sh at python -W ignore scripts/gate1_run.py --pkg aligntune --out results/raw_aligntune.json 2>&1 | grep -E '^side|^wrote'
bash scripts/inv.sh st python -W ignore scripts/gate1_run.py --pkg safetune --out results/raw_safetune.json 2>&1 | grep -E '^side|^wrote'
bash scripts/inv.sh at python -W ignore scripts/recipe_sim.py > results/recipe_sim.log 2>&1; echo "recipe_sim exit $?"
bash scripts/inv.sh at bash scripts/systemexit_check.sh > /dev/null; echo "systemexit check done"
bash scripts/path_check.sh > /dev/null; echo "path check done"
bash scripts/inv.sh at python -W ignore scripts/sql_check.py 2>/dev/null | tail -1 > results/sql_check.json
~/p9/tools/bin/python scripts/make_report.py
bash scripts/inv.sh at python -m pytest -q -p no:cacheprovider tests/
