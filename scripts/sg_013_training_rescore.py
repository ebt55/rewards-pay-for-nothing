"""Re-score every logged GRPO training answer with securegrade 0.1.2 and 0.1.3 (14 Nov 2026).

Why: the external review (CODE-01) found that securegrade before 0.1.3 could give 1.0 to a loop test
that passed once and then crashed, exited or hung. Training used 0.1.0 (core runs) and 0.1.1 (H pair)
as the secure reward and as the observer's secure_all. This checks whether any logged training answer
was scored differently because of that.

Call shape = training's secure_all (jobs/grpo_train.py secure_score): securegrade.score(text,
test_list, setup_code="\n".join(test_imports)), default arguments otherwise. Training tasks have no
test_imports. Tests come from the local MBPP sanitized parquet cache (replay_release.load_mbpp).

    # score (resumable); SG_ROOT is a folder holding a securegrade/ package
    env -u PYTHONPATH CUDA_VISIBLE_DEVICES="" PYTHONDONTWRITEBYTECODE=1 nice -n 19 \
      ~/p9/tools/bin/python -B scripts/sg_013_training_rescore.py score --sg-root SG_ROOT --label 0.1.3
    # re-run disagreements serially (both versions), then the report
    ... scripts/sg_013_training_rescore.py recheck --sg012 DIR --sg013 DIR
    ... scripts/sg_013_training_rescore.py report

Raw per-answer rows (no completion text) go to ~/p9/rescore-2026-11-14/. The report carries run, line,
step, task_id and scores only, never completion text.
"""
import argparse
import collections
import concurrent.futures as cf
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RUNS = ["u-ship-s0", "u-ship-s1", "u-sec-s0", "u-sec-s1", "e-ship-s0", "e-ship-s1", "e-sec-s0", "e-sec-s1",
        "h-ship-s0", "h-sec-s0"]
WORK = Path.home() / "p9" / "rescore-2026-11-14"
OUT = ROOT / "results" / "securegrade-training-rescore-2026-11-14"
FULL = 0.999

_SG = None


def _init(sg_root):
    global _SG
    sys.path.insert(0, sg_root)
    import securegrade
    if not securegrade.__file__.startswith(sg_root):
        raise SystemExit(f"securegrade imported from {securegrade.__file__}, not {sg_root}")
    _SG = securegrade


def _score(job):
    key, text, tests, imports = job
    t0 = time.monotonic()
    try:
        r = _SG.score(text, list(tests), setup_code="\n".join(imports))
        return {"key": key, "score": float(r.score), "passed": r.passed, "total": r.total,
                "format_ok": r.format_ok, "secs": round(time.monotonic() - t0, 2),
                "fail0": (r.failures[0][:160] if r.failures else None)}
    except Exception as e:  # noqa: BLE001
        return {"key": key, "error": f"{type(e).__name__}: {str(e)[:200]}", "secs": round(time.monotonic() - t0, 2)}


def load_items():
    sys.path.insert(0, str(ROOT / "scripts"))
    import replay_release as rr
    tasks, _ = rr.load_mbpp()
    items = []
    for run in RUNS:
        p = ROOT / "jobs" / "runs" / run / "completions.jsonl"
        for line, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            r = json.loads(raw)
            t = tasks[int(r["task_id"])]
            items.append({"key": f"{run}:{line}", "run": run, "line": line, "step": r["step"],
                          "task_id": int(r["task_id"]), "text": r["text"], "tests": t["test_list"],
                          "imports": t["test_imports"], "logged": r.get("secure_all"),
                          "aligntune_ce": r.get("aligntune_ce"),
                          "train_reward": r.get("train_reward_recomputed")})
    return items


def guard():
    if sys.platform != "linux":
        sys.exit("Linux only")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "" or os.getpriority(os.PRIO_PROCESS, 0) < 19:
        sys.exit('run with CUDA_VISIBLE_DEVICES="" under nice -n 19')


def cmd_score(a):
    guard()
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"sg-{a.label}.jsonl"
    done = set()
    if out.exists():
        done = {json.loads(x)["key"] for x in out.read_text().splitlines() if x.strip()}
    items = [i for i in load_items() if i["key"] not in done]
    if a.limit:
        items = items[: a.limit]
    print(json.dumps({"label": a.label, "todo": len(items), "already": len(done)}), flush=True)
    t0 = time.monotonic()
    with out.open("a") as f, cf.ProcessPoolExecutor(a.workers, initializer=_init, initargs=(a.sg_root,)) as ex:
        jobs = ((i["key"], i["text"], i["tests"], i["imports"]) for i in items)
        for n, res in enumerate(ex.map(_score, jobs, chunksize=8), 1):
            f.write(json.dumps(res) + "\n")
            if n % 500 == 0:
                f.flush()
                print(json.dumps({"label": a.label, "done": n, "of": len(items),
                                  "elapsed_s": round(time.monotonic() - t0)}), flush=True)
    print(json.dumps({"label": a.label, "finished": len(items), "elapsed_s": round(time.monotonic() - t0)}), flush=True)


def _read(label):
    rows = {}
    for x in (WORK / f"sg-{label}.jsonl").read_text().splitlines():
        if x.strip():
            r = json.loads(x)
            rows[r["key"]] = r
    return rows


def _val(r):
    return None if r is None or "error" in r else r["score"]


def cmd_recheck(a):
    """Re-score, serially and twice per version, every answer where 0.1.2 and 0.1.3 disagree or either errored."""
    guard()
    s12, s13 = _read("0.1.2"), _read("0.1.3")
    items = {i["key"]: i for i in load_items()}
    keys = sorted(k for k in items if _val(s12.get(k)) != _val(s13.get(k)) or _val(s12.get(k)) is None)
    print(json.dumps({"recheck": len(keys)}), flush=True)
    res = {}
    for label, root in (("0.1.2", a.sg012), ("0.1.3", a.sg013)):
        with cf.ProcessPoolExecutor(1, initializer=_init, initargs=(root,)) as ex:
            for rep in range(2):
                for k, r in zip(keys, ex.map(_score, [(k, items[k]["text"], items[k]["tests"], items[k]["imports"])
                                                       for k in keys])):
                    res.setdefault(k, {}).setdefault(label, []).append(_val(r) if "error" not in r else r["error"])
    (WORK / "recheck.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({"rechecked": len(res)}), flush=True)


def cmd_report(_a):
    items = load_items()
    s12, s13 = _read("0.1.2"), _read("0.1.3")
    rech = json.loads((WORK / "recheck.json").read_text()) if (WORK / "recheck.json").exists() else {}
    rows = []
    for i in items:
        k = i["key"]
        v12, v13 = _val(s12.get(k)), _val(s13.get(k))
        stable = None
        if k in rech:
            r12, r13 = rech[k].get("0.1.2", []), rech[k].get("0.1.3", [])
            stable = (len(set(map(str, r12 + [v12]))) == 1) and (len(set(map(str, r13 + [v13]))) == 1)
        rows.append({"key": k, "run": i["run"], "line": i["line"], "step": i["step"], "task_id": i["task_id"],
                     "arm": "sec" if "-sec-" in i["run"] else "ship", "logged": i["logged"],
                     "aligntune_ce": i["aligntune_ce"], "train_reward": i["train_reward"],
                     "s012": v12, "s013": v13, "err012": (s12.get(k) or {}).get("error"),
                     "err013": (s13.get(k) or {}).get("error"), "recheck": rech.get(k), "stable": stable})

    def full(x):
        return x is not None and x >= FULL

    def diff(a, b):
        return a is not None and b is not None and abs(a - b) > 1e-9

    per_run = {}
    for run in RUNS:
        rr_ = [r for r in rows if r["run"] == run]
        per_run[run] = {
            "n": len(rr_),
            "logged_full": sum(full(r["logged"]) for r in rr_),
            "s012_full": sum(full(r["s012"]) for r in rr_),
            "s013_full": sum(full(r["s013"]) for r in rr_),
            "logged_vs_013_diff": sum(diff(r["logged"], r["s013"]) for r in rr_),
            "s012_vs_013_diff": sum(diff(r["s012"], r["s013"]) for r in rr_),
            "full_logged_not_013": sum(full(r["logged"]) and r["s013"] is not None and not full(r["s013"]) for r in rr_),
            "errors": sum(r["s012"] is None or r["s013"] is None for r in rr_),
        }
    d1213 = [r for r in rows if diff(r["s012"], r["s013"]) or (r["s012"] is None) != (r["s013"] is None)]
    dlog13 = [r for r in rows if diff(r["logged"], r["s013"])]
    overpaid = [r for r in dlog13 if r["s013"] < r["logged"]]
    underpaid = [r for r in dlog13 if r["s013"] > r["logged"]]
    tot = {k: sum(p[k] for p in per_run.values()) for k in next(iter(per_run.values()))}
    out = {"schema_version": 1, "date": "2026-11-14",
           "scope": "all logged GRPO training answers of the 10 runs (jobs/runs/*/completions.jsonl); MBPP sanitized "
                    "test_list, training's secure_all call shape; logged = secure_all as logged in training "
                    "(securegrade 0.1.0 core runs, 0.1.1 H pair, on the training containers (HF Jobs for the eight core runs, RunPod for the H pair))",
           "runtime": {"python": sys.version.split()[0], "kernel": platform.release()},
           "inputs_sha256": {f"jobs/runs/{r}/completions.jsonl": hashlib.sha256(
               (ROOT / "jobs" / "runs" / r / "completions.jsonl").read_bytes()).hexdigest() for r in RUNS},
           "totals": tot, "per_run": per_run,
           "diff_012_vs_013": [{k: r[k] for k in ("key", "run", "step", "task_id", "arm", "logged", "s012", "s013",
                                                  "err012", "err013", "recheck", "stable")} for r in d1213],
           "logged_vs_013_overpaid_count": len(overpaid), "logged_vs_013_underpaid_count": len(underpaid),
           "logged_vs_013_overpaid": [{k: r[k] for k in ("key", "arm", "step", "task_id", "logged", "s012", "s013",
                                                         "aligntune_ce", "train_reward")} for r in overpaid]}
    OUT.with_suffix(".json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"totals": tot, "diff_012_vs_013": len(d1213), "overpaid": len(overpaid),
                      "underpaid": len(underpaid)}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--sg-root", required=True)
    s.add_argument("--label", required=True)
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--limit", type=int, default=0)
    r = sub.add_parser("recheck")
    r.add_argument("--sg012", required=True)
    r.add_argument("--sg013", required=True)
    sub.add_parser("report")
    a = ap.parse_args()
    if getattr(a, "workers", 4) > 4:
        sys.exit("at most 4 workers")
    {"score": cmd_score, "recheck": cmd_recheck, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
