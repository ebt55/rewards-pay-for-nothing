#!/bin/bash
# Runs inside the HF Job container (image ghcr.io/astral-sh/uv:python3.12-bookworm, pinned by digest
# in jobs/README.md). Usage: bash /in/jobs/run_train.sh <run_name> <grpo_train.py args...>
#
# Container safety (design §8):
# - the private bucket is mounted READ-ONLY at /in (code + securegrade only);
# - outputs go to local disk (/tmp/run/<run>) and grpo_train.py uploads them with HfApi;
# - the HF token is moved from the environment into a 0600 file before anything else starts,
#   and python is exec'd WITHOUT it in its environment; python reads the file and deletes it.
set -uo pipefail
RUN=$1
shift
TOKFILE=/tmp/.hf_tok_$$
( umask 077; printf '%s' "${HF_TOKEN:-}" > "$TOKFILE" )
unset HF_TOKEN HUGGING_FACE_HUB_TOKEN
OUTDIR=/tmp/run/$RUN
mkdir -p "$OUTDIR"
exec > >(tee -a "$OUTDIR/job.log") 2>&1
T0=$(date +%s)
echo "JOB_START_UTC $(date -u +%FT%TZ) RUN $RUN UID $(id -u)"
echo "IMAGE_FINGERPRINT python=$(python3 -VV 2>&1 | head -1) uv=$(uv --version) debian=$(cat /etc/debian_version)"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv
export UV_LINK_MODE=copy
uv venv /venv --python 3.12 -q
export VIRTUAL_ENV=/venv PATH=/venv/bin:$PATH
uv pip install -q -r /in/jobs/requirements-lock.txt || { echo "INSTALL_FAILED"; rm -f "$TOKFILE"; exit 2; }
SETUPTOOLS_SCM_PRETEND_VERSION=0.1.10 uv pip install -q --no-deps \
  "aligntune @ git+https://github.com/Lexsi-Labs/aligntune@57e9a95e79ace15014beede175c4c3d72405f3b3" \
  || { echo "ALIGNTUNE_INSTALL_FAILED"; rm -f "$TOKFILE"; exit 2; }
echo "INSTALL_SECONDS $(( $(date +%s) - T0 ))"
cd /tmp
exec python /in/jobs/grpo_train.py --out "$OUTDIR" --token-file "$TOKFILE" \
  --upload-bucket ebt005/p9-grpo-smoke --upload-prefix "runs/$RUN" "$@"
