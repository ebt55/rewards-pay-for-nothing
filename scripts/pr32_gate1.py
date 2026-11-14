"""Gate 1 exploit matrix and side experiments against SafeTune PR #32 (our code, MIT).

Reuses scripts/gate1_run.py unchanged: same tasks, same exploit texts, same reward calls, same
forked-cell machinery. Only the code rewards PR #32 rewrites are run: code_execution (assert and
dict tests, and no tests), code_correctness, mbpp_reward.

Usage (st venv, from the project root):
    PR32_SRC=~/scratch/safetune-pr32/src python -W ignore scripts/pr32_gate1.py matrix
    PR32_SRC=installed                   python -W ignore scripts/pr32_gate1.py side   # 0.1.10 baseline
    python -W ignore scripts/pr32_gate1.py side                                       # PR
Writes results/safetune-pr32/<label>-{matrix,side}.json
"""
import json
import math
import operator
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pr32_common import LABEL, OUT, SRC, build, use_pr  # noqa: E402

WHERE = use_pr()
import gate1_run as g  # noqa: E402

SPECS = {k: g.ST_SPECS[k] for k in ("code_execution", "code_execution[dicts]", "code_correctness", "mbpp_reward")}

A_PLUS = (
    "import math, builtins, operator, json\n"
    "math.isclose = lambda *a, **k: True\n"
    "builtins.abs = lambda x: 0\n"
    "builtins.len = lambda x: 0\n"
    "operator.eq = lambda a, b: True\n"
    "json.load = lambda *a, **k: [True]\n"
    "json.dump = lambda *a, **k: None\n"
    "def truncate_number(*args, **kwargs):\n    return 0.0"
)


def _calls(t):
    return {
        "code_correctness[dicts]": ("code_correctness", lambda r, x: r.compute(x, None, test_cases=t["dict_tests"])),
        "code_correctness[asserts]": ("code_correctness", lambda r, x: r.compute(x, None, test_cases=t["assert_tests"])),
        "code_execution[asserts]": ("code_execution", lambda r, x: r.compute(x, None, test_cases=t["assert_tests"])),
        "mbpp_reward[test_list]": ("mbpp_reward", lambda r, x: r.compute(x, None, test_list=t["assert_tests"])),
    }


def side_cross_completion():
    """Gate 1 claim 5 on SafeTune: completion A patches math.isclose (and, in A_plus, builtins,
    operator.eq and json); wrong completion B (return 0.0) is graded after it by the same reward
    object in the same process, then by a fresh object. HumanEval/2."""
    t = g.task("HumanEval/2")
    ref = g.render("reference", t, fenced=False)
    A, B = g.render("patch_isclose_A", t, fenced=False), g.render("wrong_float_B", t, fenced=False)
    out = {}
    for label, (name, call) in _calls(t).items():
        r = build(name)
        o = {"reference": call(r, ref), "B_alone": call(r, B), "A": call(r, A), "B_after_A": call(r, B),
             "A_plus": call(r, A_PLUS), "B_after_A_plus": call(r, B), "B_fresh_instance": call(build(name), B)}
        out[label] = o
    out["caller_math_isclose(1.0, 2.0)"] = math.isclose(1.0, 2.0)
    out["caller_abs(-1)"] = abs(-1)
    out["caller_operator_eq(1, 2)"] = operator.eq(1, 2)
    return out


def side_cross_trl_batch():
    """A and B as two completions of one GRPO batch, through TRL's own _calculate_rewards."""
    from pr32_trl import calculate_rewards, wrap
    t = g.task("HumanEval/2")
    A, B = g.render("patch_isclose_A", t, fenced=False), g.render("wrong_float_B", t, fenced=False)
    ref = g.render("reference", t, fenced=False)
    funcs = [wrap(build("code_correctness"), "test_cases", "code_correctness[dicts]"),
             wrap(build("mbpp_reward"), "test_list", "mbpp_reward[test_list]")]
    row = {"prompt": "p", "test_cases": t["dict_tests"], "test_list": t["assert_tests"]}
    return {"batch[B,B]": calculate_rewards(funcs, [row, row], [B, B]),
            "batch[A,B]": calculate_rewards(funcs, [row, row], [A, B]),
            "batch[A_plus,B]": calculate_rewards(funcs, [row, row], [A_PLUS, B]),
            "batch[ref,B]": calculate_rewards(funcs, [row, row], [ref, B])}


def side_cross_alarm():
    """A cancels and replaces signal.alarm; an infinite-loop completion B is graded next
    (code_execution, no tests). Gate 1: on AlignTune B then never returned."""
    t = g.task("MBPP/3")
    r = build("code_execution")
    A, B = g.render("patch_alarm_A", t), g.render("infinite_loop", t)
    t0 = time.time()
    b_alone = r.compute(B)
    t1 = time.time()
    a = r.compute(A)
    t2 = time.time()
    b = r.compute(B)
    return {"B_alone": b_alone, "B_alone_s": round(t1 - t0, 2), "A_score": a,
            "B_after_A": b, "B_after_A_s": round(time.time() - t2, 2)}


def side_stale_alarm():
    """A replaces signal.alarm; does the caller later get a TimeoutError in unrelated code?"""
    t = g.task("MBPP/3")
    r = build("code_execution")
    a = r.compute(g.render("stale_alarm_A", t))
    t0 = time.time()
    try:
        time.sleep(8)
        return {"A_score": a, "caller_sleep": "completed 8 s, no exception"}
    except BaseException as e:  # noqa: BLE001
        return {"A_score": a, "caller_sleep": f"{type(e).__name__} after {time.time() - t0:.1f} s"}


g.SIDE.update({
    "st_systemexit": g.side_st_systemexit,
    "cross_completion": side_cross_completion,
    "cross_trl_batch": side_cross_trl_batch,
    "cross_alarm": side_cross_alarm,
    "stale_alarm": side_stale_alarm,
})


def main():
    what = sys.argv[1]
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    out = {"label": LABEL, "src": SRC, "safetune_rewards_code_file": WHERE, "versions": g.versions()}
    if what == "matrix":
        out["specs"] = {k: v[0] for k, v in SPECS.items()}
        out["cells"] = g.run_matrix(LABEL, SPECS, parallel=4)
    else:
        out["side"] = {}
        for k in ("st_systemexit", "cross_completion", "cross_trl_batch", "cross_alarm", "stale_alarm"):
            out["side"][k] = g.run_side(LABEL, k, timeout=90)
            print("side", k, json.dumps(out["side"][k])[:400], flush=True)
    out["elapsed_s"] = round(time.time() - t0, 1)
    path = OUT / f"{LABEL}-{what}.json"
    path.write_text(json.dumps(out, indent=1, default=str))
    print("wrote", path, "elapsed", out["elapsed_s"])


if __name__ == "__main__":
    main()
