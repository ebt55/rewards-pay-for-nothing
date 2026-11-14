#!/bin/bash
# Re-run only the securegrade parts of M1 (after the unshare-probe race fix and the uid drop), then rebuild the report.
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
cd $P
I="bash scripts/inv.sh"
$I tools python -I scripts/m1_securegrade.py
$I tools python -I scripts/sg_fn_rate.py > results/m1/securegrade_fn.log 2>&1; grep -E 'reference|exploit|isolation' results/m1/securegrade_fn.log | head -24
cp results/securegrade_fn.json results/m1/securegrade_fn.json
$I tools python -I scripts/make_m1_report.py > results/m1/make_report.log 2>&1; echo "report exit $?"
