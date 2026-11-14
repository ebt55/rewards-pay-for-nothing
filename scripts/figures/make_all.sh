#!/usr/bin/env bash
# Rebuild every article figure (light + dark, PNG at 2x + SVG) and figures/tables.md.
# Needs a venv with matplotlib (see figures/README.md). CPU only, low priority.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY="${FIGS_PY:-$HOME/p9/figs/bin/python}"
export CUDA_VISIBLE_DEVICES="" OMP_NUM_THREADS=4 MPLBACKEND=Agg PYTHONDONTWRITEBYTECODE=1
status=0
for s in fig1_audit_heatmap fig2_exploit_rate_8runs fig3_hole_pair fig4_heldout_evals fig5_block_reward make_tables; do
  nice -n 19 "$PY" "scripts/figures/$s.py" || status=1
done
exit $status
