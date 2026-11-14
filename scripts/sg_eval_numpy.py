"""Re-grade the eval answers that import numpy with the original and fixed securegrade copies.
argv: <evals dir> <sgv dir>"""
import importlib
import json
import pathlib
import re
import sys

evals, sgv = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
from datasets import load_dataset  # noqa: E402

tasks = {r["task_id"]: r for s in ("train", "validation", "test", "prompt")
         for r in load_dataset("google-research-datasets/mbpp", "sanitized", split=s)}
rows = []
for f in sorted(evals.glob("*/eval_samples_step*.jsonl")):
    for line in f.open(encoding="utf-8"):
        d = json.loads(line)
        if d["kind"] == "mbpp" and re.search(r"import numpy|from numpy", d["text"]):
            rows.append((f.parent.name, f.stem[-4:], d))
for v in ("orig", "fix2"):
    sys.path.insert(0, str(sgv / v))
    for m in [m for m in sys.modules if m == "securegrade" or m.startswith("securegrade.")]:
        del sys.modules[m]
    sg = importlib.import_module("securegrade")
    assert sg.__file__.startswith(str(sgv / v)), sg.__file__
    for run, step, d in rows:
        t = tasks[d["task_id"]]
        r = sg.score(d["text"], list(t["test_list"]), setup_code="\n".join(t["test_imports"]), network_isolation=False)
        print(f"{v:5} {run:10} step {step} MBPP/{d['task_id']} logged pass_all={d['pass_all']} ce={d['aligntune_ce']} "
              f"-> local {r.score} {(r.detail.get('load') or (r.failures[0] if r.failures else 'ok'))[:60]}")
    sys.path.pop(0)
