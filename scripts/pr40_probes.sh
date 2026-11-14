#!/bin/bash
# Runs each AlignTune PR #40 probe twice, each time in a fresh throwaway process with a minimal
# environment (env -i: no tokens in the grading process), gentle mode (nice 19, 4 threads, no GPU).
#   bash scripts/pr40_probes.sh [probe ...]
# Appends one JSON line per run to results/aligntune-pr40/probes.jsonl (with rep and exit status).
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
cd $P
[ -f scripts/pr40_probes.py ] || { echo "scripts/pr40_probes.py is held back until the open issues are confirmed fixed; see results/ for the class descriptions" >&2; exit 2; }
OUT=results/aligntune-pr40/probes.jsonl

PROBES=${@:-stdout_payload result_file_channel harness_patch type_tricks free_names parent_memory setsid_survivor cf_evalplus_forge deep_nesting decoder_cost parent_memory_all_mbpp}
mkdir -p $HOME/p9/tmp
for probe in $PROBES; do
  for rep in 1 2; do
    TMPO=$(mktemp -p $HOME/p9/tmp)
    extra=""
    env -i HOME=$HOME PATH=$HOME/p9/at/bin:/usr/bin:/bin CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 \
        PR40_SRC=${PR40_SRC:-$HOME/scratch/aligntune-pr40/src} timeout 1200 nice -n 19 $HOME/p9/at/bin/python -W ignore scripts/pr40_probes.py $probe $extra > $TMPO 2>/dev/null
    status=$?
    python3 - "$TMPO" "$probe" "$rep" "$status" >> $OUT <<'EOF'
import json, sys
path, probe, rep, status = sys.argv[1:]
lines = [l for l in open(path).read().splitlines() if l.startswith('{"probe"')]
rec = json.loads(lines[-1]) if lines else {"probe": probe, "result": None}
rec.update({"rep": int(rep), "exit_status": int(status)})
print(json.dumps(rec))
EOF
    echo "$probe rep $rep exit $status"
    rm -f $TMPO
  done
done
