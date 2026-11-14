# Child bootstrap. NOT imported by the parent: sandbox.py sends codec.py + this file as the
# `python -I -c` program. Runs untrusted candidate code, answers call/lookup requests with
# type-tagged values over a pipe. Only the readiness report, sent before any candidate/setup
# code and followed by an explicit parent release, is trusted as isolation evidence.
import builtins as _sg_builtins
import os as _sg_os
import sys as _sg_sys


def _sg_write(fd, obj):
    data = (sg_dumps(obj) + "\n").encode("utf-8", "surrogatepass")
    while data:
        n = _sg_os.write(fd, data)
        data = data[n:]


def _sg_landlock(ro_paths, rw_paths):
    """Restrict filesystem access with Landlock (ABI 1). Returns a status string."""
    rfd = -1
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        libc.syscall.restype = ctypes.c_long
        abi = libc.syscall(444, None, 0, 1)  # landlock_create_ruleset(NULL, 0, VERSION)
        if abi < 1:
            return "unavailable"

        class _RA(ctypes.Structure):
            _fields_ = [("handled_access_fs", ctypes.c_uint64)]

        class _PB(ctypes.Structure):
            _pack_ = 1
            _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

        ALL = (1 << 13) - 1            # every ABI-1 filesystem right
        FILE_ONLY = 1 | 2 | 4          # rights valid on a non-directory
        if abi >= 2:
            ALL |= 1 << 13             # REFER (cross-directory rename/link)
        if abi >= 3:
            ALL |= 1 << 14             # TRUNCATE
            FILE_ONLY |= 1 << 14
        RO = 1 | 4 | 8                 # EXECUTE | READ_FILE | READ_DIR
        attr = _RA(ALL)
        rfd = libc.syscall(444, ctypes.byref(attr), ctypes.sizeof(attr), 0)
        if rfd < 0:
            return "create_ruleset failed"
        rules = [(p, RO) for p in ro_paths] + [(p, ALL) for p in rw_paths] + [("/dev/null", 2 | 4)]
        for path, acc in rules:
            try:
                fd = _sg_os.open(path, _sg_os.O_PATH | _sg_os.O_CLOEXEC)
            except OSError:
                continue
            try:
                import stat
                if not stat.S_ISDIR(_sg_os.fstat(fd).st_mode):
                    acc &= FILE_ONLY
                pb = _PB(acc, fd)
                if libc.syscall(445, rfd, 1, ctypes.byref(pb), 0) != 0:
                    return "add_rule failed (errno %d)" % ctypes.get_errno()
            finally:
                _sg_os.close(fd)
        if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
            return "no_new_privs failed"
        if libc.syscall(446, rfd, 0) != 0:  # landlock_restrict_self
            return "restrict_self failed"
        return "on (ABI %d)" % abi
    except Exception as e:  # noqa: BLE001
        return "error: " + type(e).__name__
    finally:
        if rfd >= 0:
            _sg_os.close(rfd)


def _sg_main():
    import json
    import resource
    req_fd, res_fd = int(_sg_sys.argv[1]), int(_sg_sys.argv[2])
    raw = b""
    while True:
        chunk = _sg_os.read(0, 1 << 16)
        if not chunk:
            break
        raw += chunk
    spec = json.loads(raw.decode("utf-8"))
    null = _sg_os.open("/dev/null", _sg_os.O_RDWR)
    _sg_os.dup2(null, 0)  # stdin is gone before candidate code runs
    status = {"landlock": "off", "uid": _sg_os.getuid(), "rlimits": {}}
    try:  # no setuid/file-capability escalation from here on
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        status["no_new_privs"] = "on" if (libc.prctl(38, 1, 0, 0, 0) == 0
                                                 and libc.prctl(39, 0, 0, 0, 0) == 1) else "failed"
    except Exception as e:  # noqa: BLE001
        status["no_new_privs"] = "error: " + type(e).__name__
    for name, val in spec.get("rlimits", {}).items():
        try:
            lim = getattr(resource, name)
            resource.setrlimit(lim, (val, val))
            status["rlimits"][name] = "on" if resource.getrlimit(lim) == (val, val) else "verification failed"
        except Exception as e:  # noqa: BLE001
            status["rlimits"][name] = "failed: " + type(e).__name__
    if spec.get("landlock"):
        # Read access: the interpreter's prefixes, sys.path entries inside them, and sys.path package
        # directories (site-packages / dist-packages) outside them, e.g. a layered venv's .pth line.
        # Any other sys.path entry outside the prefixes (a .pth line naming a project folder, as an
        # old-style editable install writes) is not granted.
        prefixes = [p for p in {_sg_sys.prefix, _sg_sys.base_prefix, _sg_sys.exec_prefix,
                                _sg_sys.base_exec_prefix} if p]
        roots = [_sg_os.path.realpath(p).rstrip("/") + "/" for p in prefixes]
        keep = [p for p in _sg_sys.path if p and (
            any((_sg_os.path.realpath(p) + "/").startswith(r) for r in roots)
            or _sg_os.path.basename(_sg_os.path.realpath(p)) in ("site-packages", "dist-packages"))]
        ro = [p for p in set(spec["landlock"]["ro"] + prefixes + keep) if p]
        status["landlock"] = _sg_landlock(ro, spec["landlock"]["rw"])
    _sg_write(res_fd, {"phase": "ready", "controls": status})
    # Do not evaluate setup or candidate code until the parent validates isolation.
    gate = b""
    while b"\n" not in gate:
        part = _sg_os.read(req_fd, 4096)
        if not part:
            return
        gate += part
    if json.loads(gate.decode("utf-8")) != {"op": "run"}:
        return
    ns = {"__name__": "__candidate__", "__builtins__": _sg_builtins}
    try:
        if spec.get("setup"):
            exec(compile(spec["setup"], "<setup>", "exec"), ns)
        exec(compile(spec["code"], "<candidate>", "exec"), ns)
        load = {"load": "ok"}
    except BaseException as e:  # noqa: BLE001 -- SystemExit at load is a failed load, not an exit
        load = {"load": "error", "etype": type(e).__name__, "msg": str(e)[:300]}
    _sg_write(res_fd, load)
    buf = b""
    while True:
        while b"\n" not in buf:
            chunk = _sg_os.read(req_fd, 1 << 16)
            if not chunk:
                return
            buf += chunk
        line, buf = buf.split(b"\n", 1)
        req = json.loads(line.decode("utf-8", "surrogatepass"))
        rid = req.get("id")
        try:
            if req["op"] == "lookup":
                if req["name"] not in ns:
                    out = {"id": rid, "kind": "missing"}
                else:
                    v = ns[req["name"]]
                    if callable(v):
                        out = {"id": rid, "kind": "callable"}
                    else:
                        try:
                            out = {"id": rid, "kind": "value", "v": sg_encode(v)}
                        except CodecError as e:
                            out = {"id": rid, "kind": "unencodable", "msg": str(e)[:200]}
            else:  # call
                fn = ns.get(req["name"])
                if fn is None:
                    raise NameError("name %r is not defined" % req["name"])
                args = sg_decode(req["args"])
                kwargs = sg_decode(req["kwargs"])
                val = fn(*args, **kwargs)
                try:
                    out = {"id": rid, "ok": sg_encode(val)}
                except CodecError as e:
                    # Not plain data (e.g. a re.Match). Only its truthiness crosses; the parent
                    # wraps it in an object that equals nothing but itself.
                    try:
                        out = {"id": rid, "opaque": type(val).__name__[:60], "truthy": bool(val)}
                    except BaseException:  # noqa: BLE001
                        out = {"id": rid, "unencodable": str(e)[:200]}
        except BaseException as e:  # noqa: BLE001 -- includes SystemExit raised by the candidate
            out = {"id": rid, "raised": type(e).__name__, "msg": str(e)[:300]}
        _sg_write(res_fd, out)


_sg_main()
