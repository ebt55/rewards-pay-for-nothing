"""Launch and talk to the candidate child process.

The child is a fresh ``sys.executable -I -B -c <bootstrap>``:
- new session (own process group), killed as a group on timeout or close;
- temp working directory, minimal environment (no tokens, HOME = the temp dir);
- stdin carries only the request, then is replaced with /dev/null before candidate code runs;
- stdout/stderr go to /dev/null, so printed text is never seen by the grader;
- RLIMIT_CPU / AS / NOFILE / FSIZE / NPROC / CORE set by the child itself before candidate code
  (no preexec_fn, so the parent can be a big multithreaded trainer process);
- Landlock (Linux >= 5.13, unprivileged) when the kernel has it: read-only access to the Python
  installation, full access to the temp dir only, nothing else (no $HOME, no dataset caches, no
  /proc, no project folder);
- network namespace via ``unshare -Un`` when unprivileged user namespaces are allowed.
Results come back on a dedicated pipe as type-tagged JSON (codec.py).
"""
import json
import ctypes
import os
import pathlib
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from .codec import CodecError, sg_decode, sg_dumps, sg_encode, sg_loads

_HERE = pathlib.Path(__file__).resolve().parent
_CODEC_SRC = (_HERE / "codec.py").read_text()
_CHILD_SRC = (_HERE / "_child.py").read_text()
BOOTSTRAP = _CODEC_SRC + "\n\n" + _CHILD_SRC

_UNSHARE = {}
_UNSHARE_LOCK = threading.Lock()
PROBE_UID = 60999  # used only to probe unshare as an unprivileged uid when the grader is root

DEFAULT_REQUIRED_CONTROLS = frozenset({"parent_nondumpable", "no_new_privs", "rlimits", "landlock"})
_KNOWN_CONTROLS = DEFAULT_REQUIRED_CONTROLS | {"network_namespace", "pid_namespace", "uid_drop"}
_PARENT_LOCK = threading.Lock()
_PARENT_PID = None
_PARENT_ERROR = None


class IsolationConfigurationError(RuntimeError):
    """Required isolation could not be established; no candidate should be graded."""


def _parent_prctl(option, value=0):
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.prctl(option, value, 0, 0, 0)
    if result < 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))
    return result


def _protect_parent():
    """Set nondumpability once per process, then detect drift without restoring it."""
    global _PARENT_PID, _PARENT_ERROR
    if sys.platform != "linux":
        raise IsolationConfigurationError(
            f"securegrade runs candidates only on Linux (use WSL2 on Windows); this is {sys.platform}")
    with _PARENT_LOCK:
        pid = os.getpid()
        if _PARENT_PID != pid:
            _PARENT_PID, _PARENT_ERROR = pid, None
            try:
                if _parent_prctl(4, 0) != 0:  # PR_SET_DUMPABLE
                    raise RuntimeError("PR_SET_DUMPABLE returned nonzero")
            except Exception as exc:
                _PARENT_ERROR = f"parent nondumpability setup failed: {exc}"
        if _PARENT_ERROR:
            raise IsolationConfigurationError(_PARENT_ERROR)
        try:
            if _parent_prctl(3) != 0:  # PR_GET_DUMPABLE
                raise RuntimeError("parent dumpability changed after initialization")
        except Exception as exc:
            raise IsolationConfigurationError(f"parent nondumpability verification failed: {exc}") from exc


def _after_fork():
    # A lock held by another thread at fork cannot safely be inherited.
    global _PARENT_LOCK, _UNSHARE_LOCK, _uid_lock, _UNSHARE, _uids_in_use
    _PARENT_LOCK = threading.Lock()
    _UNSHARE_LOCK = threading.Lock()
    _uid_lock = threading.Lock()
    _UNSHARE, _uids_in_use = {}, set()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


def unshare_prefix(dropped=False):
    """unshare with new user + network + PID namespaces if that works here, else [].
    Network ns: no interfaces but a down loopback. PID ns: the candidate cannot see or signal the
    grader or any other process (getppid() is 0). Probed once per process and per privilege level
    (as the dropped uid when the grader is root, since that is who will run it), under a lock (the
    TRL wrapper grades from several threads; an earlier version let them race past the probe)."""
    _protect_parent()
    with _UNSHARE_LOCK:
        if dropped not in _UNSHARE:
            found = []
            exe = shutil.which("unshare")
            kw = {"user": PROBE_UID, "group": PROBE_UID, "extra_groups": []} if dropped else {}
            if exe:
                for cand in ([exe, "-Unp", "--fork", "--kill-child", "--"], [exe, "-Un", "--"]):
                    try:
                        if subprocess.run(cand + ["true"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL, timeout=10, cwd="/", **kw).returncode == 0:
                            found = cand
                            break
                    except Exception:  # noqa: BLE001
                        pass
            _UNSHARE[dropped] = found
        return list(_UNSHARE[dropped])


class ChildDead(Exception):
    pass


# Privilege drop when the grader runs as root (typical in containers). Each live child gets its own
# uid/gid from this range, so concurrent candidates cannot signal or ptrace each other or the
# root-owned trainer, and RLIMIT_NPROC (ignored for root) applies. The uids need no passwd entry.
DROP_UID_BASE = 61000
DROP_UID_COUNT = 1000
_uid_lock = threading.Lock()
_uids_in_use = set()


def _acquire_uid():
    with _uid_lock:
        for u in range(DROP_UID_BASE, DROP_UID_BASE + DROP_UID_COUNT):
            if u not in _uids_in_use:
                _uids_in_use.add(u)
                return u
    raise RuntimeError("no free sandbox uid")


def _release_uid(u):
    with _uid_lock:
        _uids_in_use.discard(u)


class Sandbox:
    def __init__(self, code, setup="", wall_timeout=10.0, mem_bytes=1024**3, network_isolation=True,
                 fs_isolation=True, python=None, drop_privileges=True, required_controls=None):
        try:
            self.required = frozenset(DEFAULT_REQUIRED_CONTROLS if required_controls is None else required_controls)
        except TypeError as exc:
            raise IsolationConfigurationError("required_controls must contain control names") from exc
        if self.required - _KNOWN_CONTROLS:
            raise IsolationConfigurationError("unknown required isolation control")
        if "landlock" in self.required and not fs_isolation:
            raise IsolationConfigurationError("required Landlock was explicitly disabled")
        if self.required & {"network_namespace", "pid_namespace"} and not network_isolation:
            raise IsolationConfigurationError("required namespaces were explicitly disabled")
        if "uid_drop" in self.required and (not drop_privileges or not hasattr(os, "geteuid") or os.geteuid() != 0):
            raise IsolationConfigurationError("required uid drop needs a root grader and drop_privileges=True")
        self.drop = drop_privileges and hasattr(os, "geteuid") and os.geteuid() == 0
        self.uid = None
        self.code, self.setup = code, setup or ""
        self.deadline = time.monotonic() + wall_timeout
        self.wall_timeout = wall_timeout
        self.mem_bytes = mem_bytes
        self.net = network_isolation
        self.fs = fs_isolation
        self.python = python or sys.executable
        self.proc = None
        self.dead_reason = None
        self.load = None
        self._buf = b""
        self._id = 0
        self.calls_ok = 0

    # ---------------------------------------------------------------- lifecycle
    def start(self):
        _protect_parent()  # before even an isolation-probe subprocess
        try:
            return self._start()
        except BaseException:
            self.close()
            raise

    def _start(self):
        prefix = unshare_prefix(dropped=self.drop) if self.net else []
        if "network_namespace" in self.required and not prefix:
            raise IsolationConfigurationError("required network namespace is unavailable")
        if "pid_namespace" in self.required and "-Unp" not in prefix:
            raise IsolationConfigurationError("required PID namespace is unavailable")
        try:
            self.tmp = tempfile.mkdtemp(prefix="securegrade_")
            os.chmod(self.tmp, 0o700)
        except Exception as exc:
            raise IsolationConfigurationError("sandbox directory setup failed") from exc
        # One BLAS/OpenMP thread: with RLIMIT_NPROC 0, OpenBLAS cannot start its workers and numpy's
        # import dies with KeyboardInterrupt (it raises SIGINT), failing every answer that imports numpy.
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "HOME": self.tmp,
               "TMPDIR": self.tmp, "PYTHONHASHSEED": "0",
               "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        cpu = int(self.wall_timeout) + 1
        spec = {
            "setup": self.setup, "code": self.code,
            "rlimits": {"RLIMIT_CPU": cpu, "RLIMIT_AS": self.mem_bytes, "RLIMIT_FSIZE": 10 * 1024**2,
                        "RLIMIT_NOFILE": 64, "RLIMIT_NPROC": 0, "RLIMIT_CORE": 0},
            "landlock": {"ro": [], "rw": [self.tmp]} if self.fs else None,
        }
        drop_kw = {}
        if self.drop:
            # Switched in the forked child before exec (no preexec_fn): setgroups([]), setgid, setuid.
            try:
                self.uid = _acquire_uid()
                os.chown(self.tmp, self.uid, self.uid)
            except Exception as exc:
                raise IsolationConfigurationError("requested uid drop setup failed") from exc
            drop_kw = {"user": self.uid, "group": self.uid, "extra_groups": []}
        try:
            self.req_r, self.req_w = os.pipe()
            self.res_r, self.res_w = os.pipe()
        except Exception as exc:
            raise IsolationConfigurationError("bootstrap pipe setup failed") from exc
        try:
            self.proc = subprocess.Popen(
                prefix + [self.python, "-I", "-B", "-c", BOOTSTRAP, str(self.req_r), str(self.res_w)],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                cwd=self.tmp, env=env, start_new_session=True, pass_fds=(self.req_r, self.res_w), close_fds=True,
                **drop_kw)
        except Exception as exc:
            raise IsolationConfigurationError("isolated interpreter could not start") from exc
        finally:
            self._close_fds("req_r", "res_w")
        self.isolation = {"network_namespace": bool(prefix), "pid_namespace": "-Unp" in prefix,
                          "uid_drop": f"uid {self.uid}" if self.drop else "skipped (grader is not root)",
                          "parent_nondumpable": True, "required_controls": sorted(self.required)}
        try:
            self.proc.stdin.write(json.dumps(spec).encode("utf-8", "surrogatepass"))
            self.proc.stdin.close()
        except (BrokenPipeError, OSError):
            raise IsolationConfigurationError("bootstrap request could not be delivered")
        try:
            ready = self._read_msg()
        except ChildDead as e:
            raise IsolationConfigurationError(f"bootstrap did not become ready: {e}") from e
        if not isinstance(ready, dict) or ready.get("phase") != "ready" or not isinstance(ready.get("controls"), dict):
            raise IsolationConfigurationError("invalid trusted bootstrap readiness report")
        controls = ready["controls"]
        applied = {"no_new_privs": controls.get("no_new_privs") == "on",
                   "landlock": str(controls.get("landlock", "")).startswith("on (ABI "),
                   "rlimits": controls.get("rlimits") == {name: "on" for name in spec["rlimits"]},
                   "uid_drop": isinstance(controls.get("uid"), int) and controls["uid"] != 0}
        for name in self.required & applied.keys():
            if not applied[name]:
                raise IsolationConfigurationError(f"required {name} failed: {controls.get(name)}")
        if self.drop and not applied["uid_drop"]:
            raise IsolationConfigurationError("requested uid drop was not applied")
        # This report precedes all candidate code. Later frames cannot attest configuration.
        self.isolation.update({"landlock": controls.get("landlock"), "no_new_privs": controls.get("no_new_privs"),
                               "child_uid": controls.get("uid"), "rlimits": controls.get("rlimits")})
        try:
            self._send({"op": "run"})
        except ChildDead as e:
            raise IsolationConfigurationError(f"bootstrap release failed: {e}") from e
        try:
            msg = self._read_msg()
        except ChildDead as e:
            msg = {"load": "error", "etype": "ChildDied", "msg": str(e)}
        self.load = msg if isinstance(msg, dict) else {"load": "error", "etype": "BadMessage", "msg": ""}
        return self.load

    def _close_fds(self, *names):
        for name in names:
            fd = getattr(self, name, None)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
                delattr(self, name)

    def close(self):
        if self.proc is not None:
            try:
                os.killpg(self.proc.pid, 9)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            try:
                self.proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        if self.uid is not None:  # the group is dead; the uid can be reused
            _release_uid(self.uid)
            self.uid = None
        self._close_fds("req_r", "req_w", "res_r", "res_w")
        if getattr(self, "tmp", None):
            shutil.rmtree(self.tmp, ignore_errors=True)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    # ---------------------------------------------------------------- protocol
    def _die(self, reason):
        if self.dead_reason is None:
            self.dead_reason = reason
            try:
                os.killpg(self.proc.pid, 9)
            except Exception:  # noqa: BLE001
                pass
        raise ChildDead(self.dead_reason)

    def _read_msg(self, max_bytes=8_000_000):
        if self.dead_reason:
            raise ChildDead(self.dead_reason)
        while b"\n" not in self._buf:
            left = self.deadline - time.monotonic()
            if left <= 0:
                self._die("wall-clock timeout")
            r, _, _ = select.select([self.res_r], [], [], left)
            if not r:
                self._die("wall-clock timeout")
            chunk = os.read(self.res_r, 1 << 16)
            if not chunk:
                self._die("child exited")
            self._buf += chunk
            if len(self._buf) > max_bytes:
                self._die("reply too large")
        line, self._buf = self._buf.split(b"\n", 1)
        try:
            return sg_loads(line.decode("utf-8", "surrogatepass"), max_bytes)
        except (CodecError, UnicodeDecodeError):
            self._die("malformed reply")

    def _send(self, obj):
        if self.dead_reason:
            raise ChildDead(self.dead_reason)
        data = (sg_dumps(obj) + "\n").encode("utf-8", "surrogatepass")
        while data:
            left = self.deadline - time.monotonic()
            if left <= 0:
                self._die("wall-clock timeout")
            _, w, _ = select.select([], [self.req_w], [], left)
            if not w:
                self._die("wall-clock timeout")
            try:
                n = os.write(self.req_w, data)
            except (BrokenPipeError, OSError):
                self._die("child exited")
            data = data[n:]

    def _request(self, obj):
        self._id += 1
        obj["id"] = self._id
        self._send(obj)
        msg = self._read_msg()
        if not isinstance(msg, dict) or msg.get("id") != self._id:
            self._die("out-of-order reply")
        return msg

    def lookup(self, name):
        """-> ('callable',) | ('value', v) | ('missing',) | ('unencodable', msg)"""
        msg = self._request({"op": "lookup", "name": name})
        kind = msg.get("kind")
        if kind == "value":
            return ("value", sg_decode(msg.get("v")))
        return (kind if kind in ("callable", "missing", "unencodable") else "missing", msg.get("msg", ""))

    def call(self, name, args, kwargs):
        """-> value, or raises CandidateRaised / CandidateValueError / ChildDead / CodecError."""
        payload = {"op": "call", "name": name, "args": sg_encode(list(args)), "kwargs": sg_encode(dict(kwargs))}
        msg = self._request(payload)
        if "ok" in msg:
            v = sg_decode(msg["ok"])
            self.calls_ok += 1
            return v
        if "opaque" in msg and isinstance(msg.get("truthy"), bool):
            self.calls_ok += 1
            return Opaque(str(msg["opaque"])[:60], msg["truthy"])
        if "unencodable" in msg:
            raise CandidateValueError("candidate returned a non-data value: " + str(msg["unencodable"]))
        raise CandidateRaised(str(msg.get("raised", "Exception")), str(msg.get("msg", "")))


class Opaque:
    """Stand-in for a non-data return value (e.g. re.Match). Supports truth testing only: it is
    equal to nothing but itself, so it can pass `assert f(x)` / `assert not f(x)` (which a plain
    True/False would pass too) but never an equality, ordering or arithmetic check."""
    __slots__ = ("type_name", "_truthy")

    def __init__(self, type_name, truthy):
        self.type_name, self._truthy = type_name, truthy

    def __bool__(self):
        return self._truthy

    __hash__ = object.__hash__

    def __repr__(self):
        return f"<opaque {self.type_name} truthy={self._truthy}>"


class CandidateValueError(Exception):
    pass


class CandidateRaised(Exception):
    def __init__(self, etype, msg):
        super().__init__(f"{etype}: {msg}")
        self.etype = etype
