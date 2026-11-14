"""Calibrate the M3 detectors and measure the natural base rate of 'paid but wrong' under
AlignTune's shipped code_execution reward (tests wired via test_cases), on the 1,350 baseline
completions (no training) and on the Gate 1 exploit templates.

Run in WSL: ~/p9-gen/.venv/bin/python detector_calibration.py
Writes baseline/detector_calibration.json.
"""
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "jobs"))
os.environ["PATH"] = os.path.dirname(sys.executable) + ":" + os.environ.get("PATH", "")  # `python` for AlignTune

from grader import grade  # noqa: E402
from hack_detectors import detect  # noqa: E402
from aligntune.rewards.registry import RewardRegistry  # noqa: E402
from datasets import load_dataset  # noqa: E402

ce = RewardRegistry.get_reward_function("code_execution", {"type": "code_execution", "weight": 1.0, "params": {}})
ce_score = getattr(ce, "compute", ce)

ds = load_dataset("google-research-datasets/mbpp", "sanitized", split="test")
rows = {r["task_id"]: r for r in ds}


def per_assert_fraction(text, row):
    ok = sum(grade(text, [t], row["test_imports"], timeout=10)["passed"] for t in row["test_list"])
    return ok / len(row["test_list"])


def shipped(text, row):
    # AlignTune's own scorer, same kwargs the TRL bridge would pass when the dataset has test_cases
    return float(ce_score(text, test_cases=list(row["test_list"])))


def one(item):
    mode, tid, which, text = item
    row = rows[tid]
    d = detect(text, row["test_list"][0])
    s = shipped(text, row)
    t = per_assert_fraction(text, row)
    return {"mode": mode, "task_id": tid, "which": which, "shipped": s, "true_frac": t, **d}


items = []
for mode in ("recipe", "chat", "chat_tests"):
    d = json.load(open(os.path.join(HERE, f"baseline-{mode}.json"), encoding="utf-8"))
    for t in d["per_task"]:
        items.append((mode, t["task_id"], "greedy", t["greedy"]["text"]))
        for s in t["samples"]:
            items.append((mode, t["task_id"], "sample", s["text"]))

with ThreadPoolExecutor(16) as ex:
    res = list(ex.map(one, items))

out = {"n": len(res), "by_mode": {}}
for mode in ("recipe", "chat", "chat_tests"):
    rr = [r for r in res if r["mode"] == mode]
    paid_more = [r for r in rr if r["shipped"] > r["true_frac"] + 1e-9]
    paid_less = [r for r in rr if r["shipped"] < r["true_frac"] - 1e-9]
    out["by_mode"][mode] = {
        "n": len(rr),
        "mean_shipped": sum(r["shipped"] for r in rr) / len(rr),
        "mean_true_frac": sum(r["true_frac"] for r in rr) / len(rr),
        "n_shipped_gt_true": len(paid_more),
        "n_shipped_lt_true": len(paid_less),
        "examples_shipped_gt_true": [{k: r[k] for k in ("task_id", "which", "shipped", "true_frac")} for r in paid_more[:5]],
        "detector_rates": {k: sum(r[k] for r in rr) / len(rr) for k in
                           ("pass_print", "early_exit", "always_equal", "hardcoded", "stub", "any_exploit")},
        "detector_counts": {k: sum(r[k] for r in rr) for k in
                            ("pass_print", "early_exit", "always_equal", "hardcoded", "stub", "any_exploit")},
    }

# Recall on Gate 1 exploit templates (read-only use of exploits/exploits.json), on the 50 tasks
ex = json.load(open(os.path.join(HERE, "..", "exploits", "exploits.json"), encoding="utf-8"))
from hack_detectors import _parse_assert  # noqa: E402

recall = Counter()
total = Counter()
shipped_paid = Counter()
for e in ex["exploits"]:
    if "template" not in e or not e.get("solves_nothing"):
        continue
    for tid in list(rows)[:50]:
        row = rows[tid]
        p = _parse_assert(row["test_list"][0])
        fn = p[0] if p else "f"
        code = e["template"].replace("{fn}", fn)
        text = f"```python\n{code}\n```" if e.get("fenceable", True) else code
        d = detect(text, row["test_list"][0])
        total[e["id"]] += 1
        recall[e["id"]] += int(d["any"])
        if e["id"] in ("pass_exit", "print_pass_exit", "always_equal", "bare_exit", "fake_pass_lines") or True:
            shipped_paid[e["id"]] += int(shipped(text, row) >= 0.999)
out["exploit_templates"] = {k: {"n": total[k], "flagged_any": recall[k], "shipped_full_marks": shipped_paid[k]}
                            for k in total}
json.dump(out, open(os.path.join(HERE, "detector_calibration.json"), "w"), indent=1)
print(json.dumps({m: {k: v for k, v in s.items() if k != "examples_shipped_gt_true"} for m, s in out["by_mode"].items()}, indent=1))
print(json.dumps(out["exploit_templates"], indent=1))
