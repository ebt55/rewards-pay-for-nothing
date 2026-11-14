"""Configuration failures precede candidate execution; parent protection is permanent."""
import os
import pathlib
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from securegrade import IsolationConfigurationError, score  # noqa: E402
from securegrade import sandbox as sb  # noqa: E402
from securegrade.trl_reward import make_secure_code_reward  # noqa: E402


def test_parent_setup_once_with_concurrent_calls_and_drift_detection(monkeypatch):
    calls = []

    def prctl(option, value=0):
        calls.append((option, value))
        return 0

    monkeypatch.setattr(sb, "_PARENT_PID", None)
    monkeypatch.setattr(sb, "_parent_prctl", prctl)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: sb._protect_parent(), range(12)))
    assert calls.count((4, 0)) == 1
    monkeypatch.setattr(sb, "_parent_prctl", lambda option, value=0: 1)
    with pytest.raises(IsolationConfigurationError, match="changed"):
        sb._protect_parent()
    assert calls.count((4, 0)) == 1


def test_failed_parent_setup_is_not_retried_or_followed_by_child(monkeypatch):
    calls = []

    def denied(option, value=0):
        calls.append(option)
        raise PermissionError("synthetic denial")

    monkeypatch.setattr(sb, "_PARENT_PID", None)
    monkeypatch.setattr(sb, "_PARENT_ERROR", None)
    monkeypatch.setattr(sb, "_parent_prctl", denied)
    monkeypatch.setattr(sb.subprocess, "Popen", lambda *a, **k: pytest.fail("child launched"))
    for _ in range(2):
        with pytest.raises(IsolationConfigurationError, match="setup failed"):
            sb.Sandbox("pass").start()
    assert calls == [4]


def test_real_parent_protection_reinitializes_after_fork():
    # Keep fork/lock manipulation in a bounded, fresh synthetic process.
    program = """
import os, sys
sys.path.insert(0, sys.argv[1])
from securegrade import sandbox as s
s._protect_parent()
s._PARENT_LOCK.acquire()
pid = os.fork()
if pid == 0:
    s._protect_parent()
    os._exit(0 if s._PARENT_PID == os.getpid() and s._parent_prctl(3) == 0 else 1)
s._PARENT_LOCK.release()
_, status = os.waitpid(pid, 0)
assert status == 0
assert s._parent_prctl(3) == 0
"""
    process = subprocess.Popen([sys.executable, "-I", "-B", "-c", program, str(ROOT)], start_new_session=True)
    try:
        assert process.wait(timeout=15) == 0
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


@pytest.mark.parametrize("kw", [
    {"required_controls": {"unknown"}},
    {"fs_isolation": False},
    {"network_isolation": False, "required_controls": {"network_namespace"}},
    {"network_isolation": False, "required_controls": {"pid_namespace"}},
    {"drop_privileges": False, "required_controls": {"uid_drop"}},
])
def test_invalid_requirement_fails_without_launch(monkeypatch, kw):
    monkeypatch.setattr(sb.subprocess, "Popen", lambda *a, **k: pytest.fail("child launched"))
    with pytest.raises(IsolationConfigurationError):
        score("def f(): return 1", ["assert f() == 1"], **kw)


@pytest.mark.parametrize("name", ["network_namespace", "pid_namespace"])
def test_required_unavailable_namespace_fails_without_candidate(monkeypatch, name):
    monkeypatch.setattr(sb, "unshare_prefix", lambda **kw: [])
    monkeypatch.setattr(sb.subprocess, "Popen", lambda *a, **k: pytest.fail("child launched"))
    with pytest.raises(IsolationConfigurationError, match="unavailable"):
        score("def f(): return 1", ["assert f() == 1"], required_controls={name})


@pytest.mark.parametrize("control", ["landlock", "no_new_privs", "rlimits"])
def test_failed_bootstrap_control_prevents_candidate_and_setup(monkeypatch, tmp_path, control):
    marker = tmp_path / "executed"
    original = sb.tempfile.mkdtemp
    monkeypatch.setattr(sb.tempfile, "mkdtemp", lambda **kw: original(prefix="securegrade_", dir=tmp_path))
    # Write into the sandbox cwd so the marker would be allowed even with working Landlock.
    code = "open('executed', 'w').write('ran')\ndef f(): return 1"
    ready = '_sg_write(res_fd, {"phase": "ready", "controls": status})'
    modified = sb.BOOTSTRAP.replace(ready, f'status[{control!r}] = "synthetic failure"\n    ' + ready)
    assert modified != sb.BOOTSTRAP
    monkeypatch.setattr(sb, "BOOTSTRAP", modified)
    # Retain the temp directory for inspection; setup runs before candidate if the gate is broken.
    monkeypatch.setattr(sb.shutil, "rmtree", lambda *a, **k: None)
    with pytest.raises(IsolationConfigurationError, match=control):
        score(code, ["assert f() == 1"], setup_code="open('executed', 'w').write('setup')")
    assert not list(tmp_path.glob("*/executed"))
    assert not marker.exists()


def test_post_execution_configuration_frame_is_untrusted():
    code = """import __main__, os
__main__._sg_write(int(__main__._sg_sys.argv[2]), {'phase': 'ready', 'controls': {'landlock': 'failed'}})
os._exit(0)
"""
    result = score(code, ["assert f() == 1"])
    assert result.score == 0
    assert result.detail["isolation"]["landlock"].startswith("on (ABI ")


def test_configuration_failure_propagates_through_threaded_trl(monkeypatch):
    def failure(*args, **kwargs):
        raise IsolationConfigurationError("synthetic failure")

    monkeypatch.setattr("securegrade.trl_reward.score", failure)
    reward = make_secure_code_reward(max_workers=2)
    with pytest.raises(IsolationConfigurationError, match="synthetic failure"):
        reward(completions=["x", "x"], test_list=[["assert f() == 1"]] * 2)


def test_requested_root_drop_failure_is_configuration_error(monkeypatch):
    monkeypatch.setattr(sb.os, "geteuid", lambda: 0)
    monkeypatch.setattr(sb, "unshare_prefix", lambda **kw: [])
    monkeypatch.setattr(sb.os, "chown", lambda *a: None)

    def denied(*args, **kwargs):
        raise PermissionError("synthetic setuid failure")

    monkeypatch.setattr(sb.subprocess, "Popen", denied)
    with pytest.raises(IsolationConfigurationError, match="could not start"):
        score("def f(): return 1", ["assert f() == 1"])


def test_second_pipe_failure_closes_first_pipe_without_child(monkeypatch):
    original = os.pipe
    opened = []

    def create():
        if opened:
            raise OSError("synthetic second-pipe failure")
        pair = original()
        opened.extend(pair)
        return pair

    monkeypatch.setattr(sb, "unshare_prefix", lambda **kw: [])
    monkeypatch.setattr(sb.os, "pipe", create)
    monkeypatch.setattr(sb.subprocess, "Popen", lambda *a, **kw: pytest.fail("child launched"))
    with pytest.raises(IsolationConfigurationError, match="pipe setup failed"):
        score("def f(): return 1", ["assert f() == 1"])
    assert len(opened) == 2
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)
