"""Gate 1 regression tests: assert the observed behaviour of the installed wheels.

These tests pass when the reward functions behave as measured on 1 Nov 2026 (aligntune 0.1.28,
safetune 0.1.10). A failure after an upgrade means the behaviour changed (for example, a fix
landed) and the results file needs a re-run. They read the runner output in results/; run
scripts/run_all.sh first.
"""
import json
import pathlib

import pytest

RES = pathlib.Path(__file__).resolve().parents[1] / "results"
DATA = json.loads((RES / "gate1-2026-11-01.json").read_text())
TASKS = DATA["tasks"]
IDX = {(c["pkg"], c["reward"], c["mode"], c["task"], c["exploit"], c["fenced"]): c for c in DATA["cells"]}
SIDE = DATA["side_experiments"]


def scores(pkg, reward, mode, exploit, fenced):
    out = []
    for t in TASKS:
        c = IDX[(pkg, reward, mode, t, exploit, fenced)]
        assert c["status"] == "ok", c
        out.append(c["score"])
    return out


def test_versions_are_the_audited_wheels():
    assert DATA["versions"]["aligntune"]["aligntune"] == "0.1.28"
    assert DATA["versions"]["safetune"]["safetune"] == "0.1.10"
    assert DATA["versions"]["aligntune"]["trl"] == "1.7.1"


def test_gate_passes_with_at_least_two_implementations():
    assert DATA["gate"]["PASS"]
    assert len(DATA["gate"]["tests_mode_paying_implementations"]) >= 2


@pytest.mark.parametrize("pkg,reward,exploit,fenced", [
    ("aligntune", "code_execution", "print_pass_exit", True),      # claim 2
    ("aligntune", "code_execution", "always_equal", True),
    ("aligntune", "code_correctness", "always_equal", False),      # claim 3 (== comparison)
    ("aligntune", "mbpp_reward", "fake_pass_lines", True),         # claim 4
    ("aligntune", "code_verifiable", "bare_exit", True),
    ("safetune", "code_execution", "print_pass_exit", True),
    ("safetune", "mbpp_reward", "bare_exit", True),                # exit code 0 alone
    ("safetune", "mbpp_reward", "always_equal", True),
])
def test_solves_nothing_exploit_gets_full_marks_with_tests(pkg, reward, exploit, fenced):
    assert min(scores(pkg, reward, "tests", exploit, fenced)) >= 0.98


def test_aligntune_code_execution_pays_stub_without_tests():  # claim 1
    assert scores("aligntune", "code_execution", "no_tests", "stub", True) == [1.0] * 5


def test_aligntune_code_correctness_pays_half_for_empty_string_without_tests():  # claim 3
    assert scores("aligntune", "code_correctness", "no_tests", "empty", False) == [0.5] * 5


def test_aligntune_systemexit_escapes_code_execution():  # claim 6
    assert SIDE["aligntune"]["at_systemexit_compute"]["exc"].startswith("SystemExit")


def test_trl_run_ends_silently_on_sys_exit():
    txt = DATA["systemexit_trl.txt"]
    block = txt.split("=== middle completion: sys.exit(0)")[1].split("===")[0]
    assert "process exit status: 0" in block and "AFTER" not in block


def test_cross_completion_patch_flips_wrong_answer():  # claim 5
    r = SIDE["aligntune"]["at_cross_isclose"]["result"]
    assert r["B_alone_first"] == 0.0 and r["B_after_A"] == 1.0
    b = SIDE["aligntune"]["at_cross_isclose_bridge"]["result"]
    assert b["batch[B,B]"] == [0.0, 0.0] and b["batch[A,B]"] == [1.0, 1.0]


def test_code_correctness_has_no_timeout():
    assert SIDE["aligntune"]["at_loop_correctness_tests"]["status"] == "timeout"


def test_recipe_tests_never_reach_rewards():
    seen = DATA["recipe_simulation"]["seen_by_compute"]
    assert all(not v["test_cases_in_kwargs"] for v in seen.values())
    s = DATA["recipe_simulation"]["humaneval0_scores"]
    assert s["stub, bare"]["trl_total"] > s["canonical full function, fenced"]["trl_total"]
