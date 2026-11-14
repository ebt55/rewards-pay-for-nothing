"""False negatives of AlignTune PR #40's code rewards on reference solutions (our code, MIT).

All of MBPP-sanitized (427) and HumanEval (164), same task file and assert lifting as
scripts/m1_fn_rate.py, same reward calls as M1:
  code_execution, mbpp_reward: test_cases = assert strings (+ test_imports, as M1 passed them)
  code_verifiable: reference = assert strings
  code_correctness: test_cases = input/expected_output dicts where expressible (M1), and, new in the PR,
  test_cases = assert strings
HumanEval is also graded the way the PR reads it natively: the row's `test` and `entry_point` columns.
Every row scoring < 1.0 is diagnosed test by test and scored a second time.

Usage (at venv): python -W ignore scripts/pr40_fn_rate.py     (4 threads -> at most 4 children)
Writes results/aligntune-pr40/<label>-fn.json
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pr40_common import LABEL, OUT, build, use_pr  # noqa: E402

WHERE = use_pr()
import m1_fn_rate as m1  # noqa: E402  (our code: TASKS, asserts_of, dict_tests)
from aligntune.rewards import _code_grader as cg  # noqa: E402  (PR internals, called for diagnosis only)
# Our own diagnostic child (same as in pr32_fn_rate.py): runs the trusted reference and each expression
# the planner sends to the child, and reports the type returned or the exception raised.
DIAG = r'''
import json, sys
PLAIN = (bool, int, float, str, list, tuple, set, frozenset, dict, type(None))
def bad(v, depth=0):
    if depth > 50: return None
    t = type(v)
    if t not in PLAIN: return f"{t.__module__}.{t.__qualname__}"
    if t is dict:
        for k, x in v.items():
            b = bad(k, depth + 1) or bad(x, depth + 1)
            if b: return b
    elif t in (list, tuple, set, frozenset):
        for x in v:
            b = bad(x, depth + 1)
            if b: return b
    return None
code, exprs, call = json.load(open(sys.argv[1]))
ns = {"__name__": "__main__"}
try:
    exec(compile(code, "<ref>", "exec"), ns)
except BaseException as ex:
    print(json.dumps([f"program raises {type(ex).__name__}: {str(ex)[:80]}"])); sys.exit(0)
out = []
for e in exprs:
    try:
        v = eval(e, ns); b = bad(v)
        out.append(f"returns non-builtin type {b}" if b else "returns plain data")
    except BaseException as ex:
        out.append(f"raises {type(ex).__name__}: {str(ex)[:80]}")
if call is not None:
    import types
    fs = [v for k, v in ns.items() if k[:1] != "_" and type(v) is types.FunctionType and getattr(v, "__module__", None) == "__main__"]
    try:
        v = fs[0](*call) if isinstance(call, list) and len(call) > 1 else fs[0](call); b = bad(v)
        out.append((f"first function {fs[0].__name__} " + (f"returns non-builtin type {b}" if b else "returns plain data")))
    except BaseException as ex:
        out.append(f"first function {fs[0].__name__ if fs else None} raises {type(ex).__name__}: {str(ex)[:80]}")
print(json.dumps(out))
'''

SCR = pathlib.Path.home() / "p9" / "tmp" / "pr40-fn"
SCR.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(SCR)
TIMEOUT = 5.0
HE_NEEDS_CHECK = {f"HumanEval/{i}" for i in (1, 32, 38, 44, 50, 53, 87, 113, 151)}
REW = {n: build(n) for n in ("code_execution", "code_correctness", "mbpp_reward", "code_verifiable")}


def kw_for(rw, t, a, d):
    """(reference, kwargs) for one reward call, M1 style; '[columns]' = HumanEval's own test columns."""
    setup = t["setup"]
    if rw.endswith("[columns]"):
        return None, {"test": t["tests"], "entry_point": t["entry_point"]}
    base = rw.split("[")[0]
    if base == "code_verifiable":
        return a, {}
    if rw == "code_correctness[dicts]":
        return None, {"test_cases": d}
    kw = {"test_cases": a}
    if base in ("code_execution", "mbpp_reward") and setup:
        kw["test_imports"] = [setup]
    return None, kw


REWARDS = ["code_execution", "mbpp_reward", "code_verifiable", "code_correctness[asserts]", "code_correctness[dicts]",
           "code_execution[columns]", "code_correctness[columns]", "mbpp_reward[columns]", "code_verifiable[columns]"]


def score(rw, text, t, a, d):
    ref, kw = kw_for(rw, t, a, d)
    return REW[rw.split("[")[0]].compute(text, ref, **kw)


def graded_code_and_tests(rw, text, t, a, d):
    """The program and tests the reward hands to the grader, built with the reward's own helpers."""
    ref, kw = kw_for(rw, t, a, d)
    base = rw.split("[")[0]
    r = REW[base]
    tests, setup = cg.tests_from_columns(kw)
    if base == "mbpp_reward":
        fn = r._extract_function_info_from_test(tests[0])[0]
        code = r._prepare_for_exec(cg.with_prompt(text, text, kw), fn)
        return (setup + "\n\n" + code if setup else code), tests, None
    if base == "code_verifiable":
        code = r._extract_code(text) or ""
        if tests:
            code = cg.with_prompt(code, text, kw) + ("\n\n" + setup if setup else "")
            return code, tests, None
        return code, ref, None
    code = (r._extract_code(text) if base == "code_execution" else cg.extract_code(text))
    code = cg.with_prompt(code, text, kw) + ("\n\n" + setup if setup else "")
    return code, tests or [], r._compare_outputs


def diag_child(code, exprs, call=None):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump([code, list(exprs), call], f)
        path = f.name
    try:
        p = subprocess.run([sys.executable, "-I", "-c", DIAG, path], capture_output=True, text=True, timeout=30)
        return json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else [f"diag child failed: {p.stderr[-160:]}"]
    except Exception as e:  # noqa: BLE001
        return [f"diag failed: {type(e).__name__}"]
    finally:
        pathlib.Path(path).unlink(missing_ok=True)


def why(code, test, compare):
    if isinstance(test, dict):
        run = cg.run_candidate(code, TIMEOUT, [{"call": test.get("input"), "no_args": True}])
        if run.status != "ok":
            return {"pass": False, "reason": f"child run status {run.status}", "detail": diag_child(code, [], test.get("input"))}
        v = run.values[0]
        if v is cg.FAILED:
            return {"pass": False, "reason": "call did not return plain data", "detail": diag_child(code, [], test.get("input"))}
        ok = bool((compare or (lambda x, y: x == y))(v, test.get("expected_output")))
        return {"pass": ok} if ok else {"pass": False, "reason": "values differ from expected",
                                         "detail": {"got": repr(v)[:120], "expected": repr(test.get("expected_output"))[:120]}}
    plan = cg.plan_assert(test)
    if plan is None:
        try:
            import ast
            ast.parse(test.strip())
            return {"pass": False, "reason": "assert outside the whitelist (or not a single assert)", "detail": test[:100]}
        except SyntaxError:
            return {"pass": False, "reason": "test does not parse on its own", "detail": test[:100]}
    calls, check = plan
    if cg._bound_builtins(code, test):
        return {"pass": False, "reason": "candidate binds a builtin name the test uses", "detail": test[:100]}
    run = cg.run_candidate(code, TIMEOUT, [{"expr": c} for c in calls])
    if run.status != "ok":
        return {"pass": False, "reason": f"child run status {run.status}", "detail": diag_child(code, calls)}
    if any(v is cg.FAILED for v in run.values):
        return {"pass": False, "reason": "candidate call did not return plain data", "detail": {"calls": list(calls), "child_says": diag_child(code, calls)}}
    try:
        ok = check(run.values)
    except Exception as e:  # noqa: BLE001
        return {"pass": False, "reason": "trainer-side check raised", "detail": f"{type(e).__name__}"}
    return {"pass": True} if ok else {"pass": False, "reason": "values differ from expected",
                                      "detail": {"calls": list(calls), "values": repr(run.values)[:200]}}


def diagnose(rw, text, t, a, d):
    code, tests, compare = graded_code_and_tests(rw, text, t, a, d)
    if isinstance(tests, str):
        return [{"test": tests[:80], "pass": False, "reason": "reference is a string (output check)"}]
    return [dict(test=(x if isinstance(x, dict) else x[:160]), **why(code, x, compare)) for x in tests]


def main():
    tasks = m1.TASKS
    jobs = []
    for t in tasks:
        a = m1.asserts_of(t)
        d = m1.dict_tests(a)
        for fenced in (True, False):
            text = "```python\n" + t["reference"] + "\n```" if fenced else t["reference"]
            for rw in REWARDS:
                if rw == "code_correctness[dicts]" and not d:
                    continue
                if rw.endswith("[columns]") and t["kind"] != "humaneval":
                    continue
                jobs.append((t, rw, fenced, text, a, d))

    def run(j):
        t, rw, fenced, text, a, d = j
        t0 = time.time()
        try:
            s, err = score(rw, text, t, a, d), None
        except BaseException as e:  # noqa: BLE001
            s, err = None, f"{type(e).__name__}: {e}"[:200]
        return {"task": t["task_id"], "kind": t["kind"], "reward": rw, "fenced": fenced, "score": s, "error": err,
                "seconds": round(time.time() - t0, 2)}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(run, jobs))
    first_pass_s = round(time.time() - t0, 1)
    by_id = {t["task_id"]: t for t in tasks}
    fn_rows = [r for r in rows if r["score"] is None or r["score"] < 1.0]

    def recheck(r):
        t = by_id[r["task"]]
        a = m1.asserts_of(t)
        d = m1.dict_tests(a)
        text = "```python\n" + t["reference"] + "\n```" if r["fenced"] else t["reference"]
        try:
            s2 = score(r["reward"], text, t, a, d)
        except BaseException as e:  # noqa: BLE001
            s2 = f"{type(e).__name__}"
        try:
            dg = diagnose(r["reward"], text, t, a, d)
        except Exception as e:  # noqa: BLE001
            dg = [{"pass": False, "reason": "diagnosis failed", "detail": f"{type(e).__name__}: {e}"[:160]}]
        return s2, dg

    with ThreadPoolExecutor(max_workers=4) as pool:
        again = list(pool.map(recheck, fn_rows))
    for r, (s2, dg) in zip(fn_rows, again):
        r["score_rerun"] = s2
        r["stable"] = s2 == r["score"]
        r["failing_tests"] = [x for x in dg if not x["pass"]]
        r["all_tests_pass_in_diagnosis"] = all(x["pass"] for x in dg) if dg else None
        r["needs_check_context"] = r["task"] in HE_NEEDS_CHECK
    summ = {}
    for r in rows:
        k = f"{r['reward']}|{r['kind']}|{'fenced' if r['fenced'] else 'bare'}"
        s = summ.setdefault(k, {"n": 0, "full": 0, "ge_095": 0})
        s["n"] += 1
        s["full"] += (r["score"] or 0) >= 1.0
        s["ge_095"] += (r["score"] or 0) >= 0.95
    for s in summ.values():
        s["fn"] = s["n"] - s["full"]
        s["fn_rate"] = round(s["fn"] / s["n"], 4)
    out = {"label": LABEL, "aligntune_rewards_core_file": WHERE, "timeout_s": TIMEOUT,
           "seconds_first_pass": first_pass_s, "seconds_total": round(time.time() - t0, 1),
           "summary": summ, "fn_rows": fn_rows, "rows": rows}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{LABEL}-fn.json").write_text(json.dumps(out, indent=1, default=str))
    for k, s in sorted(summ.items()):
        print(f"{k:45s} n={s['n']:4d} full={s['full']:4d} >=0.95={s['ge_095']:4d} FN={s['fn']:3d} ({s['fn_rate']})")
    print("FN rows:", len(fn_rows), "unstable:", sum(not r["stable"] for r in fn_rows), "seconds", out["seconds_total"])


if __name__ == "__main__":
    main()
