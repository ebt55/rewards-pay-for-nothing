"""Minimal MBPP grader for the Tiny Aya baseline (no AlignTune imports).

pass = the extracted code plus ALL of the task's test asserts run in a fresh
`python -I` subprocess (temp working dir, 10 s wall timeout, CPU/memory/file
limits) AND the process exits 0 AND its last stdout line is a random nonce
generated for this call and printed only after the last assert.

Not adversarially hardened: model code that reads its own source file could
find the nonce. That does not matter for a base-model baseline; the GRPO
reward audit is a separate track.
"""
from __future__ import annotations

import ast
import os
import re
import resource
import secrets
import subprocess
import sys
import tempfile

FENCE_RE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\n(.*?)```", re.DOTALL)


def extract_code(completion: str) -> str | None:
    """Return the code to run, or None if nothing parseable is found.

    Order: first fenced block tagged python/py that contains `def`; else the
    first fenced block of any tag that contains `def`; else the first fenced
    block; else the whole completion if it parses as Python and has a `def`.
    An unterminated final fence (completion cut at max tokens) is accepted as
    a block running to the end of the text.
    """
    blocks = [(m.group(1).lower(), m.group(2)) for m in FENCE_RE.finditer(completion)]
    if not blocks:
        # unterminated fence, e.g. "```python\n...<cut>"
        m = re.search(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\n(.*)$", completion, re.DOTALL)
        if m:
            blocks = [(m.group(1).lower(), m.group(2))]
    for want in (lambda t, c: t in ("python", "py", "python3") and "def " in c,
                 lambda t, c: "def " in c,
                 lambda t, c: True):
        for tag, code in blocks:
            if want(tag, code) and code.strip():
                return code
    text = completion.strip()
    if "def " in text:
        try:
            ast.parse(text)
            return text
        except SyntaxError:
            pass
    # Unfenced code inside prose: from the first top-level `def`/`import`/`from`
    # line, keep the longest run of lines that parses and contains a `def`.
    lines = completion.splitlines()
    starts = [i for i, l in enumerate(lines) if re.match(r"^(def |import |from \S+ import )", l)]
    if starts:
        body = lines[starts[0]:]
        for end in range(min(len(body), 200), 0, -1):
            chunk = "\n".join(body[:end])
            if "def " not in chunk:
                break
            try:
                ast.parse(chunk)
                return chunk
            except SyntaxError:
                continue
    return None


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024**2, 10 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.setsid()


def classify(rc: int | None, stderr: str, timed_out: bool) -> str:
    if timed_out:
        return "timeout"
    last = ""
    for line in reversed(stderr.strip().splitlines()):
        if line.strip():
            last = line.strip()
            break
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_.]*(Error|Exception|Exit|Interrupt))\b", last)
    if m:
        return m.group(1).split(".")[-1]
    if rc == 0:
        return "no_nonce"
    return f"rc_{rc}"


def grade(completion: str, test_list: list[str], test_imports: list[str] | None = None,
          timeout: float = 10.0, python: str = sys.executable) -> dict:
    code = extract_code(completion)
    if code is None:
        return {"passed": False, "kind": "format_failure", "detail": ""}
    nonce = secrets.token_hex(16)
    program = "\n".join(test_imports or []) + "\n\n" + code + "\n\n" + "\n".join(test_list) + \
        f"\n\nprint({nonce!r})\n"
    with tempfile.TemporaryDirectory(prefix="mbpp_grade_") as d:
        path = os.path.join(d, "prog.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(program)
        env = {"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0", "HOME": d}
        try:
            p = subprocess.run([python, "-I", path], cwd=d, env=env, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=timeout,
                               preexec_fn=_limits)
            rc, out, err, to = p.returncode, p.stdout, p.stderr, False
        except subprocess.TimeoutExpired as e:
            rc, out, err, to = None, (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), "", True
    lines = [l for l in out.strip().splitlines() if l.strip()]
    passed = (not to) and rc == 0 and bool(lines) and lines[-1].strip() == nonce
    kind = "pass" if passed else classify(rc, err, to)
    detail = ""
    if not passed:
        tail = [l for l in err.strip().splitlines() if l.strip()]
        detail = tail[-1][:200] if tail else ""
    return {"passed": passed, "kind": kind, "detail": detail}


if __name__ == "__main__":
    # self-test
    ok = "```python\ndef add(a, b):\n    return a + b\n```"
    bad = "```python\ndef add(a, b):\n    return a - b\n```"
    exit_early = "```python\nimport os\ndef add(a,b):\n    return 0\nos._exit(0)\n```"
    printer = "```python\ndef add(a,b):\n    return 0\nprint('PASS')\nraise SystemExit(0)\n```"
    tests = ["assert add(1, 2) == 3", "assert add(0, 0) == 0"]
    for name, c in [("ok", ok), ("bad", bad), ("exit_early", exit_early), ("printer", printer),
                    ("noformat", "I cannot help"), ("loop", "```python\ndef add(a,b):\n    while True: pass\n```"),
                    ("name", "```python\ndef plus(a,b):\n    return a+b\n```")]:
        print(name, grade(c, tests, timeout=3))
