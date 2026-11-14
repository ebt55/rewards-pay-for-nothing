"""Create, inspect and end RunPod pods for P9 runs (REST API v1). The API key is read from a file and never printed.

    python -I scripts/runpod_pods.py create <run> "<grpo_train.py args>"
    python -I scripts/runpod_pods.py status <pod_id> [<pod_id> ...]
    python -I scripts/runpod_pods.py list
    python -I scripts/runpod_pods.py end <pod_id> [<pod_id> ...]
    python -I scripts/runpod_pods.py watch <run>=<pod_id> [<run>=<pod_id> ...]   (backstop off switch)

Key file: %USERPROFILE%\\.runpod\\.env with the line RUNPOD_API_KEY=<key> (filled in by Ebin; it lives outside the
project so it can never be published with the repo). The pod gets HF_TOKEN from the RunPod secret
`hf_token`; this script only passes the secret's name. Pods boot jobs/runpod_start.sh from the private bucket.
"""
import json
import pathlib
import sys
import urllib.error
import urllib.request

for _s in (sys.stdout, sys.stderr):  # pod log lines carry ✓ and █; cp1252 crashed the 5 Nov rp-smoke4 watcher mid-run
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

API = "https://rest.runpod.io/v1"
KEY_FILE = pathlib.Path.home() / ".runpod" / ".env"
IMAGE = "ghcr.io/astral-sh/uv:python3.12-bookworm"  # same tag as the HF Jobs runs
# The pod's start command: put the token in a 0600 file (printf is a builtin, so it never appears in argv), fetch the
# bootstrap, and exec it WITHOUT HF_TOKEN in its environment. If the fetch fails, the pod ends itself.
# Self-delete: REST v1 first, then the v2 path the RunPod docs use with the pod-scoped key (pods/manage-pods).
SELF_END = ("python3 -c '\n"
            'import os, urllib.request as u\n'
            'p, k = os.environ.get("RUNPOD_POD_ID", ""), os.environ.get("RUNPOD_API_KEY", "")\n'
            'def d(url):\n'
            '    try:\n'
            '        return str(u.urlopen(u.Request(url, method="DELETE", headers={"Authorization": "Bearer " + k, '
            '"User-Agent": "p9-runpod-helper/1.0"}), timeout=30).status)\n'
            '    except Exception as e:\n'
            '        return type(e).__name__ + str(getattr(e, "code", ""))\n'
            'if not p or not k:\n'
            '    print("RUNPOD self-end: no pod id or pod key")\n'
            'else:\n'
            '    s = d("https://rest.runpod.io/v1/pods/" + p)\n'
            '    print("RUNPOD self-end v1", s, "" if s.startswith("2") else "v2 " + d("https://api.runpod.io/v2/pods/" + p))\n'
            "' || true")
UA = "p9-runpod-helper/1.0"
# The 4 Nov smoke pod sat RUNNING for 25 min with nothing in the bucket and RunPod listed no secrets, so the boot now
# says plainly when the secret did not arrive, and ends the pod before trying the bucket.
BOOT = ('set -u; umask 077; mkdir -p /in/jobs; echo "RUNPOD_BOOT $(date -u +%FT%TZ) pod ${RUNPOD_POD_ID:-?}"; '
        f'case "${{HF_TOKEN:-}}" in ""|*RUNPOD_SECRET*) echo RUNPOD_NO_SECRET; {SELF_END}; sleep infinity;; esac; '
        'printf %s "${HF_TOKEN:-}" > /tmp/.p9tok; '
        'if uvx --from huggingface_hub==2.4.0 hf buckets cp hf://buckets/ebt005/p9-grpo-smoke/jobs/runpod_start.sh '
        '/in/jobs/runpod_start.sh; then exec env -u HF_TOKEN bash /in/jobs/runpod_start.sh; '
        f'else echo RUNPOD_FETCH_FAILED; rm -f /tmp/.p9tok; {SELF_END}; sleep infinity; fi')
BUCKET = "ebt005/p9-grpo-smoke"


def key():
    try:
        lines = KEY_FILE.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        sys.exit(f"no RunPod key file at {KEY_FILE}")
    for ln in lines:
        name, sep, val = ln.strip().partition("=")
        if sep and name.strip() == "RUNPOD_API_KEY":
            k = val.strip().strip('"').strip("'")
            if k and not any(c.isspace() for c in k):
                return k
    sys.exit(f"{KEY_FILE} needs a line RUNPOD_API_KEY=<your key> (no spaces)")


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {key()}", "Content-Type": "application/json",
                                          "User-Agent": UA})  # Cloudflare blocks urllib's default UA (error 1010)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "replace")[:600]}


def pod_body(run, args, cloud="COMMUNITY", vcpu=8, ram=30, gpu="NVIDIA L4"):
    return {
        "name": f"p9-{run}", "imageName": IMAGE, "gpuTypeIds": [gpu], "gpuCount": 1,
        "cloudType": cloud, "allowedCudaVersions": ["13.0"],  # torch 2.11.0+cu130 needs a CUDA 13 driver
        "minVCPUPerGPU": vcpu, "minRAMPerGPU": ram,  # HF l4x1 had 8 vCPU / 30 GB; securegrade children need the CPU
        "containerDiskInGb": 80, "volumeInGb": 0,  # no volume: nothing is billed once the pod ends
        "env": {"HF_TOKEN": "{{ RUNPOD_SECRET_hf_token }}", "P9_RUN": run, "P9_ARGS": args},
        "dockerEntrypoint": ["bash", "-c"], "dockerStartCmd": [BOOT],
    }


def cpu_check_body(run, flavors=("cpu3c", "cpu5c", "cpu3g", "cpu5g")):
    """A 2-vCPU CPU pod that runs the same boot path (secret, bucket fetch, boot marker, code pull, self-end) and stops
    before training (P9_STOP_AFTER=pull). Costs cents and needs no CUDA 13 GPU host."""
    return {
        "name": f"p9-{run}", "imageName": IMAGE, "computeType": "CPU",
        "cpuFlavorIds": list(flavors), "cpuFlavorPriority": "custom", "vcpuCount": 2,
        "containerDiskInGb": 20, "volumeInGb": 0,
        "env": {"HF_TOKEN": "{{ RUNPOD_SECRET_hf_token }}", "P9_RUN": run, "P9_ARGS": "check", "P9_STOP_AFTER": "pull"},
        "dockerEntrypoint": ["bash", "-c"], "dockerStartCmd": [BOOT],
    }


LOG_DIR = pathlib.Path.home() / ".runpod" / "logs"  # outside the project, so pod logs are never published
_SECRETISH = None


def redact(s):
    global _SECRETISH
    if _SECRETISH is None:
        import re
        _SECRETISH = re.compile(r"(hf_[A-Za-z0-9]{8,}|rpa_[A-Za-z0-9]{8,}|(?i:bearer)\s+\S+)")
    return _SECRETISH.sub("[REDACTED]", s)


def pod_logs(pid, tail=300, secs=12):
    """Read the pod's container and system logs (REST v2 SSE stream, docs: api-reference-v2/pods/stream-pod-logs) for
    up to `secs` seconds. Returns [(ts, source, line)] with anything token-like redacted, or None on an HTTP error."""
    import socket
    import time
    req = urllib.request.Request(f"https://api.runpod.io/v2/pods/{pid}/logs?tail={tail}",
                                 headers={"Authorization": f"Bearer {key()}", "User-Agent": UA,
                                          "Accept": "text/event-stream"})
    out, t0 = [], time.time()
    try:
        with urllib.request.urlopen(req, timeout=secs) as f:
            while time.time() - t0 < secs:
                raw = f.readline()
                if not raw:
                    break
                s = raw.decode("utf-8", "replace").strip()
                if not s.startswith("data:"):
                    continue
                try:
                    d = json.loads(s[5:].strip())
                except ValueError:
                    continue
                out.append((str(d.get("ts", "")), str(d.get("source", "")), redact(str(d.get("line", "")))))
    except urllib.error.HTTPError:
        return None
    except (socket.timeout, TimeoutError, urllib.error.URLError, ConnectionError, OSError):
        pass  # the stream stays open for live lines; a read timeout just ends this sample
    return out


def create(run, args, cloud="COMMUNITY", vcpu=8, ram=30, gpu="NVIDIA L4"):
    st, out = call("POST", "/pods", pod_body(run, args, cloud, vcpu, ram, gpu))
    if st >= 300:
        sys.exit(f"create {run}: HTTP {st} {out.get('error', out)}")
    print(f"{run}: pod {out.get('id')} {cloud} {gpu} costPerHr {out.get('costPerHr')} status {out.get('desiredStatus')} "
          f"vcpu {out.get('vcpuCount')} ram {out.get('memoryInGb')}")


def status(pid):
    st, out = call("GET", f"/pods/{pid}")
    if st >= 300:
        print(f"{pid}: HTTP {st} {out.get('error', '')[:200]}")
        return
    keep = ("name", "desiredStatus", "costPerHr", "lastStatusChange", "uptimeSeconds")
    print(pid, {k: out.get(k) for k in keep}, "gpu", (out.get("gpu") or {}).get("displayName", out.get("gpuTypeId")))


def bucket_files(run):
    import subprocess
    r = subprocess.run(["hf", "buckets", "list", f"{BUCKET}/runs/{run}", "-R"], capture_output=True, text=True)
    return [ln.split()[-1] for ln in r.stdout.splitlines() if ln.strip() and ln.strip() != "(empty)"] if r.returncode == 0 else None


def watch(pairs, poll=300, max_h=4.5, no_boot_min=25, grace_min=10, exit=True):
    """Backstop: end each pod when its run's summary.json has been in the bucket for grace_min, when no boot marker
    appeared within no_boot_min, or after max_h. Exit 0 if every run finished, 3 otherwise."""
    import time
    t0, live, done_at, finished, host_failed = time.time(), dict(pairs), {}, set(), set()
    seen = {run: set() for run in pairs}
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    while live:
        mins = (time.time() - t0) / 60
        for run, pid in list(live.items()):
            st, out = call("GET", f"/pods/{pid}")
            state = "GONE" if st == 404 else (out.get("desiredStatus") if st < 300 else f"HTTP{st}")
            files = bucket_files(run)
            n = "?" if files is None else len(files)
            summary = bool(files) and any(f.endswith("summary.json") for f in files)
            if summary:
                finished.add(run)
                done_at.setdefault(run, mins)
            logs = pod_logs(pid) if state not in ("GONE", "TERMINATED") else []
            new = [x for x in (logs or []) if x not in seen[run]]
            seen[run].update(new)
            if new:
                with open(LOG_DIR / f"{run}-{pid}.log", "a", encoding="utf-8") as fh:
                    fh.writelines(f"{ts} {src} {line}\n" for ts, src, line in new)
            last = next((ln for _, src, ln in reversed(logs or []) if src == "container"), "")
            change = redact(str(out.get("lastStatusChange", "") if st < 300 else ""))[:70]
            print(f"{time.strftime('%H:%M')} {run} pod={state} files={n} summary={summary} "
                  f"logs={'?' if logs is None else len(logs)} status='{change}' last='{last[:90]}'", flush=True)
            reason = None
            if state in ("GONE", "TERMINATED"):
                del live[run]
                continue
            start_errors = sum(1 for _, src, ln in seen[run] if src == "system" and "error starting container" in ln)
            gpu_bad = any(src == "container" and "RUNPOD_GPU_BAD" in ln for _, src, ln in seen[run])
            if gpu_bad:  # runpod_start.sh's preflight: cuInit failed, so no run-once marker was written
                reason = "CUDA does not start on this host (gpu preflight)"
                host_failed.add(run)
            elif summary and mins - done_at[run] >= grace_min:
                reason = "run finished but the pod did not end itself"
            elif files is not None and not files and start_errors >= 3:  # 4 Nov: a host looped on `runc create failed`
                reason = f"host could not start the container ({start_errors} tries)"
                host_failed.add(run)
            elif files is not None and not files and mins >= no_boot_min:
                reason = f"no boot marker after {no_boot_min} min"
            elif mins >= max_h * 60:
                reason = f"over {max_h} h"
            if reason:
                st, _ = call("DELETE", f"/pods/{pid}")
                print(f"ENDED {run} pod {pid}: {reason} (HTTP {st})", flush=True)
                del live[run]
        if live:
            time.sleep(poll)
    print("ALL DONE" if finished == set(pairs) else f"NOT FINISHED: {sorted(set(pairs) - finished)}")
    if not exit:
        return {"finished": finished, "host_failed": host_failed}
    sys.exit(0 if finished == set(pairs) else 3)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "create" and len(rest) >= 2:
        opts = dict(o.lstrip("-").split("=", 1) for o in rest[2:])  # --cloud=SECURE --vcpu=4 --ram=24 --gpu="NVIDIA L4"
        create(rest[0], rest[1], cloud=opts.get("cloud", "COMMUNITY"), vcpu=int(opts.get("vcpu", 8)),
               ram=int(opts.get("ram", 30)), gpu=opts.get("gpu", "NVIDIA L4"))
    elif cmd == "watch" and rest and all("=" in x for x in rest):
        watch(dict(x.split("=", 1) for x in rest))
    elif cmd == "cpucheck" and len(rest) in (1, 2):  # cpucheck rp-cpucheck1 [cpu5c,cpu3g]  (flavors in order)
        st, out = call("POST", "/pods", cpu_check_body(rest[0], *([rest[1].split(",")] if len(rest) == 2 else [])))
        if st >= 300 or not out.get("id"):
            sys.exit(f"cpucheck {rest[0]}: HTTP {st} {str(out.get('error', out))[:300]}")
        print(f"cpucheck {rest[0]}: pod {out['id']} ${out.get('costPerHr')}/h vcpu {out.get('vcpuCount')}", flush=True)
        watch({rest[0]: out["id"]}, poll=15, max_h=0.5, no_boot_min=12, grace_min=0)  # a check pod lives ~1 min
    elif cmd == "status" and rest:
        for p in rest:
            status(p)
    elif cmd == "list":
        st, out = call("GET", "/pods")
        for p in (out if isinstance(out, list) else out.get("pods", [])):
            print(p.get("id"), p.get("name"), p.get("desiredStatus"), p.get("costPerHr"))
    elif cmd == "end" and rest:
        for p in rest:
            st, out = call("DELETE", f"/pods/{p}")
            print(f"{p}: end -> HTTP {st}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
