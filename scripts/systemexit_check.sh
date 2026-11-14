#!/bin/bash
# Runs the SystemExit driver three ways and records exit status + output in results/systemexit_trl.txt
cd "$(dirname "${BASH_SOURCE[0]}")/.."   # repo root
OUT=${OUT:-results/systemexit_trl.txt}
: > $OUT
for a in none 0 3; do
  echo "=== middle completion: $( [ $a = none ] && echo 'stub (control)' || echo "sys.exit($a)" )" >> $OUT
  timeout 300 python -W ignore scripts/systemexit_trl_driver.py $a > /tmp/p9_se_out.txt 2> /tmp/p9_se_err.txt
  echo "process exit status: $?" >> $OUT
  echo "--- stdout:" >> $OUT; cat /tmp/p9_se_out.txt >> $OUT
  echo "--- stderr lines mentioning Traceback/Error/SystemExit: $(grep -c -E 'Traceback|Error|SystemExit' /tmp/p9_se_err.txt)" >> $OUT
  grep -E 'Traceback|SystemExit' /tmp/p9_se_err.txt | head -5 >> $OUT
  echo >> $OUT
done
rm -f /tmp/p9_se_out.txt /tmp/p9_se_err.txt
cat $OUT
