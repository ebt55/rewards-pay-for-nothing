#!/bin/bash
cd "$(dirname "${BASH_SOURCE[0]}")/.."   # repo root
OUT=results/path_check.jsonl
: > $OUT
for v in at:aligntune st:safetune; do
  V=${v%%:*}; P=${v##*:}
  PATH=$HOME/p9/$V/bin:/usr/bin:/bin CUDA_VISIBLE_DEVICES= $HOME/p9/$V/bin/python -W ignore scripts/path_check.py $P 2>/dev/null | tail -1 >> $OUT
  PATH=/usr/bin:/bin CUDA_VISIBLE_DEVICES= $HOME/p9/$V/bin/python -W ignore scripts/path_check.py $P 2>/dev/null | tail -1 >> $OUT
done
cat $OUT
