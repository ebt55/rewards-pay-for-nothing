"""M1: false-negative rate of AlignTune's code rewards on reference solutions, all of MBPP-sanitized
(427 tasks) and HumanEval (164). Run once in ~/p9/at (shipped 0.1.28) and once in ~/p9/at-patched.

Each reward gets the tests in the format it reads:
- code_execution, mbpp_reward: test_cases = assert strings
- code_verifiable: reference = list of assert strings
- code_correctness: test_cases = input/expected_output dicts, on the tasks whose every assert is a
  literal `assert f(args) == value` (shipped version cannot read assert strings at all)
HumanEval asserts are the single-line asserts of check(), with `candidate(` -> entry point
(asserts that need check()'s loop variables cannot be expressed this way; those tasks are listed).

Usage: python scripts/m1_fn_rate.py <label> <out.json>      (gentle: 4 threads)
"""
import ast
import json
import pathlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASKS = json.loads((ROOT / "exploits" / "tasks_all.json").read_text())


def he_asserts(t):
    return [l.strip().replace("candidate(", t["entry_point"] + "(") for l in t["tests"].splitlines()
            if l.strip().startswith("assert ") and not l.strip().startswith("assert True")]


def asserts_of(t):
    return list(t["tests"]) if t["kind"] == "mbpp" else he_asserts(t)


def dict_tests(asserts):
    out = []
    for a in asserts:
        try:
            node = ast.parse(a).body[0]
            tst = node.test
            if not (isinstance(tst, ast.Compare) and len(tst.ops) == 1 and isinstance(tst.ops[0], ast.Eq)
                    and isinstance(tst.left, ast.Call) and isinstance(tst.left.func, ast.Name) and not tst.left.keywords):
                return None
            args = [ast.literal_eval(x) for x in tst.left.args]
            exp = ast.literal_eval(tst.comparators[0])
        except Exception:
            return None
        if len(args) == 1 and isinstance(args[0], (list, tuple)) and len(args[0]) != 1:
            return None  # the dict format would splat a single list argument
        out.append({"input": args if len(args) > 1 else args[0], "expected_output": exp})
    return out or None


def main():
    label, out_path = sys.argv[1], sys.argv[2]
    from aligntune.rewards.registry import RewardRegistry as R
    import importlib.metadata as md

    def build(n):
        return R.get_reward_function(n, {"type": n, "weight": 1.0, "params": {}})

    rewards = {n: build(n) for n in ("code_execution", "mbpp_reward", "code_verifiable", "code_correctness")}
    jobs = []
    for t in TASKS:
        a = asserts_of(t)
        setup = t["setup"]
        for fenced in (True, False):
            text = "```python\n" + t["reference"] + "\n```" if fenced else t["reference"]
            jobs.append((t, "code_execution", fenced, lambda x=text, a=a, s=setup: rewards["code_execution"].compute(x, None, test_cases=a, test_imports=[s] if s else None)))
            jobs.append((t, "mbpp_reward", fenced, lambda x=text, a=a, s=setup: rewards["mbpp_reward"].compute(x, None, test_cases=a, test_imports=[s] if s else None)))
            jobs.append((t, "code_verifiable", fenced, lambda x=text, a=a: rewards["code_verifiable"].compute(x, a)))
            d = dict_tests(a)
            if d:
                jobs.append((t, "code_correctness", fenced, lambda x=text, d=d: rewards["code_correctness"].compute(x, None, test_cases=d)))

    def run(j):
        t, rw, fenced, fn = j
        try:
            s = fn()
            err = None
        except BaseException as e:  # noqa: BLE001 -- shipped code can raise SystemExit etc.
            s, err = None, f"{type(e).__name__}: {e}"[:200]
        return {"task": t["task_id"], "kind": t["kind"], "reward": rw, "fenced": fenced, "score": s, "error": err}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(run, jobs))
    summ = {}
    for r in rows:
        k = f"{r['reward']}|{r['kind']}|{'fenced' if r['fenced'] else 'bare'}"
        s = summ.setdefault(k, {"n": 0, "full": 0})
        s["n"] += 1
        s["full"] += (r["score"] or -1) >= 0.95
    for s in summ.values():
        s["fn_rate"] = round(1 - s["full"] / s["n"], 4)
    out = {"label": label, "aligntune_version": md.version("aligntune"), "seconds": round(time.time() - t0, 1),
           "summary": summ, "rows": rows}
    pathlib.Path(out_path).write_text(json.dumps(out, indent=1))
    for k, s in sorted(summ.items()):
        print(f"{label:9s} {k:40s} n={s['n']:4d} full={s['full']:4d} FN={s['fn_rate']}")


if __name__ == "__main__":
    main()
