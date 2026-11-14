"""Wait for RunPod capacity our stack can use, then start one run and watch it to the end.

    python -I scripts/runpod_wait.py <run> "<grpo_train.py args>" [--until=2026-11-06T18:00+05:30] [--every=20] [--cap=0.70]

Every --every minutes it tries the GPUs below in order (L4 first, the GPU of the 8 HF runs). Each try uses a CUDA 13.0
host (torch 2.11.0+cu130), at least 6 vCPU and 24 GB RAM, and bf16. A create that fails costs nothing. A pod priced
above --cap $/h is deleted at once. The first pod that fits becomes the run, and runpod_pods.watch then ends it
(exit 0 if the run finished, 3 if not). Exit 5 if nothing fits by --until.
"""
import datetime as dt
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # -I leaves the script dir off sys.path
import runpod_pods as r  # noqa: E402

# bf16-capable cards with at least 24 GB, in order of preference (same GPU as the 8 runs first, then by list price).
GPUS = [("NVIDIA L4", "COMMUNITY"), ("NVIDIA L4", "SECURE"),
        ("NVIDIA RTX A5000", "COMMUNITY"), ("NVIDIA GeForce RTX 3090", "COMMUNITY"), ("NVIDIA RTX A6000", "COMMUNITY"),
        ("NVIDIA GeForce RTX 4090", "COMMUNITY"), ("NVIDIA A40", "COMMUNITY"), ("NVIDIA RTX A5000", "SECURE"),
        ("NVIDIA GeForce RTX 3090", "SECURE"), ("NVIDIA RTX A6000", "SECURE"), ("NVIDIA A40", "SECURE"),
        ("NVIDIA L40", "COMMUNITY"), ("NVIDIA RTX 6000 Ada Generation", "COMMUNITY"),
        ("NVIDIA GeForce RTX 5090", "COMMUNITY")]


def secret_names():
    """Names (never values) of the account's RunPod secrets, via GraphQL. Empty set on any error."""
    import json
    import urllib.request
    req = urllib.request.Request("https://api.runpod.io/graphql", method="POST",
                                 data=json.dumps({"query": "query { myself { secrets { name } } }"}).encode(),
                                 headers={"Authorization": f"Bearer {r.key()}", "Content-Type": "application/json",
                                          "User-Agent": r.UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as f:
            me = (json.loads(f.read()).get("data") or {}).get("myself") or {}
        return {s.get("name") for s in (me.get("secrets") or [])}
    except Exception:  # noqa: BLE001
        return set()


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    run, args = sys.argv[1], sys.argv[2]
    opts = dict(o.lstrip("-").split("=", 1) for o in sys.argv[3:])
    until = dt.datetime.fromisoformat(opts.get("until", "2026-11-06T18:00+05:30"))
    every, cap = float(opts.get("every", 20)), float(opts.get("cap", 0.70))
    bad_machines, bad_types = set(), {}  # hosts whose container or CUDA failed; (gpu, cloud) -> retry-after time
    while True:
        now = dt.datetime.now(dt.timezone.utc)
        if "hf_token" not in secret_names():  # the 4 Nov smoke pod booted without it and could not reach the bucket
            print(f"{now:%m-%d %H:%M}Z waiting for the RunPod secret hf_token; next check in 5 min", flush=True)
            if now + dt.timedelta(minutes=5) > until:
                print(f"NO SECRET by {until.isoformat()}", flush=True)
                sys.exit(5)
            time.sleep(300)
            continue
        for gpu, cloud in GPUS:
            if bad_types.get((gpu, cloud), now) > now:
                continue
            st, out = r.call("POST", "/pods", r.pod_body(run, args, cloud=cloud, vcpu=6, ram=24, gpu=gpu))
            if st >= 300 or not out.get("id"):
                continue
            pid, price, machine = out["id"], float(out.get("costPerHr") or 99), out.get("machineId") or "?"
            if machine in bad_machines:
                d, _ = r.call("DELETE", f"/pods/{pid}")
                print(f"{now:%m-%d %H:%M}Z {gpu} {cloud} landed on failed host {machine}; deleted (HTTP {d})", flush=True)
                continue
            if price > cap:
                d, _ = r.call("DELETE", f"/pods/{pid}")
                print(f"{now:%m-%d %H:%M}Z {gpu} {cloud} at ${price}/h is over the cap; deleted (HTTP {d})", flush=True)
                continue
            print(f"STARTED {run}: pod {pid} {gpu} {cloud} ${price}/h vcpu {out.get('vcpuCount')} "
                  f"ram {out.get('memoryInGb')} machine {machine} at {now:%Y-%m-%d %H:%M}Z", flush=True)
            res = r.watch({run: pid}, poll=30, exit=False)  # 30 s polls catch the pod's last log lines
            if run in res["host_failed"]:  # container or CUDA never started, so the run name is still unused
                if machine != "?":
                    bad_machines.add(machine)
                else:  # no machine id in the create reply: skip this GPU type for 3 h instead
                    bad_types[(gpu, cloud)] = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)
                print(f"{now:%m-%d %H:%M}Z {gpu} {cloud} host {machine} failed (container or CUDA); trying the next GPU",
                      flush=True)
                continue
            sys.exit(0 if run in res["finished"] else 3)
        print(f"{now:%m-%d %H:%M}Z no CUDA 13 host with >= 24 GB free; next try in {every:g} min", flush=True)
        if now + dt.timedelta(minutes=every) > until:
            print(f"NO CAPACITY by {until.isoformat()}", flush=True)
            sys.exit(5)
        time.sleep(every * 60)


if __name__ == "__main__":
    main()
