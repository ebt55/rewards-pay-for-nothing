#!/bin/bash
# Usage: inv.sh <at|st|at-patched|tools> <command...>
# Runs a command inside the given WSL venv from the project root, in "gentle mode":
# lowest CPU priority, 4 math threads, no GPU.
V=$1; shift
source ~/p9/$V/bin/activate
cd "$(dirname "${BASH_SOURCE[0]}")/.."   # repo root
export CUDA_VISIBLE_DEVICES=""   # no GPU work
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false
exec nice -n 19 "$@"
