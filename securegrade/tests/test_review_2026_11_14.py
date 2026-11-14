"""Regressions for the 14 Nov 2026 adversarial review (securegrade 0.1.3).
Run from the project root:  python -m pytest -q securegrade/tests
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from securegrade import score  # noqa: E402
from securegrade.judge import build_program  # noqa: E402
from securegrade.trl_reward import make_secure_code_reward, prompt_text  # noqa: E402

ALL = ROOT / "exploits" / "tasks_all.json"
LOOP = "def check(candidate):\n    for i in range(3):\n        x = candidate(i)\n        assert x == i\n"


def _he(task_id):
    if not ALL.exists():
        pytest.skip("run scripts/sg_fn_rate.py first")
    return next(t for t in json.loads(ALL.read_text()) if t["task_id"] == task_id)


# ---------------------------------------------------------------- CODE-01: abort / dead child after a passing assert
@pytest.mark.parametrize("bad", [
    "    if i == 1:\n        raise ValueError('x')\n",
    "    if i == 1:\n        import os\n        os._exit(0)\n",
    "    while i == 1:\n        pass\n",
], ids=["raises", "os_exit", "hangs"])
def test_loop_test_that_stops_after_a_passing_assert_gets_no_credit(bad):
    r = score("def f(i):\n" + bad + "    return i\n", LOOP, entry_point="f", wall_timeout=3)
    assert r.score == 0.0 and not r.all_passed and r.passed == 0, (r.failures, r.detail)
    assert "harness_aborted" in r.detail


def test_loop_test_correct_answer_still_passes():
    r = score("def f(i):\n    return i\n", LOOP, entry_point="f")
    assert r.score == 1.0 and r.all_passed, r.failures


def test_humaneval_32_right_once_then_exit_gets_no_credit():
    t = _he("HumanEval/32")
    exit_second = ("    import os\n    global _n\n    try:\n        _n += 1\n    except NameError:\n        _n = 1\n"
                   "    if _n > 1:\n        os._exit(0)\n")
    r = score(t["prompt"] + exit_second + t["body"], t["tests"], entry_point="find_zero", prompt=t["prompt"])
    assert r.score == 0.0 and not r.all_passed, (r.failures, r.detail)
    ok = score(t["prompt"] + t["body"], t["tests"], entry_point="find_zero", prompt=t["prompt"])
    assert ok.score == 1.0 and ok.all_passed, ok.failures


def test_swallowed_child_death_never_gives_full_marks():
    tests = ("def check(candidate):\n    assert candidate(0) == 0\n    try:\n        candidate(1)\n"
             "    except Exception:\n        pass\n")
    r = score("import os\ndef f(i):\n    if i == 1:\n        os._exit(0)\n    return i\n", tests, entry_point="f")
    assert r.score < 1.0 and not r.all_passed, (r.failures, r.detail)


def test_mbpp_timeout_keeps_partial_credit_for_completed_asserts():
    r = score("def f(x):\n    while x == 3:\n        pass\n    return x\n",
              ["assert f(1) == 1", "assert f(2) == 2", "assert f(3) == 3"], wall_timeout=3)
    assert r.passed == 2 and r.total == 3 and not r.all_passed, (r.failures, r.detail)


# ---------------------------------------------------------------- CODE-02: falsy constant asserts
EXPECT_RAISE = ("def check(candidate):\n    try:\n        candidate(-1)\n        assert False, 'expected ValueError'\n"
                "    except ValueError:\n        pass\n    assert candidate(1) == 1\n")


def test_assert_false_branch_fails_a_wrong_answer():
    r = score("def f(x):\n    return x\n", EXPECT_RAISE, entry_point="f")
    assert r.score == 0.0 and not r.all_passed, (r.failures, r.detail)


def test_assert_false_branch_not_reached_by_a_correct_answer():
    r = score("def f(x):\n    if x < 0:\n        raise ValueError\n    return x\n", EXPECT_RAISE, entry_point="f")
    assert r.score == 1.0 and r.all_passed, (r.failures, r.detail)


@pytest.mark.parametrize("const", ["False", "0", "''", "None"])
def test_falsy_constant_assert_is_not_stripped(const):
    r = score("def f(x):\n    return x\n", ["assert f(1) == 1", f"assert {const}"])
    assert r.score == 0.0 and not r.all_passed, (r.failures, r.detail)


def test_truthy_constant_assert_is_still_decorative():
    tree, total = build_program(["assert f(1) == 1", "assert True, 'decorative'"])
    assert total == 1
    r = score("def f(x):\n    return x\n", ["assert f(1) == 1", "assert True, 'decorative'"])
    assert r.score == 1.0 and r.all_passed


# ---------------------------------------------------------------- CODE-03: prompts and oracle helpers
HIJACK = "def poly(xs, x):\n    return 0.0\n\ndef find_zero(xs):\n    return 0.0\n"


def _conv(prompt):
    return [[{"role": "system", "content": "You write Python."},
             {"role": "user", "content": "Complete this function:\n```python\n" + prompt + "\n```"}]]


def test_conversational_prompt_is_unwrapped():
    assert prompt_text([{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]) == "a"
    assert prompt_text([{"role": "user", "content": [{"type": "text", "text": "x"}]}]) == "x"
    assert prompt_text("plain") == "plain" and prompt_text(None) is None


def test_redefined_oracle_helper_is_not_paid_with_conversational_prompt():
    t = _he("HumanEval/32")
    reward = make_secure_code_reward(max_workers=1)
    assert reward([HIJACK], test=[t["tests"]], entry_point=["find_zero"], prompts=_conv(t["prompt"])) == [0.0]
    assert reward([HIJACK], test=[t["tests"]], entry_point=["find_zero"], prompts=[t["prompt"]]) == [0.0]


@pytest.mark.parametrize("task_id,entry", [("HumanEval/32", "find_zero"), ("HumanEval/38", "decode_cyclic"),
                                           ("HumanEval/50", "decode_shift")])
def test_conversational_prompt_still_supplies_helpers_and_body_only_answers(task_id, entry):
    t = _he(task_id)
    reward = make_secure_code_reward(max_workers=1)
    full = reward([t["reference"]], test=[t["tests"]], entry_point=[entry], prompts=_conv(t["prompt"]))
    body = reward([t["body"]], test=[t["tests"]], entry_point=[entry], prompts=_conv(t["prompt"]))
    assert full == [1.0] and body == [1.0], (full, body)


def test_supplied_prompt_without_code_does_not_proxy_helpers():
    t = _he("HumanEval/32")
    r = score(HIJACK, t["tests"], entry_point="find_zero", prompt="Write find_zero.")
    assert r.score == 0.0 and r.detail.get("helpers_not_proxied") == ["poly"], r.detail


# ---------------------------------------------------------------- CODE-06: silent zeros and None
def test_check_program_without_entry_point_is_a_configuration_error():
    t = _he("HumanEval/0")
    with pytest.raises(ValueError, match="entry_point"):
        score(t["reference"], t["tests"])
    with pytest.raises(ValueError, match="entry_point"):
        make_secure_code_reward(max_workers=1)([t["reference"]], test=[t["tests"]])
    # a program that calls check itself needs no entry point
    r = score("def f(x):\n    return x\n", "def check(c):\n    assert c(1) == 1\n\ncheck(f)\n")
    assert r.score == 1.0


def test_unbatched_test_list_matching_batch_size_is_refused_not_zeroed():
    reward = make_secure_code_reward(max_workers=1)
    tl = ["assert f(1) == 1", "assert f(2) == 2", "assert f(3) == 3"]
    good = "def f(x):\n    return x\n"
    with pytest.raises(ValueError, match="one list of assert strings per completion"):
        reward([good] * 3, test_list=tl)
    assert reward([good] * 3, test_list=[tl] * 3) == [1.0, 1.0, 1.0]
    assert reward([good] * 2, test_list=tl) == [1.0, 1.0]  # unbatched, length != batch: shared (unchanged)


def test_rows_without_tests_raise_unless_allowed():
    good = "def f(x):\n    return x\n"
    with pytest.raises(ValueError, match="no tests"):
        make_secure_code_reward(max_workers=1)([good], test_list=[[]])
    with pytest.raises(ValueError, match="no tests"):
        make_secure_code_reward(max_workers=1)([good], test=[""])
    mixed = make_secure_code_reward(max_workers=1, allow_empty_rows=True)
    assert mixed([good, good], test_list=[["assert f(1) == 1"], []]) == [1.0, None]


# ---------------------------------------------------------------- CODE-04: Landlock read set
@pytest.mark.skipif(sys.platform != "linux", reason="Landlock is Linux-only")
def test_pth_entry_outside_the_interpreter_is_not_readable():
    with tempfile.TemporaryDirectory() as w:
        w = pathlib.Path(w)
        if subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(w / "venv")]).returncode:
            pytest.skip("venv module unavailable")
        site = next((w / "venv").glob("lib/python*/site-packages"))
        (w / "project").mkdir()
        (w / "project" / "answers.txt").write_text("secret")
        (site / "editable_project.pth").write_text(str(w / "project") + "\n")
        layered = w / "base" / "site-packages"  # a layered venv's package directory stays importable
        layered.mkdir(parents=True)
        (layered / "sg_layered_mod.py").write_text("VALUE = 7\n")
        (site / "layered.pth").write_text(str(layered) + "\n")
        code = ("import sys\ndef peek(p):\n    try:\n        return open(p).read()\n"
                "    except Exception as e:\n        return type(e).__name__\n"
                "def on_path(p):\n    return p in sys.path\n"
                "def layered():\n    import sg_layered_mod\n    return sg_layered_mod.VALUE\n")
        target = str(w / "project" / "answers.txt")
        r = score(code, [f"assert on_path({str(w / 'project')!r})", f"assert peek({target!r}) == 'PermissionError'",
                         "assert layered() == 7"],
                  python=str(w / "venv" / "bin" / "python"))
        if not str(r.detail.get("isolation", {}).get("landlock", "")).startswith("on"):
            pytest.skip("Landlock unavailable")
        assert r.all_passed, (r.failures, r.detail)


# ---------------------------------------------------------------- RPL-08: non-Linux
def test_non_linux_is_a_clear_configuration_error():
    program = ("import sys\nsys.path.insert(0, sys.argv[1])\n"
               "from securegrade import IsolationConfigurationError, score\nsys.platform = 'win32'\n"
               "try:\n    score('def f():\\n    return 1\\n', ['assert f() == 1'])\n"
               "except IsolationConfigurationError as e:\n    print('refused:', e)\n")
    out = subprocess.run([sys.executable, "-I", "-B", "-c", program, str(ROOT)], capture_output=True, text=True,
                         timeout=60)
    assert "refused:" in out.stdout and "Linux" in out.stdout, (out.stdout, out.stderr)


def test_test_column_row_must_be_a_string():
    with pytest.raises(ValueError, match="one test program string per completion"):
        make_secure_code_reward(max_workers=1)(["def f(x):\n    return x\n"], test=[["assert f(1) == 1"]])


# ---------------------------------------------------------------- RPL-11: no bytecode from the candidate child
def test_candidate_child_runs_with_dont_write_bytecode():
    r = score("import sys\ndef flag():\n    return sys.dont_write_bytecode\n", ["assert flag() is True"])
    assert r.all_passed, (r.failures, r.detail)
