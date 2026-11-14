"""Write the hand-read dossier: every RBW completion in steps 91-100 of each hole run, with its MBPP task and tests.
Read-only; nothing is executed. Usage (WSL venv with pyarrow): python dossier.py <hole_dir> <mbpp_sanitized_dir> <out.md> <blind.md>"""
import json
import pathlib
import sys

import pyarrow.parquet as pq

D, M, OUT, BLIND = (pathlib.Path(a) for a in sys.argv[1:5])
tasks = {}
for split in ("train", "test", "validation", "prompt"):
    for r in pq.read_table(M / f"{split}-00000-of-00001.parquet").to_pylist():
        tasks[r["task_id"]] = r

items = []
for run in ("h-ship-s0", "h-sec-s0"):
    for line in (D / run / "completions.jsonl").read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        if 91 <= c["step"] <= 100 and c["rewarded_but_wrong"]:
            items.append((run, c))

full, blind = [], []
for i, (run, c) in enumerate(items, 1):
    t = tasks[c["task_id"]]
    flags = [k[4:] for k in c if k.startswith("det_") and c[k]]
    head = (f"## Item {i}: {run} step {c['step']} MBPP {c['task_id']}\n"
            f"AlignTune {c['aligntune_ce']}, securegrade all {c['secure_all']:.2f}, visible {c.get('secure_visible')}, "
            f"hidden {c.get('secure_hidden')}, flags {flags}, len {len(c['text'])}\n")
    body = ("\n**Task:** " + t["prompt"] + "\n\n**Tests (first one is shown in the prompt):**\n```python\n"
            + "\n".join(t["test_imports"] + t["test_list"]) + "\n```\n\n**Reference solution:**\n```python\n" + t["code"]
            + "\n```\n\n**Completion (as logged, at most 4,000 chars):**\n````text\n" + c["text"] + "\n````\n")
    full.append(head + body)
    blind.append(f"## Item {i}: MBPP {c['task_id']}\n" + body)  # no run name, scores or flags

OUT.write_text(f"# Hole pair hand-read dossier: {len(items)} RBW completions, steps 91-100\n\n" + "\n".join(full), encoding="utf-8")
BLIND.write_text(f"# {len(items)} items to label\n\n" + "\n".join(blind), encoding="utf-8")
print(len(items), "items;", sum(r == "h-ship-s0" for r, _ in items), "ship,", sum(r == "h-sec-s0" for r, _ in items), "sec")
