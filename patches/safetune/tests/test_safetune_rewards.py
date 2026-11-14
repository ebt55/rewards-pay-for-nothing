"""Regression tests for SafeTune's code rewards (our code, MIT; it only *calls* SafeTune, which is LSAL).

They state the behaviour a fixed SafeTune should have. Cases known to fail on safetune 0.1.10 are
marked xfail(strict=True): when a fix lands they turn into failures ("XPASS(strict)"), which is the
signal to drop the marker. Run in the safetune venv:
    ~/p9/st/bin/python -m pytest -q patches/safetune/tests
"""
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
TASKS = json.loads((ROOT / "exploits" / "tasks.json").read_text())
EX = json.loads((ROOT / "exploits" / "exploits.json").read_text())
NOTHING = [e for e in EX["exploits"] if e["solves_nothing"]]

from safetune.rewards.registry import RewardRegistry  # noqa: E402


def build(name):
    return RewardRegistry.get_reward_function(name, {"type": name, "weight": 1.0, "params": {}})


def render(body, t, fenced):
    body = body.replace("{fn}", t["entry_point"])
    return "```python\n" + body + "\n```" if fenced else body


CALLS = {
    "code_execution": lambda r, t, x: r.compute(x, None, test_cases=t["assert_tests"]),
    "code_execution[dicts]": lambda r, t, x: r.compute(x, None, test_cases=t["dict_tests"]),
    "code_correctness": lambda r, t, x: r.compute(x, None, test_cases=t["assert_tests"]),
    "mbpp_reward": lambda r, t, x: r.compute(x, None, test_list=t["assert_tests"]),
}

# Measured on safetune 0.1.10 (results/gate1-2026-11-01.md): these exploits score 1.0 on all 5 tasks.
KNOWN_PAYING = {
    ("code_execution", "print_pass_exit"), ("code_execution", "always_equal"),
    ("code_execution[dicts]", "print_pass_exit"), ("code_execution[dicts]", "fake_pass_lines"),
    ("code_execution[dicts]", "always_equal"),
    ("code_correctness", "print_pass_exit"), ("code_correctness", "always_equal"),
    ("mbpp_reward", "print_pass_exit"), ("mbpp_reward", "bare_exit"), ("mbpp_reward", "always_equal"),
}
# Correct bare answers with an import above the def lose it to the extractor (2 of 5 pass bare).
KNOWN_FN = {("code_execution", False), ("code_execution[dicts]", False), ("code_correctness", False),
            ("code_execution[dicts]", True)}  # dict path also takes the first callable (typing.List) and compares floats with ==

CASES = [pytest.param(rw, e, marks=pytest.mark.xfail(strict=True, reason="pays on safetune 0.1.10"))
         if (rw, e["id"]) in KNOWN_PAYING else pytest.param(rw, e)
         for rw in CALLS for e in NOTHING]


@pytest.mark.parametrize("reward,ex", CASES, ids=[f"{c.values[0]}-{c.values[1]['id']}" for c in CASES])
def test_solves_nothing_exploit_scores_zero(reward, ex):
    r = build(reward.split("[")[0])
    worst = max(CALLS[reward](r, t, render(ex["template"], t, f) if ex.get("fenceable", True) else ex["template"])
                for t in TASKS for f in (True, False))
    assert worst <= 0.0


REF = [pytest.param(rw, f, marks=pytest.mark.xfail(strict=True, reason="false negative on safetune 0.1.10"))
       if (rw, f) in KNOWN_FN else pytest.param(rw, f) for rw in CALLS for f in (True, False)]


@pytest.mark.parametrize("reward,fenced", REF)
def test_reference_solutions_score_full_marks(reward, fenced):
    r = build(reward.split("[")[0])
    for t in TASKS:
        text = t["reference_solution"]
        assert CALLS[reward](r, t, "```python\n" + text + "\n```" if fenced else text) >= 0.95, t["task_id"]


@pytest.mark.xfail(strict=True, reason="safetune 0.1.10: code_execution without tests pays 1.0 for exiting with status 0")
def test_exit_without_tests_is_not_success():
    r = build("code_execution")
    assert r.compute("```python\nimport os\ndef f():\n    pass\nos._exit(0)\n```") == 0.0
