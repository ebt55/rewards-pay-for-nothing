#!/bin/bash
# Small helper venv (datasets only) used to fetch the benchmark tasks once.
set -eu
~/.local/bin/uv venv --python 3.12 ~/p9/tools >/dev/null 2>&1 || true
source ~/p9/tools/bin/activate
~/.local/bin/uv pip install -q datasets
cd "$(dirname "${BASH_SOURCE[0]}")/.."   # repo root
python -I scripts/fetch_tasks.py
