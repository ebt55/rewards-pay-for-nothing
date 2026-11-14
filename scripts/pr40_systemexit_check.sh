#!/bin/bash
# AlignTune PR #40: does an exiting completion end a TRL run? Each case in a fresh throwaway process,
# env -i (no tokens in the driver's environment), gentle mode. Two parts, each on 0.1.28 (installed in
# ~/p9/at) and on the PR clone:
#  A. Gate 1's own driver, unchanged (scripts/systemexit_trl_driver.py); the PR is loaded by PYTHONPATH.
#  B. scripts/pr40_systemexit_trl_driver.py: more middle completions and rewards with tests.
#   bash scripts/pr40_systemexit_check.sh
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
cd $P
OUT=${OUT:-results/aligntune-pr40/systemexit_trl.txt}
PRSRC=${PR40_SRC_PR:-$HOME/scratch/aligntune-pr40/src}
TMPO=$(mktemp -p $HOME/p9/tmp); TMPE=$(mktemp -p $HOME/p9/tmp)
E="env -i HOME=$HOME PATH=$HOME/p9/at/bin:/usr/bin:/bin CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=4 MKL_NUM_THREADS=4"
record() {  # label, then the command
  echo "=== $1" >> $OUT
  shift
  timeout 300 "$@" > $TMPO 2> $TMPE
  echo "process exit status: $?" >> $OUT
  echo "--- stdout:" >> $OUT; grep -v "^\[aligntune\]" $TMPO | sed "s#$HOME#~#g" >> $OUT
  echo "--- stderr lines mentioning Traceback/Error/SystemExit: $(grep -c -E 'Traceback|Error|SystemExit' $TMPE)" >> $OUT
  grep -E 'Traceback|SystemExit' $TMPE | head -5 >> $OUT
  echo >> $OUT
}
: > $OUT
echo "# Part A: Gate 1 driver unchanged (recipe's code_execution, weight 0.2, via RewardBridge; no tests in the row)" >> $OUT
for src in installed pr; do
  if [ $src = pr ]; then PP="PYTHONPATH=$PRSRC"; lab="PR #40 clone"; else PP=""; lab="0.1.28 (installed)"; fi
  echo "--- import check ($lab): $($E $PP $HOME/p9/at/bin/python -W ignore -c 'import aligntune.rewards.core as c; print(c.__file__)' 2>/dev/null | tail -1 | sed "s#$HOME#~#g")" >> $OUT
  for a in none 0 3; do
    record "aligntune $lab | Gate 1 driver | middle: $([ $a = none ] && echo 'stub (control)' || echo "sys.exit($a)")" \
      $E $PP nice -n 19 $HOME/p9/at/bin/python -W ignore scripts/systemexit_trl_driver.py $a
  done
done
echo "# Part B: extended driver (4 rewards; middle completion varied)" >> $OUT
for src in installed "$PRSRC"; do
  lab=$([ $src = installed ] && echo '0.1.28 (installed)' || echo 'PR #40 clone')
  for a in none exit0 exit3 os_exit0 kill_parent; do
    record "aligntune $lab | extended driver | middle: $a" \
      $E PR40_SRC=$src nice -n 19 $HOME/p9/at/bin/python -W ignore scripts/pr40_systemexit_trl_driver.py $a
  done
done
rm -f $TMPO $TMPE
cat $OUT
