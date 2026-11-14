#!/bin/bash
# Install the patched AlignTune tree (~/p9/src/aligntune-patched = 57e9a95 + patches/aligntune/*.diff)
# into its own venv ~/p9/at-patched, same dependency set as ~/p9/at (PyICU excluded).
set -u
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
LOG=$P/notes/logs/at_patched_install.log
mkdir -p "$P/notes/logs"   # not part of the published repo
UV=~/.local/bin/uv
[ -d ~/p9/at-patched ] || nice -n 19 $UV venv --python 3.12 ~/p9/at-patched > $LOG 2>&1
source ~/p9/at-patched/bin/activate
date -u >> $LOG
nice -n 19 $UV pip install ~/p9/src/aligntune-patched pytest --override $P/notes/overrides-no-pyicu.txt >> $LOG 2>&1
echo "EXIT=$?" >> $LOG
date -u >> $LOG
tail -3 $LOG
