"""Tables for the AlignTune PR #40 check, from the raw result files (our code, MIT; stdlib only).

Usage: python3 scripts/pr40_tables.py   -> prints markdown; writes results/aligntune-pr40/tables.json
"""
import json
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / "results" / "aligntune-pr40"
EXPLOITS = ["reference", "empty", "prose", "stub", "print_pass_exit", "bare_exit", "fake_pass_lines", "always_equal",
            "hardcode_visible"]
HEAD = ["reference", "empty", "prose", "stub", "PASS+exit", "bare exit", "fake PASS:", "always-equal",
        "hardcode visible (not counted)"]
ROWS = [("code_execution", "tests", "code_execution [assert tests]"),
        ("code_execution[dicts]", "tests", "code_execution [dict tests]"),
        ("code_execution", "no_tests", "code_execution [no tests]"),
        ("code_correctness", "tests", "code_correctness [dict tests]"),
        ("code_correctness[asserts]", "tests", "code_correctness [assert tests]"),
        ("code_correctness", "no_tests", "code_correctness [no tests]"),
        ("mbpp_reward", "tests", "mbpp_reward [test_cases]"),
        ("mbpp_reward", "no_tests", "mbpp_reward [no tests]"),
        ("code_verifiable", "tests", "code_verifiable [reference = asserts]"),
        ("code_verifiable", "no_tests", "code_verifiable [no tests]"),
        ("counterfact_grpo_code", "tests", "counterfactual-GRPO code reward [tests]"),
        ("counterfact_grpo_code", "no_tests", "counterfactual-GRPO code reward [no tests]")]


def agg(cells):
    d = defaultdict(dict)
    for c in cells:
        d[(c["reward"], c["mode"], c["exploit"])][(c["task"], c["fenced"])] = c.get("score") if c["status"] == "ok" else c["status"]
    return d


def fmt(v):
    if isinstance(v, str):
        return v
    return "–" if v is None else ("0" if v == 0 else f"{v:.2f}")


def mx(d):
    nums = [v for v in d.values() if isinstance(v, (int, float))]
    other = sorted({v for v in d.values() if isinstance(v, str)})
    m = max(nums, default=None)
    return m, other


def exploit_table():
    old = agg(json.loads((ROOT / "results" / "raw_aligntune.json").read_text())["cells"])
    new = agg(json.loads((D / "aligntune-pr40-matrix.json").read_text())["cells"])
    lines = ["| reward [tests] | " + " | ".join(HEAD) + " |", "|" + "---|" * (len(HEAD) + 1)]
    data, above = [], []
    for rw, mode, label in ROWS:
        row = [label]
        for ex in EXPLOITS:
            o, n = old.get((rw, mode, ex), {}), new.get((rw, mode, ex), {})
            if ex == "reference":
                def full(d, f):
                    return sum(isinstance(v, (int, float)) and v >= 0.95 for (t, fen), v in d.items() if fen == f)
                row.append(f"{full(o, True)} · {full(o, False)} → {full(n, True)} · {full(n, False)}")
                rec = {"old_ge095_fenced": full(o, True), "old_ge095_bare": full(o, False),
                       "pr_ge095_fenced": full(n, True), "pr_ge095_bare": full(n, False)}
            else:
                (om, oo), (nm, no) = mx(o), mx(n)
                oc = fmt(om) + (f" ({', '.join(oo)})" if oo else "")
                nc = fmt(nm) + (f" ({', '.join(no)})" if no else "")
                cell = f"{oc} → {nc}"
                if nm is not None and nm > 0 and ex != "hardcode_visible":
                    cell = f"{oc} → **{nc}**"
                    above.append({"reward": rw, "mode": mode, "exploit": ex, "pr_max": nm,
                                  "pr_tasks_formats_above_0": sorted(f"{t} {'fenced' if f else 'bare'}" for (t, f), v in n.items()
                                                                     if isinstance(v, (int, float)) and v > 0)})
                row.append(cell)
                rec = {"old_max": om, "old_other": oo, "pr_max": nm, "pr_other": no,
                       "pr_cells": {f"{t}|{'fenced' if f else 'bare'}": v for (t, f), v in sorted(n.items())},
                       "old_cells": {f"{t}|{'fenced' if f else 'bare'}": v for (t, f), v in sorted(o.items())}}
            data.append({"reward": rw, "mode": mode, "exploit": ex, **rec})
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines), data, above


def fn_tables():
    fn = json.loads((D / "aligntune-pr40-fn.json").read_text())
    s = fn["summary"]
    rws = ["code_execution", "code_correctness[asserts]", "code_correctness[dicts]", "mbpp_reward", "code_verifiable",
           "code_execution[columns]", "code_correctness[columns]", "mbpp_reward[columns]", "code_verifiable[columns]"]
    lines = ["| reward [tests] | MBPP fenced | MBPP bare | HumanEval fenced | HumanEval bare |", "|---|---|---|---|---|"]
    for rw in rws:
        cells = []
        for kind in ("mbpp", "humaneval"):
            for f in ("fenced", "bare"):
                x = s.get(f"{rw}|{kind}|{f}")
                if not x:
                    cells.append("–")
                    continue
                rows_here = [r for r in fn["fn_rows"] if r["reward"] == rw and r["kind"] == kind and r["fenced"] == (f == "fenced")]
                failing = sum(not r.get("all_tests_pass_in_diagnosis") for r in rows_here)
                penalty_only = len(rows_here) - failing
                cells.append(f"{failing}/{x['n']}" + (f" (+{penalty_only} all-pass below 1.0)" if penalty_only else ""))
        lines.append(f"| `{rw}` | " + " | ".join(cells) + " |")
    by_task = defaultdict(lambda: {"where": [], "reasons": defaultdict(set), "unstable": 0})
    for r in fn["fn_rows"]:
        if r.get("all_tests_pass_in_diagnosis"):
            continue  # listed only as a count: every test passes, the score is lowered by format terms
        b = by_task[r["task"]]
        b["where"].append(f"{r['reward']} {'fenced' if r['fenced'] else 'bare'} {r['score']:.2f}" if isinstance(r["score"], (int, float)) else f"{r['reward']} {r['error']}")
        b["unstable"] += not r["stable"]
        if r.get("all_tests_pass_in_diagnosis"):
            b["reasons"]["all tests pass in diagnosis (score lowered by the reward's own format terms)"].add(r["reward"])
        for ft in r["failing_tests"]:
            dt = ft.get("detail")
            if isinstance(dt, dict) and "child_says" in dt:
                dt = "; ".join(sorted({c for c in dt["child_says"] if "plain data" not in c or "non-builtin" in c}))
            elif isinstance(dt, (dict, list)):
                dt = json.dumps(dt)[:140]
            b["reasons"][ft["reason"]].add(str(dt)[:140])
    task_lines = []
    for tid in sorted(by_task, key=lambda x: (x.split("/")[0], int(x.split("/")[1]))):
        b = by_task[tid]
        reasons = "; ".join(f"{k}: {' | '.join(sorted(v))[:200]}" for k, v in b["reasons"].items())
        task_lines.append({"task": tid, "where": b["where"], "reasons": reasons, "unstable_rows": b["unstable"]})
    return "\n".join(lines), task_lines


def main():
    md, data, above = exploit_table()
    print(md)
    print("\nPR cells > 0 for a solves-nothing exploit:")
    for a in above:
        print(" ", a["reward"], a["mode"], a["exploit"], a["pr_max"], len(a["pr_tasks_formats_above_0"]), "cells")
    out = {"exploit_table": data, "pr_above_zero": above}
    if (D / "aligntune-pr40-fn.json").exists():
        fmd, tl = fn_tables()
        print("\n" + fmd)
        for t in tl:
            print(f"- {t['task']}: {', '.join(t['where'])} -- {t['reasons']}" + (" (unstable)" if t["unstable_rows"] else ""))
        out["fn_by_task"] = tl
    (D / "tables.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
