"""securegrade false-negative rate on reference solutions, and exploit scores, over all of
MBPP-sanitized (427 tasks, all splits) and HumanEval (164 tasks).

Usage (tools venv, which has `datasets`):  python scripts/sg_fn_rate.py
Writes exploits/tasks_all.json (cached task data) and results/securegrade_fn.json.
"""
import json
import pathlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from securegrade import score  # noqa: E402

CACHE = ROOT / "exploits" / "tasks_all.json"


def load_tasks():
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    from datasets import load_dataset
    tasks = []
    for split in ["train", "test", "validation", "prompt"]:
        for r in load_dataset("google-research-datasets/mbpp", "sanitized", split=split):
            tasks.append({"task_id": f"MBPP/{r['task_id']}", "kind": "mbpp", "split": split, "prompt": r["prompt"],
                          "reference": r["code"], "tests": list(r["test_list"]),
                          "setup": "\n".join(r["test_imports"] or []), "entry_point": None})
    for r in load_dataset("openai/openai_humaneval", split="test"):
        tasks.append({"task_id": r["task_id"], "kind": "humaneval", "split": "test", "prompt": r["prompt"],
                      "reference": r["prompt"] + r["canonical_solution"], "body": r["canonical_solution"],
                      "tests": r["test"], "setup": "", "entry_point": r["entry_point"]})
    tasks.sort(key=lambda t: (t["kind"], int(t["task_id"].split("/")[1])))
    CACHE.write_text(json.dumps(tasks))
    return tasks


def mbpp_entry(t):
    import re
    m = re.search(r"assert\s+(?:\w+\()*?\s*(\w+)\(", t["tests"][0])
    return None


def grade(t, text, prompt=None):
    return score(text, t["tests"], entry_point=t["entry_point"], setup_code=t["setup"],
                 prompt=prompt, wall_timeout=10.0)


def main():
    tasks = load_tasks()
    ex = json.loads((ROOT / "exploits" / "exploits.json").read_text())
    nothing = [e for e in ex["exploits"] if e["solves_nothing"]]
    jobs = []
    for t in tasks:
        ep = t["entry_point"]
        jobs.append((t, "reference_fenced", "```python\n" + t["reference"] + "\n```", None))
        jobs.append((t, "reference_bare", t["reference"], None))
        if t["kind"] == "humaneval":
            jobs.append((t, "reference_body_with_prompt", t["body"], t["prompt"]))
        for e in nothing:
            fn = ep or _guess_name(t)
            body = e["template"].replace("{fn}", fn)
            text = body if not e.get("fenceable", True) else "```python\n" + body + "\n```"
            jobs.append((t, "exploit:" + e["id"], text, None))
    t0 = time.time()

    def run(j):
        t, label, text, prompt = j
        r = grade(t, text, prompt)
        return {"task": t["task_id"], "kind": t["kind"], "label": label, "score": r.score, "passed": r.passed,
                "total": r.total, "all_passed": r.all_passed, "format_ok": r.format_ok,
                "failures": r.failures[:3], "detail": {k: v for k, v in r.detail.items() if k != "isolation"},
                "isolation": r.detail.get("isolation")}

    with ThreadPoolExecutor(max_workers=4) as pool:  # gentle: at most 4 candidate processes
        rows = list(pool.map(run, jobs))
    out = {"n_tasks": {"mbpp": sum(t["kind"] == "mbpp" for t in tasks), "humaneval": sum(t["kind"] == "humaneval" for t in tasks)},
           "seconds": round(time.time() - t0, 1), "rows": rows}
    summ = {}
    for r in rows:
        k = (r["kind"], r["label"])
        s = summ.setdefault(f"{k[0]}|{k[1]}", {"n": 0, "full": 0, "zero": 0, "mean": 0.0})
        s["n"] += 1
        s["full"] += r["all_passed"]
        s["zero"] += r["score"] == 0
        s["mean"] += r["score"]
    for s in summ.values():
        s["mean"] = round(s["mean"] / s["n"], 4)
    out["summary"] = summ
    out["isolation_seen"] = sorted({json.dumps(r["isolation"], sort_keys=True) for r in rows})
    (ROOT / "results" / "securegrade_fn.json").write_text(json.dumps(out, indent=1))
    for k, s in sorted(summ.items()):
        print(f"{k:45s} n={s['n']:4d} full={s['full']:4d} zero={s['zero']:4d} mean={s['mean']}")
    print("isolation:", out["isolation_seen"], "seconds", out["seconds"])
    for r in rows:
        if r["label"].startswith("reference") and not r["all_passed"]:
            print("FN", r["task"], r["label"], r["score"], r["failures"][:2], r["detail"].get("load"), r["detail"].get("ungradable"))


def _guess_name(t):
    import ast
    import builtins
    for node in ast.walk(ast.parse(t["tests"][0])):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id not in dir(builtins):
            return node.func.id
    return "f"


if __name__ == "__main__":
    main()
