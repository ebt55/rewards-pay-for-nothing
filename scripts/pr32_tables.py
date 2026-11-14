"""Tables for the SafeTune PR #32 check, from the raw result files (our code, MIT; stdlib only).

Usage: python3 scripts/pr32_tables.py    -> prints markdown tables; writes results/safetune-pr32/tables.json
"""
import json
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / "results" / "safetune-pr32"
EXPLOITS = ["reference", "empty", "prose", "stub", "print_pass_exit", "bare_exit", "fake_pass_lines", "always_equal",
            "hardcode_visible"]
HEAD = ["reference (tasks at 1.0, fenced · bare)", "empty", "prose", "stub", "PASS+exit", "bare exit", "fake PASS:",
        "always-equal", "hardcode visible (not counted)"]
ROWS = [("code_execution", "tests", "code_execution [assert tests]"),
        ("code_execution[dicts]", "tests", "code_execution [dict tests]"),
        ("code_execution", "no_tests", "code_execution [no tests]"),
        ("code_correctness", "tests", "code_correctness [assert tests]"),
        ("code_correctness", "no_tests", "code_correctness [no tests]"),
        ("mbpp_reward", "tests", "mbpp_reward [test_list]"),
        ("mbpp_reward", "no_tests", "mbpp_reward [no tests]")]


def agg(cells):
    d = defaultdict(dict)
    for c in cells:
        d[(c["reward"], c["mode"], c["exploit"])][(c["task"], c["fenced"])] = c.get("score") if c["status"] == "ok" else None
    return d


def fmt(v):
    return "–" if v is None else ("0" if v == 0 else f"{v:.2f}")


def exploit_table():
    old = agg(json.loads((ROOT / "results" / "raw_safetune.json").read_text())["cells"])
    new = agg(json.loads((D / "safetune-pr32-matrix.json").read_text())["cells"])
    lines = ["| reward [tests] | " + " | ".join(HEAD) + " |", "|" + "---|" * (len(HEAD) + 1)]
    data, above = [], []
    for rw, mode, label in ROWS:
        row = [label]
        for ex in EXPLOITS:
            o, n = old.get((rw, mode, ex), {}), new.get((rw, mode, ex), {})
            if ex == "reference":
                def full(d, f):
                    return sum((v or 0) >= 1.0 for (t, fen), v in d.items() if fen == f)
                row.append(f"{full(o, True)} · {full(o, False)} → {full(n, True)} · {full(n, False)}")
                rec = {"old_full_fenced": full(o, True), "old_full_bare": full(o, False),
                       "pr_full_fenced": full(n, True), "pr_full_bare": full(n, False)}
            else:
                om = max((v for v in o.values() if v is not None), default=None)
                nm = max((v for v in n.values() if v is not None), default=None)
                cell = f"{fmt(om)} → {fmt(nm)}"
                if nm and nm > 0 and ex != "hardcode_visible":
                    cell = f"{fmt(om)} → **{fmt(nm)}**"
                    above.append({"reward": rw, "mode": mode, "exploit": ex, "pr_max": nm,
                                  "pr_tasks_formats_above_0": sorted(f"{t} {'fenced' if f else 'bare'}" for (t, f), v in n.items() if v and v > 0)})
                row.append(cell)
                rec = {"old_max": om, "pr_max": nm,
                       "old_min": min((v for v in o.values() if v is not None), default=None),
                       "pr_min": min((v for v in n.values() if v is not None), default=None),
                       "pr_cells": {f"{t}|{'fenced' if f else 'bare'}": v for (t, f), v in sorted(n.items())},
                       "old_cells": {f"{t}|{'fenced' if f else 'bare'}": v for (t, f), v in sorted(o.items())}}
            data.append({"reward": rw, "mode": mode, "exploit": ex, **rec})
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines), data, above


def fn_tables():
    fn = json.loads((D / "safetune-pr32-fn.json").read_text())
    s = fn["summary"]
    rws = ["code_execution", "code_correctness", "mbpp_reward", "code_execution[dicts]"]
    lines = ["| reward | MBPP fenced | MBPP bare | HumanEval fenced | HumanEval bare |", "|---|---|---|---|---|"]
    for rw in rws:
        cells = []
        for kind in ("mbpp", "humaneval"):
            for f in ("fenced", "bare"):
                x = s.get(f"{rw}|{kind}|{f}")
                cells.append(f"{x['fn']}/{x['n']} ({100 * x['fn_rate']:.1f}%)" if x else "–")
        lines.append(f"| `{rw}` | " + " | ".join(cells) + " |")
    # Group FN rows by task: which reward/format, and the distinct reasons.
    by_task = defaultdict(lambda: {"where": [], "reasons": defaultdict(set), "unstable": 0})
    for r in fn["fn_rows"]:
        b = by_task[r["task"]]
        b["where"].append(f"{r['reward']} {'fenced' if r['fenced'] else 'bare'} {r['score']:.2f}" if r["score"] is not None else f"{r['reward']} error")
        b["unstable"] += not r["stable"]
        b["check_ctx"] = r["needs_check_context"]
        for ft in r["failing_tests"]:
            d = ft.get("detail")
            if isinstance(d, dict) and "child_says" in d:
                d = "; ".join(sorted({c for c in d["child_says"] if "plain data" not in c or "non-builtin" in c}))
            elif isinstance(d, dict):
                d = json.dumps(d)[:140]
            b["reasons"][ft["reason"]].add(str(d)[:160])
    task_lines = []
    for tid in sorted(by_task, key=lambda x: (x.split("/")[0], int(x.split("/")[1]))):
        b = by_task[tid]
        reasons = "; ".join(f"{k}: {' | '.join(sorted(v))[:220]}" for k, v in b["reasons"].items())
        task_lines.append({"task": tid, "where": b["where"], "reasons": reasons, "unstable_rows": b["unstable"],
                           "needs_check_context": b.get("check_ctx")})
    return "\n".join(lines), task_lines, fn


def main():
    md, data, above = exploit_table()
    print(md)
    print("\nPR cells > 0 for a solves-nothing exploit:")
    for a in above:
        print(" ", a)
    out = {"exploit_table": data, "pr_above_zero": above}
    if (D / "safetune-pr32-fn.json").exists():
        fmd, tl, fn = fn_tables()
        print("\n" + fmd)
        for t in tl:
            print(f"- {t['task']}: {', '.join(t['where'])} -- {t['reasons']}" + (" (unstable)" if t["unstable_rows"] else ""))
        out["fn_by_task"] = tl
    (D / "tables.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
