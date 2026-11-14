"""Process containment for a single reward_fn(completions, **columns) adapter."""
import contextlib
import importlib
import io
import logging
import math
import multiprocessing as mp
import os
from pathlib import Path
import signal
import sys
import tempfile
import time

class ConfigurationError(ValueError):
    pass

def require_linux():
    if sys.platform != "linux":
        raise ConfigurationError("candidate execution requires Linux; use WSL on Windows")

def has_tests(columns):
    # The contract uses batch-aligned columns, including the outer batch dimension.
    for key in ("test_cases", "test_list", "test", "reference"):
        value = columns.get(key)
        if isinstance(value, (list, tuple)) and value and all(bool(x) for x in value):
            return True
    return False

def _resolve(factory):
    module, name = factory.split(":", 1)
    return getattr(importlib.import_module(module), name)

def _child(conn, factory, factory_kwargs, batches, scratch):
    os.setsid()
    logging.disable(logging.CRITICAL)
    with tempfile.TemporaryDirectory(prefix="cell-", dir=scratch) as tmp:
        tempfile.tempdir = tmp
        os.environ["TMPDIR"] = tmp
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                reward_fn = _resolve(factory)(**factory_kwargs)
                values = []
                for completions, columns in batches:
                    scores = reward_fn(completions=completions, **columns)
                    if not isinstance(scores, list) or len(scores) != len(completions):
                        raise ConfigurationError("reward must return one score per completion")
                    if any(isinstance(s, bool) or not isinstance(s, (int, float)) or not math.isfinite(s) for s in scores):
                        raise ConfigurationError("reward scores must be finite real numbers")
                    values.append([float(s) for s in scores])
            result = {"status":"ok", "scores":values}
        except BaseException as e:
            # Do not export candidate-controlled exception messages/output.
            result = {"status":"configuration_error" if isinstance(e, ConfigurationError) else "exception", "exception_type":type(e).__name__}
    try:
        conn.send(result)
    finally:
        os._exit(0)

def _run(factory, factory_kwargs, batches, timeout, scratch):
    require_linux()
    if not 0 < timeout <= 120:
        raise ConfigurationError("timeout must be in (0, 120] seconds")
    Path(scratch).mkdir(parents=True, exist_ok=True)
    ctx = mp.get_context("fork")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(child,factory,factory_kwargs,batches,str(scratch)))
    start = time.monotonic(); proc.start(); child.close()
    result = None
    try:
        if parent.poll(timeout):
            try: result = parent.recv()
            except EOFError: pass
        elapsed = time.monotonic()-start
        proc.join(.1)
        if result is None:
            result = {"status":"deadline" if proc.is_alive() else "child_exit"}
        # Kill the per-cell process group, including package-created descendants.
        try: os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        if proc.is_alive(): proc.kill()
        proc.join(2)
        result.update(seconds=round(elapsed,4),exitcode=proc.exitcode)
        return result
    finally:
        parent.close()
        if proc.is_alive(): proc.kill(); proc.join(2)

def check_cell(factory, completion, columns, *, factory_kwargs=None, timeout=30, scratch="/tmp/rewardcheck", require_tests=True, observe_unconfigured=False):
    """Fresh reward object in a fresh child. No tests is never a wrong answer.

    observe_unconfigured is audit-only: record the underlying reward's behavior,
    while preserving configuration_error as this harness's classification.
    """
    missing = require_tests and not has_tests(columns)
    if missing and not observe_unconfigured:
        return {"status":"configuration_error", "reason":"no tests supplied"}
    result = _run(factory, factory_kwargs or {}, [([completion],columns)], timeout,scratch)
    if missing:
        return {"status":"configuration_error","reason":"no tests supplied","native_observation":result}
    if result["status"] == "ok":
        result["score"] = result.pop("scores")[0][0]
        result["status"] = "scored"
        result["full_score"] = result["score"] >= 0.999
        result["at_least_095"] = result["score"] >= 0.95
    return result

def check_sequence(factory, batches, *, factory_kwargs=None, timeout=30, scratch="/tmp/rewardcheck"):
    """One isolated sequence deliberately shares its reward object across calls."""
    if any(not has_tests(columns) for _,columns in batches):
        return {"status":"configuration_error","reason":"no tests supplied"}
    return _run(factory,factory_kwargs or {},batches,timeout,scratch)
