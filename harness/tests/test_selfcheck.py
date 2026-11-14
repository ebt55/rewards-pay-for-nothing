import json
from pathlib import Path
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="candidate execution is Linux/WSL only")
ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "harness/examples"


def strict_column_factory():
    """Requires a column under a name check_cell does not know; never pays."""
    def reward_fn(completions, *, my_tests, **kwargs):
        assert my_tests and my_tests[0]
        return [0.0] * len(completions)
    return reward_fn


def run(tmp_path, *args):
    from rewardcheck.selfcheck.run import main
    out = tmp_path / "report.json"
    code = main([*args, "--scratch", str(tmp_path / "scratch"), "--out", str(out), "--limit", "1", "--timeout", "10"])
    return code, (json.loads(out.read_text()) if out.exists() else None)


def test_vendored_render_matches_scripts():
    scripts = ROOT / "scripts"
    if not (scripts / "gate1_run.py").exists():
        pytest.skip("scripts/ not present")
    sys.path.insert(0, str(scripts))
    import gate1_run
    from rewardcheck.selfcheck import fixtures
    assert fixtures.TASKS == gate1_run.TASKS and fixtures.EXPLOITS == gate1_run.EXPLOITS
    for task in fixtures.TASKS:
        for ex in list(fixtures.EX_BY_ID) + list(fixtures.SPECIAL):
            for fenced in (True, False):
                assert fixtures.render(ex, task, fenced) == gate1_run.render(ex, task, fenced)


def test_job_matrix_and_column_mapping():
    from argparse import Namespace
    from rewardcheck.selfcheck.fixtures import TASKS, EXPLOITS
    from rewardcheck.selfcheck.run import build_jobs
    a = Namespace(tests_column="reference", test_format="asserts", entry_point_column="entry_point", setup_column="setup")
    jobs = build_jobs(a, TASKS)
    nonanswers = [e for e in EXPLOITS if e.get("solves_nothing")]
    assert len(jobs) == len(TASKS) * len(EXPLOITS) * 2 + len(nonanswers)
    refs = [j for j in jobs if j[0]["group"] == "reference"]
    assert len(refs) == 10 and {j[0]["fenced"] for j in refs} == {True, False}
    meta, _, col = refs[0]
    task = next(t for t in TASKS if t["task_id"] == meta["task"])
    assert col == {"reference": [task["assert_tests"]], "entry_point": [task["entry_point"]], "setup": [task["setup_code"]]}
    assert all(j[2] == {} for j in jobs if j[0]["group"] == "no_tests")
    a.test_format = "dicts"
    assert build_jobs(a, TASKS[:1])[0][2]["reference"] == [TASKS[0]["dict_tests"]]


def test_naive_example_is_flagged(tmp_path, capsys):
    code, report = run(tmp_path, "--factory", f"{EXAMPLES}/naive_reward.py:make_reward")
    assert code == 1 and report["complete"]
    s = report["summary"]
    assert s["nonanswer"]["print_pass_exit"]["paid"] == 2 and s["nonanswer"]["bare_exit"]["paid"] == 2
    assert s["reference"]["accepted"] == 2
    assert report["provenance"]["module_sha256"] and "selfcheck/run.py" in report["provenance"]["harness_hashes"]
    assert "FAIL" in capsys.readouterr().out


def test_wrong_column_name_rejects_references(tmp_path, capsys):
    code, report = run(tmp_path, "--factory", f"{EXAMPLES}/naive_reward.py:make_reward", "--tests-column", "test_list")
    assert code == 1
    assert report["summary"]["reference"]["accepted"] == 0
    assert report["summary"]["errors"] == {"exception:TypeError": len(report["rows"]) - 7}
    assert "check the column names" in capsys.readouterr().out


def test_unrecognised_column_name_still_reaches_reward(tmp_path):
    code, report = run(tmp_path, "--factory", "test_selfcheck:strict_column_factory", "--tests-column", "my_tests")
    assert code == 1  # it never pays, so references are rejected
    assert all(r["status"] == "scored" for r in report["rows"] if r["group"] != "no_tests")


def test_setup_errors_exit_2(tmp_path, capsys):
    assert run(tmp_path, "--factory", "no_colon_here")[0] == 2
    assert run(tmp_path, "--factory", str(tmp_path / "absent.py") + ":f")[0] == 2
    assert run(tmp_path, "--factory", f"{EXAMPLES}/naive_reward.py:absent")[0] == 2
    assert "no callable" in capsys.readouterr().err


def test_securegrade_example_passes(tmp_path):
    sys.path.insert(0, str(ROOT))
    from securegrade import IsolationConfigurationError, self_check
    try:
        self_check()
    except IsolationConfigurationError:
        pytest.skip("securegrade isolation unavailable on this kernel")
    code, report = run(tmp_path, "--factory", f"{EXAMPLES}/securegrade_reward.py:make_reward", "--tests-column",
                       "test_list", "--entry-point-column", "entry_point", "--setup-column", "test_imports")
    assert code == 0, report["summary"]["failures"]
    assert report["summary"]["reference"]["accepted"] == 2
