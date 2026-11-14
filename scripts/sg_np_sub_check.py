"""Re-grade every training completion that uses numpy or subprocess with a securegrade copy.

argv: <dir holding a securegrade package> <runs dir> <out json> [mem GiB]
Namespaces off, as on HF Jobs. Prints why each answer fails.
"""
import collections
import json
import os
import pathlib
import re
import sys

pkg_dir, runs, out_path = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3]
mem = int(float(sys.argv[4]) * 1024**3) if len(sys.argv) > 4 else 1024**3
sys.path.insert(0, pkg_dir)
import securegrade  # noqa: E402
assert securegrade.__file__.startswith(pkg_dir), securegrade.__file__
from datasets import load_dataset  # noqa: E402

tasks = {}
for split in ("train", "validation", "test", "prompt"):
    for r in load_dataset("google-research-datasets/mbpp", "sanitized", split=split):
        tasks[r["task_id"]] = r

PATS = (("numpy", r"import numpy|from numpy"), ("subproc", r"subprocess"))
rows = []
for d in sorted(runs.iterdir()):
    for line in (d / "completions.jsonl").open(encoding="utf-8"):
        c = json.loads(line)
        kinds = [k for k, p in PATS if re.search(p, c["text"])]
        if not kinds:
            continue
        t = tasks[c["task_id"]]
        r = securegrade.score(c["text"], list(t["test_list"]), setup_code="\n".join(t["test_imports"]),
                              network_isolation=False, mem_bytes=mem)
        rows.append({"run": d.name, "step": c["step"], "task": c["task_id"], "kinds": kinds,
                     "logged_sec": c["secure_all"], "logged_ce": c["aligntune_ce"], "rbw": c["rewarded_but_wrong"],
                     "local_sec": r.score, "load": r.detail.get("load"), "child": r.detail.get("child"),
                     "fail": r.failures[:2], "iso": r.detail.get("isolation")})

json.dump(rows, open(out_path, "w"), indent=1, default=str)
print("pkg", securegrade.__file__, "mem GiB", mem / 1024**3, "iso", rows[0]["iso"] if rows else None)
for k in ("numpy", "subproc"):
    rs = [r for r in rows if k in r["kinds"]]
    print(f"\n{k}: n={len(rs)}  logged sec pass={sum(r['logged_sec'] >= 0.999 for r in rs)}  "
          f"local sec pass={sum(r['local_sec'] >= 0.999 for r in rs)}  ce pass={sum(r['logged_ce'] >= 0.999 for r in rs)}  "
          f"agree with log={sum(abs(r['logged_sec'] - r['local_sec']) < 1e-9 for r in rs)}")
    why = collections.Counter((r["load"] or (r["fail"][0] if r["fail"] else "ok"))[:90] for r in rs)
    for w, n in why.most_common(8):
        print(f"   {n:3}  {w}")
print("\nRBW cases:")
for r in rows:
    if r["rbw"]:
        print(f"  {r['run']} step {r['step']} task {r['task']} {r['kinds']} local {r['local_sec']} load={r['load']} fail={r['fail']}")
