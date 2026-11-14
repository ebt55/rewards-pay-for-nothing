#!/bin/bash
# Runs each SafeTune PR #32 probe twice, each time in a fresh throwaway process with a minimal
# environment (env -i: no tokens in the grading process), gentle mode (nice 19, 4 threads, no GPU).
#   bash scripts/pr32_probes.sh [probe ...]
# Appends one JSON line per run to results/safetune-pr32/probes.jsonl (with rep and exit status).
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
cd $P
[ -f scripts/pr32_probes.py ] || { echo "scripts/pr32_probes.py is held back until the open issues are confirmed fixed; see results/ for the class descriptions" >&2; exit 2; }
OUT=results/safetune-pr32/probes.jsonl
CASES=results/safetune-pr32/free_name_cases.json
PROBES=${@:-stdout_payload result_file_channel harness_patch type_tricks free_names setsid_survivor deep_nesting decoder_cost}
mkdir -p $HOME/p9/tmp
for probe in $PROBES; do
  for rep in 1 2; do
    TMPO=$(mktemp -p $HOME/p9/tmp)
    extra=""; [ "$probe" = free_names ] && extra=$CASES
    env -i HOME=$HOME PATH=$HOME/p9/st/bin:/usr/bin:/bin CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 \
        PR32_SRC=${PR32_SRC:-$HOME/scratch/safetune-pr32/src} timeout 1200 nice -n 19 $HOME/p9/st/bin/python -W ignore scripts/pr32_probes.py $probe $extra > $TMPO 2>/dev/null
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
