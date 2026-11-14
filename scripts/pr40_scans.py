"""Dataset scans for AlignTune PR #40 (our code, MIT). Informative, not exploits of the PR.

1. Constant forge (stated by the PR): a function that returns one constant (True, False or None)
   for every call, scored for real on all MBPP-sanitized tasks with code_execution and mbpp_reward
   (test_cases) and on HumanEval with code_execution (lifted asserts). Cross-checked against a static count made
   with the PR's own trainer-side planner (each assert evaluated with that constant as every
   candidate value).
2. Other guessable values, static only: NaN, +inf, -inf, 0, [] and "" as the candidate value.
3. Names in an assert that the planner hands to the child but that are not the task's function
   (they are evaluated with the candidate's own definitions).
4. Asserts the planner cannot decompose (they always fail), and tasks whose function shares a name
   with a builtin or `math` (always fail).

Usage (at venv): python -W ignore scripts/pr32_scans.py
Writes results/safetune-pr32/<label>-scans.json
"""
import ast
import builtins
import json
import math
import pathlib
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pr40_common import LABEL, OUT, build, use_pr  # noqa: E402

WHERE = use_pr()
import m1_fn_rate as m1  # noqa: E402
from aligntune.rewards import _code_grader as cg  # noqa: E402

SCR = pathlib.Path.home() / "p9" / "tmp" / "pr40-scans"
SCR.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(SCR)

CONSTS = {"True": True, "False": False, "None": None}
GUESS = {"nan": float("nan"), "inf": float("inf"), "-inf": float("-inf"), "0": 0, "[]": [], "''": ""}


def entry(t):
    """The task's function: HumanEval's entry_point; for MBPP the first called name in the first
    assert that the reference defines (else the first non-builtin called name)."""
    if t["entry_point"]:
        return t["entry_point"]
    defined = {n.name for n in ast.walk(ast.parse(t["reference"])) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    called = [n.func.id for n in ast.walk(ast.parse(t["tests"][0])) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    for c in called:
        if c in defined:
            return c
    return next((c for c in called if c not in dir(builtins)), "f")


def root(expr):
    node = ast.parse(expr, mode="eval").body
    while True:
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, (ast.Attribute, ast.Subscript)):
            node = node.value
        else:
            break
    return node.id if isinstance(node, ast.Name) else type(node).__name__


def static_pass(assertion, value):
    plan = cg.plan_assert(assertion)
    if plan is None:
        return None
    calls, check = plan
    try:
        return bool(check([value] * len(calls)))
    except Exception:  # noqa: BLE001
        return False


def main():
    t0 = time.time()
    tasks = m1.TASKS
    out = {"label": LABEL, "safetune_rewards_code_file": WHERE}
    static, free, undecomp, clash = [], [], [], []
    for t in tasks:
        fn = entry(t)
        asserts = m1.asserts_of(t)
        per = {"task": t["task_id"], "kind": t["kind"], "fn": fn, "n": len(asserts)}
        for name, val in {**CONSTS, **GUESS}.items():
            res = [static_pass(a, val) for a in asserts]
            per[name] = sum(bool(r) for r in res)
        static.append(per)
        for a in asserts:
            plan = cg.plan_assert(a)
            if plan is None:
                undecomp.append({"task": t["task_id"], "kind": t["kind"], "assert": a[:160]})
                continue
            others = sorted({root(c) for c in plan[0]} - {fn})
            if others:
                free.append({"task": t["task_id"], "kind": t["kind"], "fn": fn, "assert": a[:200], "child_side_names": others,
                             "needs_check_context": t["task_id"] in {f"HumanEval/{i}" for i in (1, 32, 38, 44, 50, 53, 87, 113, 151)}})
        if fn in set(cg._FUNCS) | {"math"}:
            clash.append({"task": t["task_id"], "fn": fn})
    out["static"] = static
    out["free_names"] = free
    out["undecomposable"] = undecomp
    out["builtin_name_tasks"] = clash

    # Real runs of the three constant returners.
    rew = {"mbpp_reward": build("mbpp_reward"), "code_execution": build("code_execution")}
    jobs = []
    for t in tasks:
        fn = entry(t)
        for cname in CONSTS:
            text = f"```python\ndef {fn}(*args, **kwargs):\n    return {cname}\n```"
            jobs.append((t, cname, text))

    def run(j):
        t, cname, text = j
        a = m1.asserts_of(t)
        # code_execution gives the fraction of asserts passed; mbpp_reward (MBPP only) the net reward
        # after its own penalties (-0.10 when nothing passes).
        s = rew["code_execution"].compute(text, None, test_cases=a)
        m = rew["mbpp_reward"].compute(text, None, test_cases=a) if t["kind"] == "mbpp" else None
        return {"task": t["task_id"], "kind": t["kind"], "const": cname, "score": s, "mbpp_reward": m}

    with ThreadPoolExecutor(max_workers=4) as pool:
        real = list(pool.map(run, jobs))
    out["constant_runs"] = real
    summ = {}
    for kind in ("mbpp", "humaneval"):
        best = {}
        for r in real:
            if r["kind"] == kind:
                best[r["task"]] = max(best.get(r["task"], 0.0), r["score"])
        per_const = {c: Counter() for c in CONSTS}
        for r in real:
            if r["kind"] == kind:
                per_const[r["const"]]["full" if r["score"] >= 1.0 else ("partial" if r["score"] > 0 else "zero")] += 1
        st = [s for s in static if s["kind"] == kind]
        summ[kind] = {
            "tasks": len(best),
            "full_marks_by_one_constant": sum(v >= 1.0 for v in best.values()),
            "above_zero_by_one_constant": sum(v > 0 for v in best.values()),
            "mean_best_constant_score": round(sum(best.values()) / max(1, len(best)), 4),
            "mbpp_reward_tasks_above_zero_by_one_constant": len({r["task"] for r in real if r["kind"] == kind
                                                                 and r["mbpp_reward"] is not None and r["mbpp_reward"] > 0}),
            "mbpp_reward_max": max((r["mbpp_reward"] for r in real if r["kind"] == kind and r["mbpp_reward"] is not None), default=None),
            "per_constant": {c: dict(v) for c, v in per_const.items()},
            "static_full_by_one_constant": sum(any(s[c] == s["n"] and s["n"] > 0 for c in CONSTS) for s in st),
            "static_above_zero_by_one_constant": sum(any(s[c] > 0 for c in CONSTS) for s in st),
            "asserts": sum(s["n"] for s in st),
            "asserts_passed_static": {c: sum(s[c] for s in st) for c in {**CONSTS, **GUESS}},
            "tasks_full_static_by_guess": {c: sum(s[c] == s["n"] and s["n"] > 0 for s in st) for c in GUESS},
            "undecomposable_asserts": sum(u["kind"] == kind for u in undecomp),
            "asserts_with_child_side_names_other_than_fn": sum(f["kind"] == kind for f in free),
        }
    out["summary"] = summ
    out["seconds"] = round(time.time() - t0, 1)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{LABEL}-scans.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(summ, indent=1))
    print("builtin-name tasks:", clash)
    print("free names (first 30):")
    for f in free[:30]:
        print(" ", f["task"], f["child_side_names"], f["assert"][:110])
    print("seconds", out["seconds"])


if __name__ == "__main__":
    main()
