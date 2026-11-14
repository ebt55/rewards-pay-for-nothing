#!/bin/bash
# RunPod bootstrap for one P9 run (4 Nov 2026). Same image and run_train.sh as the HF Jobs runs; only the launcher differs.
# Started by the pod's BOOT command (scripts/runpod_pods.py), which writes HF_TOKEN to /tmp/.p9tok (0600) and execs this
# script WITHOUT HF_TOKEN in its environment. Env: P9_RUN (run name), P9_ARGS (grpo_train.py args), RUNPOD_POD_ID and
# RUNPOD_API_KEY (pod-scoped, set by RunPod). P9_STOP_AFTER=pull (CPU check pods) stops after the code pull.
# - Pulls jobs/ and securegrade/ from the private bucket into /in, the same layout as the HF Jobs read-only mount.
# - Runs once per run name: refuses if runs/$P9_RUN already holds a BOOT-* marker or logs, and fails closed if it
#   cannot list the bucket. A marker is written before training, so a restart during install cannot start a second run.
# - The token is held in an unexported shell variable and passed per command; run_train.sh moves it to its own 0600
#   file and execs python without it.
# - Ends this pod on every exit path (trap). scripts/runpod_pods.py watch is the backstop.
set -uo pipefail
HUB="uvx --from huggingface_hub==2.4.0 hf"   # the version pinned in requirements-lock.txt
BUCKET=ebt005/p9-grpo-smoke
POD="${RUNPOD_POD_ID:-}"
BOOTLOG=/tmp/boot.log   # only this script's own lines; saved to the bucket when the pod ends before training starts
log() { echo "RUNPOD $(date -u +%FT%TZ) $*" | tee -a "$BOOTLOG"; }

end_pod() {
  trap - EXIT
  log "ending pod ${POD:-?}"
  if [ -n "${TOK:-}" ] && [ -n "${P9_RUN:-}" ]; then  # the token is cleared once training starts; run_train.sh uploads job.log
    HF_TOKEN="$TOK" $HUB buckets cp "$BOOTLOG" "hf://buckets/$BUCKET/runs/$P9_RUN/boot-${POD:-unknown}.log" >/dev/null 2>&1 || true
  fi
  TOK=""
  # Give the local watcher (30 s polls of the pod log stream) time to read the last lines before the pod disappears;
  # the 4 Nov rp-smoke1 pod ended between two reads and its failure lines were lost. Costs well under a cent.
  [ "${P9_STOP_AFTER:-}" = "pull" ] || { log "waiting 60 s so the watcher can read the final log lines"; sleep 60; }
  if [ -n "$POD" ] && command -v runpodctl >/dev/null 2>&1; then
    runpodctl remove pod "$POD" >/dev/null 2>&1 && log "ended via runpodctl"
  fi
  python3 - <<'PY'
import json, os, urllib.request
pod, key = os.environ.get("RUNPOD_POD_ID", ""), os.environ.get("RUNPOD_API_KEY", "")
if not pod or not key:
    print("RUNPOD no pod id or pod key; the local watcher ends this pod"); raise SystemExit
calls = [("DELETE", f"https://rest.runpod.io/v1/pods/{pod}", None),
         ("DELETE", f"https://api.runpod.io/v2/pods/{pod}", None),  # the path RunPod's docs use with the pod key
         ("POST", "https://api.runpod.io/graphql",
          json.dumps({"query": 'mutation { podTerminate(input: {podId: "%s"}) }' % pod}).encode())]
for method, url, body in calls:
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "User-Agent": "p9-runpod-helper/1.0"})  # Cloudflare blocks urllib's default UA
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"RUNPOD end call {method} {url.split('/')[2]} -> {r.status}")
            if r.status < 300:
                break
    except Exception as e:  # noqa: BLE001 -- report the failure type only, never the key
        print(f"RUNPOD end call {method} {url.split('/')[2]} failed: {type(e).__name__} {getattr(e, 'code', '')}")
PY
  sleep infinity  # if the pod is still alive, never exit: an exit could restart the container and the run
}
trap end_pod EXIT

TOK="$(cat /tmp/.p9tok 2>/dev/null || true)"
rm -f /tmp/.p9tok
# BOOT set umask 077 only to write the token file. Back to the default 022 (as on HF Jobs) from here: securegrade runs
# each candidate as an unprivileged uid, which must be able to run /venv/bin/python. The 4 Nov rp-smoke2 run made
# /venv under 077, so every candidate failed to start and securegrade's start-up self_check stopped the run.
umask 022
log "boot pod ${POD:-?} run ${P9_RUN:-?} kernel $(uname -r)"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
if [ -z "$TOK" ] || [[ "$TOK" == *RUNPOD_SECRET* ]]; then
  log "HF token missing or the RunPod secret was not substituted"; end_pod
fi
if [ -z "${P9_RUN:-}" ] || [ -z "${P9_ARGS:-}" ]; then log "P9_RUN or P9_ARGS missing"; end_pod; fi

# GPU preflight before the run-once marker, so a broken host costs a minute and leaves the run name unused. 5 Nov:
# rp-smoke3 (A6000) had a working nvidia-smi but torch failed with "CUDA unknown error". cuInit through the driver
# library (no installs) tells a host fault (non-zero here) from a problem in our stack (zero here, torch fails later).
if [ "${P9_STOP_AFTER:-}" != "pull" ]; then
  cu="$(python3 -I -c 'import ctypes
try:
    c = ctypes.CDLL("libcuda.so.1")
except OSError as e:
    print("no libcuda:", str(e)[:120]); raise SystemExit
n = ctypes.c_int(0)
r = c.cuInit(0)
print("cuInit", r, "count", c.cuDeviceGetCount(ctypes.byref(n)) if r == 0 else "-", "devices", n.value)' 2>&1 | tail -1 | cut -c1-200)"
  log "gpu preflight: $cu; nvidia device nodes: $(ls /dev | grep -c '^nvidia') (uvm $([ -e /dev/nvidia-uvm ] && echo yes || echo no))"
  case "$cu" in
    "cuInit 0 count 0 devices "[1-9]*) ;;
    *) log "RUNPOD_GPU_BAD: CUDA does not start on this host; ending the pod before the run-once marker"; end_pod;;
  esac
fi

# Run once: list the run folder (exit 0 with empty output when it does not exist yet; non-zero on auth or bucket errors).
if ! listing="$(HF_TOKEN="$TOK" $HUB buckets list "$BUCKET/runs/$P9_RUN" -R 2>&1)"; then
  log "cannot list runs/$P9_RUN in the bucket; failing closed"; end_pod
fi
if grep -q "BOOT-\|steps.jsonl\|job.log" <<<"$listing"; then
  log "runs/$P9_RUN already has a boot marker or logs; not starting a second time"; end_pod
fi
echo "pod ${POD:-?} booted $(date -u +%FT%TZ)" > /tmp/bootmark
HF_TOKEN="$TOK" $HUB buckets cp /tmp/bootmark "hf://buckets/$BUCKET/runs/$P9_RUN/BOOT-${POD:-unknown}" >/dev/null \
  || { log "could not write the boot marker; failing closed"; end_pod; }

mkdir -p /in
for d in jobs securegrade; do
  HF_TOKEN="$TOK" $HUB buckets sync "hf://buckets/$BUCKET/$d" "/in/$d" --exclude "*__pycache__*" >/dev/null \
    || { log "sync of $d failed"; end_pod; }
done
log "code pulled: $(ls /in/jobs | wc -l) jobs files, securegrade $(grep -o '"[0-9.]*"' /in/securegrade/__init__.py | tail -1)"
if [ "${P9_STOP_AFTER:-}" = "pull" ]; then
  # Check mode also proves the token can read the gated model (one small file) before a GPU is rented.
  if HF_TOKEN="$TOK" $HUB download CohereLabs/tiny-aya-global config.json --local-dir /tmp/modelcheck >/tmp/mc.out 2>&1; then
    log "check mode: gated model readable"
  else
    log "check mode: CANNOT read CohereLabs/tiny-aya-global with this token. Error tail:"
    grep -v '^\s*$' /tmp/mc.out | tail -4 | sed -E 's/hf_[A-Za-z0-9]{8,}/[REDACTED]/g' | cut -c1-300 | while IFS= read -r ln; do log "  $ln"; done
  fi
  HF_TOKEN="$TOK" $HUB auth whoami 2>&1 | sed -E 's/hf_[A-Za-z0-9]{8,}/[REDACTED]/g' | head -3 | while IFS= read -r ln; do log "  whoami: $ln"; done
  # securegrade's start-up self_check in an empty venv made under each umask (seconds, no installs): expected
  # ok false under 077 (the rp-smoke2 failure) and ok true under 022, with the isolation layers this host allows.
  for m in 077 022; do
    if ! ( umask "$m"; uv venv "/tmp/sg$m" --python 3.12 -q ) >/dev/null 2>&1; then log "check mode: uv venv under umask $m failed"; continue; fi
    sc="$("/tmp/sg$m/bin/python" -I -c 'import json, sys
sys.path.insert(0, "/in")
import securegrade
try:
    r = securegrade.self_check()
except Exception as e:
    r = {"ok": False, "error": repr(e)[:300]}
print(json.dumps(r))' 2>&1 | tail -1 | cut -c1-700)"
    log "check mode: securegrade self_check, venv made under umask $m: $sc"
  done
  log "check mode: bucket read, boot marker write and code pull work; stopping before training"; end_pod
fi
# The token goes in the child's environment only (never in argv, where /proc/<pid>/cmdline would show it to everyone).
# run_train.sh then execs python without it. A 4 h watchdog replaces `timeout`, whose argv would hold the token.
# shellcheck disable=SC2086  # P9_ARGS is a plain word list (no spaces inside any argument)
HF_TOKEN="$TOK" bash /in/jobs/run_train.sh "$P9_RUN" $P9_ARGS &
child=$!
TOK=""
( sleep 4h; log "4 h watchdog: stopping the run"; kill -TERM "$child" 2>/dev/null ) &
watchdog=$!
wait "$child"
rc=$?
kill "$watchdog" 2>/dev/null
log "run_train.sh exited with $rc"
if [ "$rc" != 0 ]; then  # an early exit uploads nothing; its start-up events (no secrets) say why, e.g. the self_check result
  grep -hE '"event": "(start|securegrade[a-z_]*|model_downloaded)"' "/tmp/run/$P9_RUN/events.jsonl" 2>/dev/null \
    | cut -c1-800 | while IFS= read -r ln; do log "  event: $ln"; done
fi
end_pod
