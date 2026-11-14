"""Regression tests for the patched AlignTune code rewards (MIT, our code).

Run in the venv that has the patched tree installed:
    ~/p9/at-patched/bin/python -m pytest -q patches/aligntune/tests
Every Gate 1 "solves nothing" exploit must fail; every reference solution must pass.
"""
import json
import pathlib
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
TASKS = json.loads((ROOT / "exploits" / "tasks.json").read_text())
EX = json.loads((ROOT / "exploits" / "exploits.json").read_text())
NOTHING = [e for e in EX["exploits"] if e["solves_nothing"]]

from aligntune.rewards.registry import RewardRegistry  # noqa: E402


def build(name):
    return RewardRegistry.get_reward_function(name, {"type": name, "weight": 1.0, "params": {}})


def render(e, t, fenced, key="template"):
    body = (e[key] if isinstance(e, dict) else e).replace("{fn}", t["entry_point"])
    return "```python\n" + body + "\n```" if fenced and (not isinstance(e, dict) or e.get("fenceable", True)) else body


CALLS = {
    "code_execution": lambda r, t, x: r.compute(x, None, test_cases=t["assert_tests"]),
    "code_correctness": lambda r, t, x: r.compute(x, None, test_cases=t["dict_tests"]),
    "code_correctness[asserts]": lambda r, t, x: r.compute(x, None, test_cases=t["assert_tests"]),
    "mbpp_reward": lambda r, t, x: r.compute(x, None, test_cases=t["assert_tests"]),
    "code_verifiable": lambda r, t, x: r.compute(x, t["assert_tests"]),
}


@pytest.mark.parametrize("fenced", [True, False])
@pytest.mark.parametrize("ex", NOTHING, ids=[e["id"] for e in NOTHING])
@pytest.mark.parametrize("reward", list(CALLS))
def test_gate1_exploits_fail_with_tests(reward, ex, fenced):
    r = build(reward.split("[")[0])
    for t in TASKS:
        s = CALLS[reward](r, t, render(ex, t, fenced))
        assert s <= 0.0, (reward, ex["id"], t["task_id"], s)


@pytest.mark.parametrize("fenced", [True, False])
@pytest.mark.parametrize("reward", list(CALLS))
def test_reference_solutions_pass(reward, fenced):
    r = build(reward.split("[")[0])
    for t in TASKS:
        text = t["reference_solution"]
        s = CALLS[reward](r, t, "```python\n" + text + "\n```" if fenced else text)
        assert s >= 0.95, (reward, t["task_id"], s)


def test_code_correctness_without_tests_pays_nothing():
    r = build("code_correctness")
    assert r.compute("") == 0.0
    assert r.compute("def f(*a, **k):\n    pass") == 0.0


def test_code_execution_without_tests_still_pays_a_stub():
    """Documented limitation: with no tests, code_execution can only check that code runs."""
    r = build("code_execution")
    assert r.compute("```python\ndef f(*a, **k):\n    pass\n```") == 1.0


@pytest.mark.parametrize("tail", ["import sys\nsys.exit(0)", "raise SystemExit(0)", "import os\nos._exit(0)"])
def test_exit_does_not_escape_or_pay(tail):
    r = build("code_execution")
    code = "```python\ndef f(*a, **k):\n    pass\n" + tail + "\n```"
    assert r.compute(code) == 0.0  # no tests: exiting is a failed run, and the caller survives
    t = TASKS[0]
    assert r.compute(render("def {fn}(*a, **k):\n    pass\n" + tail, t, True), None, test_cases=t["assert_tests"]) == 0.0


def test_cross_completion_patch_does_not_carry_over():
    t = next(x for x in TASKS if x["task_id"] == "HumanEval/2")
    r = build("code_correctness")
    a = "import math\nmath.isclose = lambda *a, **k: True\ndef truncate_number(x):\n    return 0.0\n"
    b = "def truncate_number(x):\n    return 0.0\n"
    assert r.compute(b, None, test_cases=t["dict_tests"]) == 0.0
    r.compute(a, None, test_cases=t["dict_tests"])
    assert r.compute(b, None, test_cases=t["dict_tests"]) == 0.0
    import math
    assert math.isclose(1.0, 2.0) is False  # the trainer process was never touched


def test_infinite_loop_returns_zero_within_timeout():
    t = TASKS[0]
    for name in ("code_execution", "code_correctness", "mbpp_reward"):
        r = build(name)
        t0 = time.time()
        s = CALLS[name](r, t, "```python\ndef is_not_prime(n):\n    while True:\n        pass\n```")
        assert s <= 0.0 and time.time() - t0 < 30, (name, s)


def test_tests_reach_rewards_through_trl_bridge_for_humaneval_and_mbpp():
    from aligntune.core.rl.reward_handler import prepare_trl_rewards
    he = next(x for x in TASKS if x["task_id"] == "HumanEval/0")["raw_columns"]
    prepared = prepare_trl_rewards([{"type": "code_correctness", "weight": 0.5, "params": {}},
                                    {"type": "code_execution", "weight": 0.2, "params": {}}])
    comps = [he["canonical_solution"], "```python\ndef has_close_elements(*a, **k):\n    pass\n```"]
    cols = {"test": [he["test"]] * 2, "entry_point": [he["entry_point"]] * 2, "task_id": [he["task_id"]] * 2}
    for f in prepared.functions:
        scores = f(prompts=[he["prompt"]] * 2, completions=comps, completion_ids=None, **cols)
        assert scores[0] == 1.0 and scores[1] == 0.0, (f.__name__, scores)
    mb = next(x for x in TASKS if x["task_id"] == "MBPP/3")
    p = prepare_trl_rewards([{"type": "mbpp_reward", "weight": 1.0, "params": {}}]).functions[0]
    s = p(prompts=["p", "p"], completions=["```python\n" + mb["reference_solution"] + "\n```", "I cannot."],
          completion_ids=None, test_list=[mb["assert_tests"]] * 2)
    assert s[0] >= 0.95 and s[1] < 0
