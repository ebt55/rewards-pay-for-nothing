#!/bin/bash
# Full install of the safetune wheel from PyPI into ~/p9/st (WSL home).
set -u
UV=~/.local/bin/uv
LOG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/notes/logs"
mkdir -p "$LOG"
mkdir -p ~/p9
cd ~/p9
$UV venv --python 3.12 ~/p9/st > $LOG/st_venv.log 2>&1
source ~/p9/st/bin/activate
date -u > $LOG/st_install.log
$UV pip install "safetune==0.1.10" pytest pytest-timeout >> $LOG/st_install.log 2>&1
echo "EXIT=$?" >> $LOG/st_install.log
date -u >> $LOG/st_install.log
