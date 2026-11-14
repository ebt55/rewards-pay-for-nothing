"""securegrade 0.1.3 reference compatibility (14 Nov 2026 review fixes), same cells as sg_012_references.py.

Grades the 591 cached supplied references (fenced, bare, and HumanEval body + prompt: 1,346 cells) with
sg_fn_rate.grade(), then compares every cell with the accepted 0.1.2 run in
results/memread-2026-11-08/references-012.json. Cached tasks only; no network. Linux/WSL only.

    CUDA_VISIBLE_DEVICES="" nice -n 19 ~/p9/tools/bin/python -B scripts/sg_013_references.py \
        --workers 2 --output results/securegrade-013-references-2026-11-14.json
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

BASELINE = ROOT / "results" / "memread-2026-11-08" / "references-012.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--workers", type=int, default=2, choices=range(1, 5))
    args = parser.parse_args()
    if sys.platform != "linux" or securegrade.__version__ != "0.1.3":
        raise SystemExit("requires Linux and securegrade 0.1.3")
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
        r = previous.grade(task, text, prompt)
        return {"task": task["task_id"], "kind": task["kind"], "label": label, "score": r.score,
                "all_passed": r.all_passed, "passed": r.passed, "total": r.total, "failures": r.failures[:3],
                "harness_aborted": r.detail.get("harness_aborted"), "child": r.detail.get("child"),
                "helpers_from_candidate": r.detail.get("helpers_from_candidate"),
                "isolation": r.detail.get("isolation")}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run, jobs))
    base = json.loads(BASELINE.read_text())
    old = {(r["task"], r["label"]): (r["score"], r["all_passed"]) for r in base["rows"]}
    changed = [{"task": r["task"], "label": r["label"], "old": old.get((r["task"], r["label"])),
                "new": (r["score"], r["all_passed"])} for r in rows
               if old.get((r["task"], r["label"])) != (r["score"], r["all_passed"])]
    failed = [r for r in rows if not r["all_passed"] or r["score"] != 1.0]
    files = sorted((ROOT / "securegrade").glob("*.py")) + [pathlib.Path(__file__).resolve(),
                                                           ROOT / "scripts" / "sg_fn_rate.py"]
    out = {"version": securegrade.__version__, "kernel": platform.release(), "python": sys.version.split()[0],
           "interpreter": sys.executable, "workers": args.workers, "tasks": len(tasks), "reference_cells": len(rows),
           "accepted_reference_cells": len(rows) - len(failed), "rejected_reference_cells": len(failed),
           "seconds": round(time.monotonic() - started, 3),
           "vs_012": {"path": str(BASELINE.relative_to(ROOT)), "sha256": hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
                      "cells_compared": len(rows), "score_or_all_passed_changes": changed},
           "cells_with_candidate_helpers": sorted({(r["task"], r["label"]) for r in rows if r["helpers_from_candidate"]}),
           "cells_with_harness_abort": sum(bool(r["harness_aborted"]) for r in rows),
           "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
           "fixture_sha256": hashlib.sha256(previous.CACHE.read_bytes()).hexdigest(), "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("version", "reference_cells", "accepted_reference_cells",
                                          "rejected_reference_cells", "seconds", "cells_with_harness_abort")}
                     | {"changes_vs_012": len(changed)}), flush=True)
    if failed or changed:
        raise SystemExit("reference rejection or score change vs 0.1.2; inspect output")


if __name__ == "__main__":
    main()
