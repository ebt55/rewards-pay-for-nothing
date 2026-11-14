#!/bin/bash
# Runs inside the HF Job container (image ghcr.io/astral-sh/uv:python3.12-bookworm).
# Usage: bash /out/jobs/run_smoke.sh <steps> <run_name> [extra args for grpo_smoke.py]
# /out is the PRIVATE bucket hf://buckets/ebt005/p9-grpo-smoke mounted read-write.
set -uo pipefail
STEPS=${1:-2}
RUN=${2:-dry}
shift 2 || true
OUTDIR=/out/runs/$RUN
mkdir -p "$OUTDIR"
exec > >(tee -a "$OUTDIR/job.log") 2>&1
T0=$(date +%s)
echo "JOB_START_UTC $(date -u +%FT%TZ)"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv
nproc; free -g | head -2
export UV_LINK_MODE=copy
uv venv /venv --python 3.12 -q
export VIRTUAL_ENV=/venv PATH=/venv/bin:$PATH
uv pip install -q -r /out/jobs/requirements-lock.txt || { echo "INSTALL_FAILED"; exit 2; }
SETUPTOOLS_SCM_PRETEND_VERSION=0.1.10 uv pip install -q --no-deps \
  "aligntune @ git+https://github.com/Lexsi-Labs/aligntune@57e9a95e79ace15014beede175c4c3d72405f3b3" \
  || { echo "ALIGNTUNE_INSTALL_FAILED"; exit 2; }
echo "INSTALL_SECONDS $(( $(date +%s) - T0 ))"
cd /tmp
python /out/jobs/grpo_smoke.py --steps "$STEPS" --out "$OUTDIR" "$@"
RC=$?
echo "TOTAL_SECONDS_IN_CONTAINER $(( $(date +%s) - T0 )) RC $RC"
exit $RC
