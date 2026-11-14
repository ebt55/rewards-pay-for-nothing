"""M1: the Gate 1 exploit x task matrix, graded by securegrade (fenced and bare), plus the
cross-completion, exit and loop side checks. Writes results/m1/raw_securegrade.json. Gentle: 4 threads."""
import json, pathlib, sys, time
from concurrent.futures import ThreadPoolExecutor
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from securegrade import score  # noqa: E402
TASKS = json.loads((ROOT / "exploits" / "tasks.json").read_text())
EX = json.loads((ROOT / "exploits" / "exploits.json").read_text())


def render(e, t, fenced):
    if e["id"] == "reference":
        body = t["reference_solution"].strip()
    else:
        body = e["template"].replace("{fn}", t["entry_point"])
        if "{table}" in body:
            body = body.replace("{table}", repr({repr(tuple(v["args"])): v["expected"] for v in t["visible_examples"]}))
    return "```python\n" + body + "\n```" if fenced and e.get("fenceable", True) else body


def tests(t):
    if t["task_id"].startswith("HumanEval"):
        return t["raw_columns"]["test"], t["entry_point"], t["raw_columns"]["prompt"]
    return t["assert_tests"], None, None


jobs = [(t, e, f) for t in TASKS for e in EX["exploits"] for f in (True, False)]


def run(j):
    t, e, f = j
    tl, ep, prompt = tests(t)
    r = score(render(e, t, f), tl, entry_point=ep, setup_code=t["setup_code"], prompt=prompt, wall_timeout=10)
    return {"pkg": "securegrade", "reward": "securegrade", "mode": "tests", "task": t["task_id"], "exploit": e["id"],
            "fenced": f, "status": "ok", "score": r.score, "all_passed": r.all_passed, "failures": r.failures[:2],
            "isolation": r.detail.get("isolation")}


t0 = time.time()
with ThreadPoolExecutor(max_workers=4) as pool:
    cells = list(pool.map(run, jobs))
out = {"cells": cells, "seconds": round(time.time() - t0, 1),
       "isolation_seen": sorted({json.dumps(c["isolation"], sort_keys=True) for c in cells})}
(ROOT / "results" / "m1" / "raw_securegrade.json").write_text(json.dumps(out, indent=1))
print("securegrade cells", len(cells), "seconds", out["seconds"], out["isolation_seen"])
