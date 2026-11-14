"""Cached reference compatibility using sg_fn_rate's existing grade() logic.

Writes only a new explicitly named output. Does not fetch tasks or overwrite historical data.
"""
import argparse
import hashlib
import json
import pathlib
import platform
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import sg_fn_rate as previous  # noqa: E402
import securegrade  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--workers", type=int, default=2, choices=range(1, 5))
    args = parser.parse_args()
    if sys.platform != "linux" or securegrade.__version__ != "0.1.2":
        raise SystemExit("requires Linux and securegrade 0.1.2")
    if not previous.CACHE.exists():
        raise SystemExit("cached tasks required; network loading is disabled")
    tasks = previous.load_tasks()
    if len(tasks) != 591:
        raise SystemExit("expected exactly 591 cached supplied references")
    jobs = []
    for task in tasks:
        jobs.append((task, "reference_fenced", "```python\n" + task["reference"] + "\n```", None))
        jobs.append((task, "reference_bare", task["reference"], None))
        if task["kind"] == "humaneval":
            jobs.append((task, "reference_body_with_prompt", task["body"], task["prompt"]))
    started = time.monotonic()

    def run(job):
        task, label, text, prompt = job
        result = previous.grade(task, text, prompt)
        return {"task": task["task_id"], "kind": task["kind"], "label": label,
                "score": result.score, "all_passed": result.all_passed, "passed": result.passed,
                "total": result.total, "failures": result.failures[:3],
                "isolation": result.detail.get("isolation")}

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(run, jobs):
            rows.append(row)
            if len(rows) % 100 == 0:
                print(f"completed {len(rows)}/{len(jobs)} reference cells", flush=True)
    historical_path = ROOT / "results" / "securegrade_fn.json"
    historical = json.loads(historical_path.read_text())
    recorded = {(row["task"], row["label"]): row["score"] for row in historical["rows"]
                if row["label"].startswith("reference")}
    changed = [{"task": row["task"], "label": row["label"], "old": recorded.get((row["task"], row["label"])),
                "new": row["score"]} for row in rows if recorded.get((row["task"], row["label"])) != row["score"]]
    failed = [row for row in rows if not row["all_passed"] or row["score"] != 1.0]
    baseline_path = ROOT / "results" / "release-reaudit-2026-11-08" / "securegrade-011-references.json"
    baseline = json.loads(baseline_path.read_text())
    baseline_scores = {(row["task"], "reference_fenced" if row["fenced"] else "reference_bare"): row["score"]
                       for row in baseline["rows"] if row["status"] == "scored"}
    if len(baseline_scores) != 1182:
        raise SystemExit("expected frozen 0.1.1 baseline for 591 references in both formats")
    baseline_changed = [row for row in rows if row["label"] != "reference_body_with_prompt"
                        and baseline_scores.get((row["task"], row["label"])) != row["score"]]
    files = list((ROOT / "securegrade").glob("*.py")) + [pathlib.Path(__file__).resolve(), ROOT / "scripts" / "sg_fn_rate.py"]
    output = {"version": securegrade.__version__, "kernel": platform.release(), "workers": args.workers,
              "tasks": len(tasks), "reference_cells": len(rows), "rejected_reference_cells": len(failed),
              "seconds": round(time.monotonic() - started, 3), "observed_historical_score_changes": changed,
              "observed_011_score_changes": len(baseline_changed),
              "frozen_011_comparison": {"path": str(baseline_path.relative_to(ROOT)),
                                        "sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
                                        "scope": "591 supplied references in both formats; 1182 cells"},
              "historical_comparison": {"path": str(historical_path.relative_to(ROOT)),
                                        "sha256": hashlib.sha256(historical_path.read_bytes()).hexdigest(),
                                        "scope": "recorded sg_fn_rate reference rows, including HE body+prompt"},
              "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
              "fixture_sha256": hashlib.sha256(previous.CACHE.read_bytes()).hexdigest(), "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=1) + "\n")
    print(json.dumps({key: output[key] for key in ("version", "tasks", "reference_cells", "rejected_reference_cells", "seconds")}), flush=True)
    if failed or changed or baseline_changed:
        raise SystemExit("reference rejection or observed score change; inspect output")


if __name__ == "__main__":
    main()
