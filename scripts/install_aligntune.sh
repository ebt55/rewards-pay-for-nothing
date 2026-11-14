#!/bin/bash
# Install the aligntune wheel from PyPI into ~/p9/at (WSL home).
# Attempt 1 (plain `uv pip install aligntune==0.1.28`) failed on PyICU (needs libicu-dev + pkg-config, no sudo).
# Attempt 2 (this script): full dependency tree with PyICU excluded via a uv override.
set -u
UV=~/.local/bin/uv
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
LOG=$P/notes/logs
mkdir -p "$LOG"   # notes/logs/ is not part of the published repo
mkdir -p ~/p9
[ -d ~/p9/at ] || $UV venv --python 3.12 ~/p9/at > $LOG/at_venv.log 2>&1
source ~/p9/at/bin/activate
date -u > $LOG/at_install2.log
$UV pip install "aligntune==0.1.28" pytest pytest-timeout --override $P/notes/overrides-no-pyicu.txt >> $LOG/at_install2.log 2>&1
echo "EXIT=$?" >> $LOG/at_install2.log
date -u >> $LOG/at_install2.log
