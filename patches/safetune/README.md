# SafeTune code rewards: what to fix (prose only)

SafeTune is under the Lexsi Labs Source Available License (LSAL v1.2), not MIT. This folder
therefore contains **no SafeTune source and no patched SafeTune code**: only this description
and our own tests (`tests/test_safetune_rewards.py`, MIT), which call the installed
safetune 0.1.10 and mark each known failure as `xfail(strict=True)`.

What was measured is in `results/gate1-2026-11-01.md` and `results/m1-2026-11-02.md`.

## What is already right

`CodeExecutionReward` (and `CodeCorrectnessReward`, which wraps it) run model code in a subprocess,
never in the trainer process, with a timeout. The source comment that marks this as a security
decision is accurate: `SystemExit`, `os._exit` and infinite loops cannot harm the caller.

## What still lets an answer that solves nothing get full marks

1. **"PASS" in stdout plus exit code 0 is treated as a pass.** The assertion path appends the
   test and `print("PASS")` to the candidate's code, and the dict path prints "PASS" when the
   values compare equal. A candidate that prints "PASS" and exits 0 before the asserts run passes
   every assert test; one that prints "PASS" anywhere passes every dict test. Fix: do not read
   stdout or the exit code. Have the child send back the *values* the candidate's function returns,
   as plain data, and evaluate the assert or the comparison in the parent ("values out"). If a
   stdout protocol must stay, at least use a per-call random token printed by the harness after the
   last test, and accept that a candidate able to read its own program can find it.

2. **`MBPPReward` passes a test when the process exits with status 0.** Nothing else is checked, so
   `sys.exit(0)` (or `os._exit(0)`) before the asserts passes all of them. Same fix as above.

3. **The comparison runs in the candidate's process.** The actual-versus-expected equality check and the test's own `assert`
   execute next to the candidate's code, so a returned object whose `__eq__` always returns True
   passes. With values out, only plain data reaches the comparison.

4. **With no tests, "it ran" earns 1.0.** That includes a compile-only stub and, because the exit
   code is the signal, a program that calls `os._exit(0)`. A correctness reward should return 0
   (and warn once) when no tests reach it, and "ran without error" should mean the child reported
   that the code finished, not that it exited 0.

## False negatives seen (correct answers that fail)

5. **Imports dropped from bare code.** Without a code fence, `_extract_code` keeps only the lines
   from the first `def`, so `import math` / `import heapq as hq` / `from typing import List` above
   it are lost and correct answers fail (2 of 5 bare references pass). Keep every top-level
   import and definition.

6. **`'python'` resolved through PATH.** The test runners start the child process with a bare `python` resolved through PATH.
   On a stock Ubuntu 24.04 without an activated venv there is no `python`, and every answer,
   correct ones included, scores 0 (`results/path_check.jsonl`). Use `sys.executable`.

7. **Dict tests pick "the first callable in globals()"** (on HumanEval this is `typing.List`) and
   compare floats with `==` (HumanEval/2 fails 2 of 3). Name the function under test explicitly
   and compare floats with a tolerance.

8. **`MBPPReward` with no `test_list`** returns 0 for every answer, silently. Warn once.

## Hardening worth adding to the subprocess

Run with `-I`, a temporary working directory, a minimal environment (no tokens), stdin closed,
resource limits (CPU, address space, file size, processes), a new session killed as a group on
timeout, and, where the kernel allows it, Landlock and unprivileged user/network/PID namespaces.
`securegrade/` in this project does all of this under MIT and can serve as a reference for the
design (not as code to paste into an LSAL file without the authors' agreement on licensing).
