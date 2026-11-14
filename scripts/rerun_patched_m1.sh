#!/bin/bash
# After a change to the patched AlignTune tree: regenerate the diff, reinstall into ~/p9/at-patched,
# re-run the patched parts of M1 and its regression tests, rebuild the report. Gentle mode.
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
cd $P
mkdir -p notes/logs   # not part of the published repo
nice -n 19 bash patches/aligntune/apply.sh | tail -2
source ~/p9/at-patched/bin/activate
nice -n 19 ~/.local/bin/uv pip install --reinstall-package aligntune ~/p9/src/aligntune-patched --override notes/overrides-no-pyicu.txt > notes/logs/at_patched_reinstall.log 2>&1; echo "reinstall exit $?"
deactivate
I="bash scripts/inv.sh"
$I at-patched python -W ignore -m pytest -q -p no:cacheprovider patches/aligntune/tests 2>&1 | tail -1
$I at-patched python -W ignore scripts/gate1_run.py --pkg aligntune --parallel 4 --out results/m1/raw_patched.json 2>&1 | grep -E '^wrote'
$I at-patched python -W ignore scripts/m1_fn_rate.py patched results/m1/fn_patched.json 2>/dev/null | grep -E '^patched'
$I at-patched python -W ignore scripts/recipe_sim.py results/m1/recipe_sim_patched.json > results/m1/recipe_sim_patched.log 2>&1; echo "recipe_sim exit $?"
$I tools python -I scripts/make_m1_report.py > results/m1/make_report.log 2>&1; echo "report exit $?"
