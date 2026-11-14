"""Trusted side: run the test program with the candidate's names replaced by proxies.

The test program (MBPP assert list, or a HumanEval ``check(candidate)`` program) is trusted dataset
code and runs here, in the grader's process. It never sees candidate code. Every free name the tests
use that the dataset does not define (the entry point, any helper the tests call) is bound to a
proxy: calling it sends the *arguments* to the child, the child runs the candidate's function and
sends back a type-tagged plain value, and the comparison (``==``, ``set(...)``, ``math.isclose``,
``assert f(x)``, ``assert not f(x)``, ...) happens here on fresh built-in objects. Expected values
never enter the child. Each ``assert`` statement is rewritten so one failure does not stop the rest.
"""
import ast
import builtins
import dataclasses
import importlib
import sys
import time

from .codec import CodecError
from .extract import extract_code
from .sandbox import CandidateRaised, CandidateValueError, ChildDead, Sandbox

_BUILTINS = set(dir(builtins))
_BUILTIN_EXC = {n: getattr(builtins, n) for n in dir(builtins)
                if isinstance(getattr(builtins, n), type) and issubclass(getattr(builtins, n), Exception)}


@dataclasses.dataclass
class GradeResult:
    score: float            # fraction of (non-trivial) assert statements that passed
    passed: int
    total: int
    failures: list          # short reasons, one per failed assert (capped)
    format_ok: bool         # parseable code was found
    all_passed: bool = False
    detail: dict = dataclasses.field(default_factory=dict)


class CandidateError(Exception):
    """A proxied call did not produce a usable value."""


class _AssertRewriter(ast.NodeTransformer):
    def __init__(self):
        self.n = 0

    def visit_Assert(self, node):
        self.generic_visit(node)
        if isinstance(node.test, ast.Constant):   # `assert True, "..."` lines in HumanEval tests
            return ast.copy_location(ast.Pass(), node)
        idx = self.n
        self.n += 1
        call = ast.Call(func=ast.Name("__sg_assert", ast.Load()),
                        args=[ast.Constant(idx), ast.Lambda(
                            args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
                            body=node.test)],
                        keywords=[])
        return ast.copy_location(ast.Expr(call), node)


def _bound_and_loaded(tree):
    bound, loaded = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            (loaded if isinstance(n.ctx, ast.Load) else bound).add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(n.name)
        elif isinstance(n, ast.arg):
            bound.add(n.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound.add(n.name)
    return bound, loaded


def build_program(tests, entry_point=None):
    """-> (module AST with rewritten asserts, number of counted asserts, entry names to proxy)."""
    if isinstance(tests, str):
        src = tests
        if entry_point and "def check(" in tests:
            src = tests + f"\n\ncheck({entry_point})\n"
    else:
        src = "\n".join(str(t) for t in tests)
    tree = ast.parse(src)
    rw = _AssertRewriter()
    tree = ast.fix_missing_locations(rw.visit(tree))
    return tree, rw.n


class _Proxy:
    __slots__ = ("_sb", "_name", "_rec")

    def __init__(self, sb, name, rec):
        self._sb, self._name, self._rec = sb, name, rec

    def __call__(self, *args, **kwargs):
        try:
            return self._sb.call(self._name, args, kwargs)
        except CandidateRaised as e:
            exc = _BUILTIN_EXC.get(e.etype)
            if exc is not None and exc not in (SystemExit, KeyboardInterrupt, GeneratorExit):
                raise exc(f"(candidate) {e}")
            raise CandidateError(str(e)) from None
        except CandidateValueError as e:
            raise CandidateError(str(e)) from None
        except CodecError as e:  # an argument the dataset passes cannot cross the boundary
            self._rec["ungradable"].append(f"{self._name}: {e}")
            raise CandidateError(f"ungradable argument: {e}") from None
        except ChildDead as e:
            raise CandidateError(f"candidate process: {e}") from None

    def __repr__(self):
        return f"<candidate {self._name}>"


class _Missing:
    def __init__(self, name):
        self.name = name

    def __call__(self, *a, **k):
        raise NameError(f"name {self.name!r} is not defined by the candidate")

    def __repr__(self):
        return f"<missing {self.name}>"


def infer_entry(tests):
    """MBPP has no entry_point column: take the first called plain name in the first assert that is
    not a builtin; if every called name is a builtin (MBPP/126 calls its function `sum`), the first one.
    Only this name may shadow a builtin; the tests' other builtins stay the trusted ones, so a candidate
    cannot redefine `set` or `sorted` to make both sides of a comparison agree."""
    if not isinstance(tests, (list, tuple)) or not tests:
        return None
    try:
        tree = ast.parse(str(tests[0]))
    except SyntaxError:
        return None
    names = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    for n in names:
        if n not in _BUILTINS:
            return n
    return names[0] if names else None


def score(completion_text, tests, entry_point=None, setup_code="", prompt=None, wall_timeout=10.0,
          network_isolation=True, fs_isolation=True, mem_bytes=1024**3,
          python=None, drop_privileges=True, required_controls=None):
    """Grade one completion.

    tests: list of assert strings (MBPP ``test_list``) or a test program string (HumanEval ``test``,
    which defines ``check(candidate)``; entry_point is then required).
    setup_code: dataset imports run before both the candidate and the tests (MBPP ``test_imports``).
    prompt: trusted prompt text. For HumanEval it is run on the trusted side (so helpers it defines,
    like ``poly``, are the dataset's, not the candidate's) and used to complete body-only answers.
    """
    t0 = time.monotonic()
    failures, detail = [], {}
    if isinstance(setup_code, (list, tuple)):
        setup_code = "\n".join(setup_code)
    if not entry_point:
        entry_point = infer_entry(tests)
        detail["entry_point_inferred"] = entry_point
    try:
        tree, total = build_program(tests, entry_point)
    except SyntaxError as e:
        return GradeResult(0.0, 0, 0, [f"test program does not parse: {e}"], False, False, {"error": "bad tests"})
    code, how = extract_code(completion_text, entry_point, prompt)
    detail["extract"] = how
    if code is None:
        return GradeResult(0.0, 0, total, ["no parseable code"], False, False, detail)

    # Trusted namespace: dataset setup + (HumanEval) the prompt's own definitions.
    ns = {"__name__": "__sg_tests__", "__builtins__": builtins}
    trusted = [setup_code or ""]
    if prompt and isinstance(prompt, str):
        try:
            ast.parse(prompt)
            trusted.append(prompt)
        except SyntaxError:
            pass
    for src in trusted:
        if src.strip():
            try:
                exec(compile(src, "<trusted>", "exec"), ns)
            except Exception as e:  # noqa: BLE001
                detail.setdefault("trusted_setup_errors", []).append(f"{type(e).__name__}: {e}"[:200])
    bound, loaded = _bound_and_loaded(tree)
    free = {n for n in loaded if n not in bound and n not in _BUILTINS and n not in ns}
    if entry_point:
        free.add(entry_point)
    free.discard("__sg_assert")
    for name in sorted(free - {entry_point}):  # stdlib modules the tests use without importing them
        if name in getattr(sys, "stdlib_module_names", ()):
            try:
                ns[name] = importlib.import_module(name)
                free.discard(name)
            except Exception:  # noqa: BLE001
                pass

    status, reasons = {}, {}
    rec = {"ungradable": []}

    def __sg_assert(idx, thunk):
        try:
            ok = bool(thunk())
            why = "assertion false"
        except Exception as e:  # noqa: BLE001
            ok, why = False, f"{type(e).__name__}: {e}"[:200]
        if not ok:
            reasons.setdefault(idx, why)
        status[idx] = status.get(idx, True) and ok

    with Sandbox(code, setup_code, wall_timeout=wall_timeout, mem_bytes=mem_bytes,
                 network_isolation=network_isolation, fs_isolation=fs_isolation, python=python,
                 drop_privileges=drop_privileges, required_controls=required_controls) as sb:
        detail["isolation"] = getattr(sb, "isolation", {})
        if sb.load.get("load") != "ok":
            detail["load"] = f"{sb.load.get('etype')}: {sb.load.get('msg', '')}"[:300]
            failures.append("candidate failed to load: " + detail["load"])
            return GradeResult(0.0, 0, total, failures, True, False, detail)
        for name in sorted(free):
            try:
                kind = sb.lookup(name)
            except ChildDead as e:
                kind = ("missing", str(e))
            except CodecError:
                kind = ("missing", "bad value")
            if kind[0] == "callable":
                ns[name] = _Proxy(sb, name, rec)
            elif kind[0] == "value":
                ns[name] = kind[1]
            else:
                ns[name] = _Missing(name)
        ns["__sg_assert"] = __sg_assert
        try:
            exec(compile(tree, "<tests>", "exec"), ns)
        except Exception as e:  # noqa: BLE001 -- harness stopped outside an assert; the rest count as failed
            detail["harness_aborted"] = f"{type(e).__name__}: {e}"[:200]
        calls_ok = sb.calls_ok
        detail["candidate_calls_ok"] = calls_ok
        if sb.dead_reason:
            detail["child"] = sb.dead_reason
    passed = sum(1 for i in range(total) if status.get(i) is True)
    for i in range(total):
        if status.get(i) is not True:
            failures.append(f"assert #{i}: " + reasons.get(i, "not reached"))
    if calls_ok == 0:  # nothing the candidate computed was ever used: no credit
        passed = 0
    if rec["ungradable"]:
        detail["ungradable"] = rec["ungradable"][:5]
    sc = (passed / total) if total else 0.0
    detail["seconds"] = round(time.monotonic() - t0, 3)
    return GradeResult(sc, passed, total, failures[:20], True, bool(total) and passed == total, detail)


def self_check(python=None, required_controls=None):
    """Grade two tiny programs and report which isolation layers are active here. Call it once at
    trainer start-up and log the result (or refuse to train if a layer you need is missing)."""
    import os
    good = score("def f(x):\n    return x + 1\n", ["assert f(1) == 2"], python=python, required_controls=required_controls)
    bad = score("def f(x):\n    return x\n", ["assert f(1) == 2"], python=python, required_controls=required_controls)
    iso = dict(good.detail.get("isolation", {}))
    return {"ok": good.score == 1.0 and bad.score == 0.0, "grader_euid": os.geteuid(),
            "isolation": iso, "load_error": good.detail.get("load")}
