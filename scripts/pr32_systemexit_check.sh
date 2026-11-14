#!/bin/bash
# Runs scripts/pr32_systemexit_trl_driver.py for each middle completion, once with safetune 0.1.10
# (installed in ~/p9/st) and once with the PR #32 clone, each in a fresh throwaway process with a
# minimal environment (env -i: no tokens in the driver's environment). Gentle mode: nice 19,
# 4 threads, no GPU. Records exit status and output in results/safetune-pr32/systemexit_trl.txt.
#   bash scripts/pr32_systemexit_check.sh
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
cd $P
OUT=${OUT:-results/safetune-pr32/systemexit_trl.txt}
PRSRC=${PR32_SRC_PR:-$HOME/scratch/safetune-pr32/src}
TMPO=$(mktemp); TMPE=$(mktemp)
: > $OUT
for src in installed "$PRSRC"; do
  for a in none exit0 exit3 os_exit0 kill_parent; do
    echo "=== safetune: $([ $src = installed ] && echo '0.1.10 (installed)' || echo 'PR #32 clone') | middle completion: $a" >> $OUT
    env -i HOME=$HOME PATH=$HOME/p9/st/bin:/usr/bin:/bin CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 \
        PR32_SRC=$src timeout 300 nice -n 19 $HOME/p9/st/bin/python -W ignore scripts/pr32_systemexit_trl_driver.py $a > $TMPO 2> $TMPE
    echo "process exit status: $?" >> $OUT
    echo "--- stdout:" >> $OUT; sed "s#$HOME#~#g" $TMPO >> $OUT
    echo "--- stderr lines mentioning Traceback/Error/SystemExit: $(grep -c -E 'Traceback|Error|SystemExit' $TMPE)" >> $OUT
    grep -E 'Traceback|SystemExit' $TMPE | head -5 >> $OUT
    echo >> $OUT
  done
done
rm -f $TMPO $TMPE
cat $OUT
