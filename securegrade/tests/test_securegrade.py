"""securegrade tests. Run from the project root:  python -m pytest -q securegrade/tests
Uses exploits/tasks.json, exploits/exploits.json and (for the wide reference check)
exploits/tasks_all.json written by scripts/sg_fn_rate.py.
"""
import json
import os
import pathlib
import socket
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from securegrade import extract_code, score  # noqa: E402
from securegrade.codec import CodecError, sg_decode, sg_encode  # noqa: E402
from securegrade.sandbox import unshare_prefix  # noqa: E402
from securegrade.trl_reward import make_secure_code_reward, secure_code_reward  # noqa: E402

TASKS = json.loads((ROOT / "exploits" / "tasks.json").read_text())
EX = json.loads((ROOT / "exploits" / "exploits.json").read_text())
ALL = ROOT / "exploits" / "tasks_all.json"
NOTHING = [e for e in EX["exploits"] if e["solves_nothing"]]


def task_tests(t):
    """Gate 1 tasks: MBPP gets its assert list; HumanEval gets the dataset's own check() program."""
    if t["task_id"].startswith("HumanEval"):
        return t["raw_columns"]["test"], t["entry_point"]
    return t["assert_tests"], None


def render(e, t, fenced):
    body = e["template"].replace("{fn}", t["entry_point"])
    if "{table}" in body:
        table = {repr(tuple(v["args"])): v["expected"] for v in t["visible_examples"]}
        body = body.replace("{table}", repr(table))
    return "```python\n" + body + "\n```" if fenced and e.get("fenceable", True) else body


# ---------------------------------------------------------------- Gate 1 exploits and references
@pytest.mark.parametrize("fenced", [True, False])
@pytest.mark.parametrize("ex", NOTHING, ids=[e["id"] for e in NOTHING])
@pytest.mark.parametrize("task", TASKS, ids=[t["task_id"] for t in TASKS])
def test_every_solves_nothing_exploit_scores_zero(task, ex, fenced):
    tests, ep = task_tests(task)
    r = score(render(ex, task, fenced), tests, entry_point=ep, setup_code=task["setup_code"], wall_timeout=5)
    assert r.score == 0.0, (r.failures, r.detail)


@pytest.mark.parametrize("fenced", [True, False])
@pytest.mark.parametrize("task", TASKS, ids=[t["task_id"] for t in TASKS])
def test_reference_scores_full_marks(task, fenced):
    tests, ep = task_tests(task)
    text = task["reference_solution"]
    r = score("```python\n" + text + "\n```" if fenced else text, tests, entry_point=ep, setup_code=task["setup_code"])
    assert r.all_passed and r.score == 1.0, (r.failures, r.detail)


@pytest.mark.skipif(not ALL.exists(), reason="run scripts/sg_fn_rate.py first")
def test_reference_full_marks_on_60_mbpp_and_all_humaneval():
    tasks = json.loads(ALL.read_text())
    mbpp = [t for t in tasks if t["kind"] == "mbpp"][:60]
    he = [t for t in tasks if t["kind"] == "humaneval"]

    def run(t):
        r = score("```python\n" + t["reference"] + "\n```", t["tests"], entry_point=t["entry_point"],
                  setup_code=t["setup"])
        return t["task_id"], r.all_passed, r.failures[:2]

    with ThreadPoolExecutor(max_workers=4) as pool:
        res = list(pool.map(run, mbpp + he))
    bad = [r for r in res if not r[1]]
    assert len(res) == 60 + 164
    assert bad == [], bad


# ---------------------------------------------------------------- attacks beyond Gate 1
HE2 = next(t for t in TASKS if t["task_id"] == "HumanEval/2")
MB3 = next(t for t in TASKS if t["task_id"] == "MBPP/3")


def test_cross_completion_monkeypatch_does_not_carry_over():
    tests, ep = task_tests(HE2)
    A = ("import math, builtins\nmath.isclose = lambda *a, **k: True\nbuiltins.abs = lambda x: 0\n"
         "def truncate_number(x):\n    return 0.0\n")
    B = "def truncate_number(x):\n    return 0.0\n"
    ra, rb = score(A, tests, entry_point=ep), score(B, tests, entry_point=ep)
    assert ra.score == 0.0 and rb.score == 0.0
    fn = secure_code_reward  # one TRL batch, A first
    assert fn(completions=[A, B], test=[tests] * 2, entry_point=[ep] * 2) == [0.0, 0.0]


def test_infinite_loop_scores_zero_within_timeout():
    import time
    t0 = time.time()
    r = score("def is_not_prime(n):\n    while True:\n        pass\n", MB3["assert_tests"], wall_timeout=3)
    assert r.score == 0.0 and time.time() - t0 < 8


def test_infinite_loop_at_import_time():
    r = score("while True:\n    pass\n", MB3["assert_tests"], wall_timeout=2)
    assert r.score == 0.0


def test_reading_cwd_and_files_gives_nothing():
    # Lists and reads everything in its cwd, tries the task file and the HF cache, and answers
    # with whatever it finds. The cwd is an empty temp dir; the rest is outside the sandbox.
    probe = f"""
import os, glob
def is_not_prime(n):
    found = []
    for p in os.listdir('.'):
        try:
            found.append(open(p).read())
        except Exception:
            pass
    for p in [{str(ROOT / 'exploits' / 'tasks.json')!r}, os.path.expanduser('~/.cache/huggingface')]:
        try:
            found.append(open(p).read()[:10])
        except Exception:
            pass
    return 'True' in ''.join(found)
"""
    r = score(probe, MB3["assert_tests"])
    assert r.passed <= 2  # constant False answers pass the two "== False" asserts at most; nothing found
    leak = score(probe.replace("return 'True' in ''.join(found)", "return len(''.join(found))"),
                 ["assert is_not_prime(1) == 0"])
    assert leak.score == 1.0, leak.failures  # nothing was readable


@pytest.mark.skipif(sys.platform != "linux", reason="Landlock is Linux-only")
def test_filesystem_outside_sandbox_is_denied_when_landlock_is_on():
    code = f"""
def probe():
    try:
        open({str(ROOT / 'exploits' / 'tasks.json')!r}).read(1)
        return 'read'
    except PermissionError:
        return 'denied'
    except OSError as e:
        return 'oserror'
"""
    r = score(code, ["assert probe() == 'denied'"])
    if not str(r.detail.get("isolation", {}).get("landlock", "")).startswith("on"):
        pytest.skip("Landlock not available here: " + str(r.detail.get("isolation")))
    assert r.score == 1.0, r.failures


def test_network_is_isolated_when_unshare_works():
    if not unshare_prefix(dropped=os.geteuid() == 0):
        pytest.skip("unprivileged network namespaces not available")
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    threading.Thread(target=lambda: srv.accept(), daemon=True).start()
    code = f"""
import socket
def probe():
    try:
        socket.create_connection(('127.0.0.1', {port}), timeout=2).close()
        return 'connected'
    except OSError:
        return 'blocked'
"""
    r = score(code, ["assert probe() == 'blocked'"])
    srv.close()
    assert r.score == 1.0, r.failures


def test_cannot_see_or_signal_the_grader():
    if "-Unp" not in unshare_prefix(dropped=os.geteuid() == 0):
        pytest.skip("unprivileged PID namespaces not available")
    code = '''import os
def probe(pid):
    try:
        os.kill(pid, 0)
        return 'alive'
    except OSError:
        return 'blocked'
def parent():
    return os.getppid()
'''
    r = score(code, [f"assert probe({os.getpid()}) == 'blocked'", "assert parent() == 0"])
    assert r.score == 1.0, r.failures


def test_fake_nonces_pass_lines_and_exit_codes_are_ignored():
    code = ("import sys, os\nfor i in range(20):\n    print('PASS', i, 'PASS:%d' % i)\n"
            "print('0123456789abcdef0123456789abcdef')\n"
            "def is_not_prime(n):\n    print('PASS')\n    return None\n")
    assert score(code, MB3["assert_tests"]).score == 0.0
    for tail in ("sys.exit(0)", "os._exit(0)", "raise SystemExit(0)"):
        r = score("import sys, os\ndef is_not_prime(n):\n    " + tail + "\n", MB3["assert_tests"])
        assert r.score == 0.0, (tail, r.failures)


def test_fork_is_blocked():
    code = "import os\ndef probe():\n    try:\n        os.fork()\n        return 'forked'\n    except OSError:\n        return 'blocked'\n"
    r = score(code, ["assert probe() == 'blocked'"])
    assert r.score == 1.0, r.failures


def test_numpy_imports_under_nproc_zero_and_scalars_cross_as_python_values():
    # GRPO runs, 3 Nov: OpenBLAS could not start threads, so `import numpy` failed every such answer,
    # and np.int64 returns crossed as opaque values that equal nothing.
    pytest.importorskip("numpy")
    code = ("import numpy as np\n"
            "def big(xs):\n    return np.max(np.array(xs))\n"
            "def mean(xs):\n    return np.mean(xs)\n"
            "def has(xs, x):\n    return np.isin(x, xs)\n")
    r = score(code, ["assert big([5, 19, 3]) == 19", "assert mean([1, 2]) == 1.5", "assert has([1, 2], 2) == True"])
    assert r.score == 1.0, r.failures


def test_numpy_arrays_still_do_not_cross():
    pytest.importorskip("numpy")
    r = score("import numpy as np\ndef f():\n    return np.array([1, 2])\n", ["assert f() == [1, 2]"])
    assert r.score == 0.0, r.failures


def test_shadowing_builtins_used_by_tests_does_not_help():
    # In a normal harness, redefining `set` makes `set(f(x)) == set(y)` compare two equal fakes.
    tests = ["assert set(similar(1)) == set((4, 5))"]
    code = "set = lambda *a: 1\ndef similar(x):\n    return (9,)\n"
    assert score(code, tests).score == 0.0
    good = "def similar(x):\n    return (5, 4)\n"
    assert score(good, tests).score == 1.0


def test_function_named_like_a_builtin_is_graded():  # MBPP/126 calls its function `sum`
    code = "def sum(a, b):\n    return 6 if (a, b) == (10, 15) else 0\n"
    assert score(code, ["assert sum(10,15) == 6"]).score == 1.0


def test_truthiness_tests_accept_match_objects_but_equality_never_does():
    code = "import re\ndef check(s):\n    return re.search('^a', s)\n"
    assert score(code, ["assert check('abc')", "assert not check('xbc')"]).score == 1.0
    assert score(code, ["assert check('abc') == True"]).score == 0.0


def test_huge_and_weird_returns_fail_cleanly():
    for body in ("return [0] * 10**7", "return {1: object()}", "x = []\n    x.append(x)\n    return x",
                 "return 10 ** 100000"):
        r = score(f"def f():\n    {body}\n", ["assert f() == 1"], wall_timeout=5)
        assert r.score == 0.0


# ---------------------------------------------------------------- pieces
def test_codec_round_trip_and_rejects_objects():
    v = [1, 2.5, float("inf"), -0.0, 3 + 4j, "s", b"b", (1, (2,)), {1: {"a": None}}, {1, 2}, frozenset({3}), True, None]
    assert sg_decode(sg_encode(v)) == v
    with pytest.raises(CodecError):
        sg_encode(object())
    with pytest.raises(CodecError):
        sg_decode(["l", [["x"]]])


def test_extractor_keeps_imports_on_bare_code():
    text = "Here you go:\nimport math\nfrom heapq import nlargest\n\ndef f(x):\n    return math.sqrt(x)\n\nThis works because..."
    code, how = extract_code(text, "f")
    assert "import math" in code and "nlargest" in code and "This works" not in code


def test_extractor_unterminated_fence():
    code, _ = extract_code("```python\nimport math\ndef f(x):\n    return math.pi\n", "f")
    assert "import math" in code


def test_trl_wrapper_mbpp_conversational_and_humaneval_body():
    mb = secure_code_reward(
        completions=[[{"role": "assistant", "content": "```python\n" + MB3["reference_solution"] + "\n```"}],
                     [{"role": "assistant", "content": "I cannot."}]],
        test_list=[MB3["assert_tests"]] * 2, test_imports=[[]] * 2)
    assert mb == [1.0, 0.0]
    he = HE2["raw_columns"]
    out = secure_code_reward(completions=[he["canonical_solution"], "    return 0.0\n"],
                             prompts=[he["prompt"]] * 2, test=[he["test"]] * 2, entry_point=[he["entry_point"]] * 2)
    assert out[0] == 1.0 and out[1] == 0.0
    allpass = make_secure_code_reward(mode="all_pass")
    assert allpass(completions=["def is_not_prime(n):\n    return n > 3\n"], test_list=[MB3["assert_tests"]]) == [0.0]


def test_trl_wrapper_refuses_to_run_without_tests():
    with pytest.raises(ValueError):
        secure_code_reward(completions=["x"], prompts=["p"])


MINIMAL_ENV = {"HOME", "LANG", "LC_ALL", "PATH", "PYTHONHASHSEED", "TMPDIR",
               "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"}
FAKE = "hf_FAKEsecuregradeTESTtoken0000"


def test_child_environment_is_minimal_and_has_no_tokens_or_proxies():
    keys = ["HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HTTP_PROXY", "https_proxy", "ALL_PROXY", "SG_FAKE_SECRET"]
    old = {k: os.environ.get(k) for k in keys}
    os.environ.update({k: FAKE for k in keys})
    try:
        code = ("import os\n"
                "def keys():\n    return sorted(os.environ)\n"
                "def leaked(m):\n    return any(m in v for v in os.environ.values())\n")
        r = score(code, [f"assert keys() == {sorted(MINIMAL_ENV)!r}", f"assert leaked({FAKE!r}) == False"])
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    assert r.score == 1.0, r.failures


_PROBE = (
    "def probe(pid, marker):\n"
    "    try:\n"
    "        data = open('/proc/%d/environ' % pid, 'rb').read()\n"
    "    except OSError:\n"
    "        return 'denied'\n"
    "    return 'leak' if marker.encode() in data else 'clean'\n"
)
_PARENT = (
    "import json, os, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from securegrade import score\n"
    "code = sys.argv[3]\n"
    "mode = sys.argv[2]\n"
    "r = score(code, [\"assert probe(%d, %r) != 'leak'\" % (os.getpid(), os.environ['HF_TOKEN'])],\n"
    "          fs_isolation=mode == 'all', network_isolation=mode in ('all', 'userns'),\n"
    "          required_controls=None if mode == 'all' else {'parent_nondumpable', 'no_new_privs', 'rlimits'})\n"
    "print(json.dumps({'score': r.score, 'isolation': r.detail.get('isolation'), 'failures': r.failures[:1]}))\n"
)


def _grade_from_parent_with_token(fs_mode):
    """A separate grading process whose *initial* environment holds a fake HF token (what
    /proc/<pid>/environ shows), grading a candidate that tries to read that file."""
    import subprocess
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HF_TOKEN": FAKE, "HUGGING_FACE_HUB_TOKEN": FAKE}
    out = subprocess.run([sys.executable, "-I", "-c", _PARENT, str(ROOT), fs_mode, _PROBE], env=env,
                         capture_output=True, text=True, timeout=120)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_parent_environ_is_not_readable_by_the_candidate():
    """All layers on: Landlock (and the user namespace, and as root the uid drop) stop the read."""
    res = _grade_from_parent_with_token("all")
    assert res["score"] == 1.0, res


def test_user_namespace_with_parent_nondumpability_blocks_parent_environ():
    if not unshare_prefix(dropped=os.geteuid() == 0):
        pytest.skip("no unprivileged user namespaces here")
    res = _grade_from_parent_with_token("userns")
    assert res["isolation"]["landlock"] == "off" and res["score"] == 1.0, res


def test_parent_nondumpability_protects_with_filesystem_and_namespaces_disabled():
    """Reduced requirements do not turn off permanent parent protection."""
    if os.geteuid() == 0:
        pytest.skip("as root the uid drop covers this")
    res = _grade_from_parent_with_token("none")
    assert res["score"] == 1.0, res


def test_privilege_drop_matches_the_grader_uid():
    r = score("import os\ndef uid():\n    return os.getuid()\n", ["assert uid() >= 0"])
    iso = r.detail["isolation"]
    if os.geteuid() == 0:
        assert 61000 <= iso["child_uid"] < 62000 and iso["uid_drop"].startswith("uid"), iso
    else:
        # inside `unshare -U` an unmapped uid reads as 65534; the kernel still sees the grader's uid
        assert iso["uid_drop"].startswith("skipped") and iso["child_uid"] in (os.getuid(), 65534), iso
    assert iso["no_new_privs"] == "on", iso
