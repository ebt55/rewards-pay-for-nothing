"""False negatives of SafeTune PR #32's code rewards on reference solutions (our code, MIT).

All of MBPP-sanitized (427) and HumanEval (164), the same task file and assert lifting as
scripts/m1_fn_rate.py (HumanEval: the single-line asserts of check(), `candidate(` -> entry point).
Each reward gets tests in the format it reads, as in Gate 1:
  code_execution, code_correctness: test_cases = assert strings
  mbpp_reward: test_list = assert strings
  code_execution[dicts]: test_cases = input/expected_output dicts, on tasks whose every assert is a
  literal `assert f(args) == value` (m1_fn_rate.dict_tests)
Every reference scoring < 1.0 is diagnosed assert by assert, and every one is scored a second time
to check it is stable.

Usage (st venv): python -W ignore scripts/pr32_fn_rate.py      (gentle: 4 threads -> <= 4 children)
Writes results/safetune-pr32/<label>-fn.json
"""
import ast
import json
import pathlib
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pr32_common import LABEL, OUT, build, use_pr  # noqa: E402

WHERE = use_pr()
import m1_fn_rate as m1  # noqa: E402  (our code: TASKS, asserts_of, dict_tests)
from safetune.rewards import _code_grader as cg  # noqa: E402  (PR internals, called for diagnosis only)

SCR = pathlib.Path.home() / "p9" / "tmp" / "pr32-fn"
SCR.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(SCR)
TIMEOUT = 5.0  # the rewards' default
# HumanEval tasks whose check() asserts use loop variables or helpers (found in M1).
HE_NEEDS_CHECK = {f"HumanEval/{i}" for i in (1, 32, 38, 44, 50, 53, 87, 113, 151)}

REW = {n: build(n) for n in ("code_execution", "code_correctness", "mbpp_reward")}
CALLS = {
    "code_execution": lambda x, a, d: REW["code_execution"].compute(x, None, test_cases=a),
    "code_correctness": lambda x, a, d: REW["code_correctness"].compute(x, None, test_cases=a),
    "mbpp_reward": lambda x, a, d: REW["mbpp_reward"].compute(x, None, test_list=a),
    "code_execution[dicts]": lambda x, a, d: REW["code_execution"].compute(x, None, test_cases=d),
}

# Our own diagnostic child: runs the (trusted) reference and each expression the PR's planner
# sends to the child, and reports the type returned or the exception raised.
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
exec(compile(code, "<ref>", "exec"), ns)
out = []
for e in exprs:
    try:
        v = eval(e, ns); b = bad(v)
        out.append(f"returns non-builtin type {b}" if b else "returns plain data")
    except BaseException as ex:
        out.append(f"raises {type(ex).__name__}: {str(ex)[:80]}")
if call is not None:
    import inspect
    fs = [v for k, v in ns.items() if k[:1] != "_" and inspect.isfunction(v)]
    try:
        v = fs[0](*call) if isinstance(call, list) else fs[0](call); b = bad(v)
        out.append((f"first public function {fs[0].__name__} " + (f"returns non-builtin type {b}" if b else "returns plain data")))
    except BaseException as ex:
        out.append(f"first public function {fs[0].__name__ if fs else None} raises {type(ex).__name__}: {str(ex)[:80]}")
print(json.dumps(out))
'''


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


def why_assert(code, assertion):
    """Replays grade_assertion's steps with the PR's own functions and says where it fails."""
    try:
        tree = ast.parse(assertion.strip())
    except SyntaxError:
        return {"pass": False, "reason": "assert does not parse on its own (multi-line in check())",
                "detail": assertion[:80]}
    try:
        cg._compile(tree.body[0].test, [])
    except cg._Undecomposable as e:
        return {"pass": False, "reason": "assert outside the whitelist", "detail": f"not evaluable in trainer: {str(e)[:80]}"}
    plan = cg._plan_assert(assertion)
    if plan is None:
        return {"pass": False, "reason": "assert outside the whitelist", "detail": "planner returned None"}
    calls, check = plan
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    clash = used & (set(cg._FUNCS) | {"math"}) & cg._bound_names(code)
    if clash:
        return {"pass": False, "reason": "function shares a builtin's name", "detail": sorted(clash)}
    t0 = time.time()
    vals = cg.run_candidate(code, TIMEOUT, exprs=tuple(calls))
    secs = round(time.time() - t0, 2)
    if vals is None:
        return {"pass": False, "reason": "timeout" if secs >= TIMEOUT - 0.05 else "child returned no result",
                "detail": f"{secs} s; calls={calls}"}
    failed = [c for c, v in zip(calls, vals) if v is cg._FAILED]
    if failed:
        return {"pass": False, "reason": "candidate call did not return plain data",
                "detail": {"calls": calls, "child_says": diag_child(code, calls)}}
    try:
        ok = check(vals)
    except Exception as e:  # noqa: BLE001
        return {"pass": False, "reason": "trainer-side check raised", "detail": f"{type(e).__name__}: {str(e)[:80]}"}
    if not ok:
        return {"pass": False, "reason": "values differ from expected", "detail": {"calls": calls, "values": repr(vals)[:200]}}
    return {"pass": True}


def why_dict(code, tc):
    try:
        json.dumps(tc.get("input"))
    except TypeError as e:
        return {"pass": False, "reason": "input not JSON-serialisable", "detail": str(e)[:80]}
    t0 = time.time()
    vals = cg.run_candidate(code, TIMEOUT, call=tc.get("input"))
    secs = round(time.time() - t0, 2)
    if vals is None:
        return {"pass": False, "reason": "timeout" if secs >= TIMEOUT - 0.05 else "child returned no result",
                "detail": {"secs": secs, "child_says": diag_child(code, [], tc.get("input"))}}
    if vals[-1] is cg._FAILED:
        return {"pass": False, "reason": "candidate call did not return plain data"}
    ok = vals[-1] == tc.get("expected_output")
    if not ok:
        return {"pass": False, "reason": "values differ from expected",
                "detail": {"got": repr(vals[-1])[:120], "expected": repr(tc.get("expected_output"))[:120],
                           "input_json_roundtrip_changes_it": json.loads(json.dumps(tc.get("input"))) != tc.get("input")}}
    return {"pass": True}


def diagnose(row, t, text):
    rw = row["reward"]
    code = (REW["mbpp_reward"] if rw == "mbpp_reward" else REW["code_execution"])._extract_code(text)
    if rw == "code_execution[dicts]":
        return [dict(test=tc, **why_dict(code, tc)) for tc in m1.dict_tests(m1.asserts_of(t))]
    return [dict(test=a, **why_assert(code, a)) for a in m1.asserts_of(t)]


def main():
    tasks = m1.TASKS
    jobs = []
    for t in tasks:
        a = m1.asserts_of(t)
        d = m1.dict_tests(a)
        for fenced in (True, False):
            text = "```python\n" + t["reference"] + "\n```" if fenced else t["reference"]
            for rw in CALLS:
                if rw == "code_execution[dicts]" and not d:
                    continue
                jobs.append((t, rw, fenced, text, a, d))

    def run(j):
        t, rw, fenced, text, a, d = j
        t0 = time.time()
        try:
            s, err = CALLS[rw](text, a, d), None
        except BaseException as e:  # noqa: BLE001
            s, err = None, f"{type(e).__name__}: {e}"[:200]
        return {"task": t["task_id"], "kind": t["kind"], "reward": rw, "fenced": fenced, "score": s, "error": err,
                "n_tests": len(d) if rw.endswith("[dicts]") else len(a), "seconds": round(time.time() - t0, 2)}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(run, jobs))
    first_pass_s = round(time.time() - t0, 1)
    by_id = {t["task_id"]: t for t in tasks}
    text_of = {(j[0]["task_id"], j[1], j[2]): j[3] for j in jobs}
    fn_rows = [r for r in rows if r["score"] is None or r["score"] < 1.0]

    def recheck(r):
        t = by_id[r["task"]]
        text = text_of[(r["task"], r["reward"], r["fenced"])]
        a = m1.asserts_of(t)
        r2 = CALLS[r["reward"]](text, a, m1.dict_tests(a))
        try:
            dg = diagnose(r, t, text)
        except Exception as e:  # noqa: BLE001
            dg = [{"pass": False, "reason": "diagnosis failed", "detail": f"{type(e).__name__}: {e}"[:160]}]
        return r2, dg

    with ThreadPoolExecutor(max_workers=4) as pool:
        again = list(pool.map(recheck, fn_rows))
    for r, (s2, dg) in zip(fn_rows, again):
        r["score_rerun"] = s2
        r["stable"] = s2 == r["score"]
        r["failing_tests"] = [x for x in dg if not x["pass"]]
        r["needs_check_context"] = r["task"] in HE_NEEDS_CHECK
    summ = {}
    for r in rows:
        k = f"{r['reward']}|{r['kind']}|{'fenced' if r['fenced'] else 'bare'}"
        s = summ.setdefault(k, {"n": 0, "full": 0})
        s["n"] += 1
        s["full"] += (r["score"] or 0) >= 1.0
    for s in summ.values():
        s["fn"] = s["n"] - s["full"]
        s["fn_rate"] = round(s["fn"] / s["n"], 4)
    out = {"label": LABEL, "safetune_rewards_code_file": WHERE, "timeout_s": TIMEOUT,
           "seconds_first_pass": first_pass_s, "seconds_total": round(time.time() - t0, 1),
           "n_tasks": {"mbpp": sum(t["kind"] == "mbpp" for t in tasks), "humaneval": sum(t["kind"] == "humaneval" for t in tasks)},
           "summary": summ, "fn_rows": fn_rows, "rows": rows}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{LABEL}-fn.json").write_text(json.dumps(out, indent=1, default=str))
    for k, s in sorted(summ.items()):
        print(f"{k:45s} n={s['n']:4d} full={s['full']:4d} FN={s['fn']:3d} ({s['fn_rate']})")
    print("FN rows:", len(fn_rows), "unstable:", sum(not r["stable"] for r in fn_rows), "seconds", out["seconds_total"])


if __name__ == "__main__":
    main()
