# CHANGELOG

## 0.1.3 — 14 November 2026

Fixes from the 14 Nov 2026 adversarial review (review notes not part of this repo), each with a
regression test in `securegrade/tests/test_review_2026_11_14.py` (selfcheck fixes CODE-09/10:
`harness/tests/test_selfcheck.py`). **Grading rules change** (first three items).

- **CODE-01** (critical): an exception, timeout or candidate exit that stopped the test program
  outside an assertion left earlier passes counted, so a loop test (e.g. HumanEval/32: right on
  iteration 1, then raise / `os._exit(0)` / hang) scored 1.0 with `all_passed`. Now such an abort
  gives no credit, and a dead candidate process never gives `all_passed` or full marks. MBPP
  assertion lists keep partial credit for assertions that completed before a timeout.
- **CODE-02**: `assert False` / `assert 0` (any falsy constant) was rewritten to `pass`. Only
  truthy constants are now ignored; a reached falsy-constant assertion stops the test program
  (no credit), also under `python -O`.
- **CODE-03**: the TRL wrapper dropped conversational prompts (`list[dict]`), so HumanEval
  oracle helpers (`poly`, `encode_cyclic`, `encode_shift`) were proxied to the candidate and a
  candidate redefining `poly` scored 1.0. Prompts are now unwrapped (`prompt_text`), a prompt that
  is prose or fenced is reduced to its code, and with a supplied prompt only the entry point is
  bound to the candidate. Residual (documented): with no prompt at all, helpers still come from
  the candidate, as the supplied fenced/bare reference checks rely on.
- **CODE-06**: a `check(candidate)` program without `entry_point` silently scored 0 (now
  ValueError); an unbatched `test_list` whose length equals the batch size was split into
  characters (now ValueError naming the expected shape); rows without tests returned None (now
  ValueError, or None with `allow_empty_rows=True`).
- **CODE-04** (part): Landlock no longer grants read access to `sys.path` entries outside the
  interpreter prefixes unless they are `site-packages`/`dist-packages` directories (layered venvs
  such as the 8 Nov `at-0129` interpreter keep numpy); a `.pth` line naming a project folder, as an
  old-style editable install writes, no longer exposes that folder.
  The missing system-library paths for standalone Python builds are documented in Limits.
- **CODE-08**: the variadic `libc.syscall` argument claim was not reproduced (Landlock reports
  "on (ABI 1)"), so the call is unchanged. Unconditional parent
  nondumpability is by design and documented; packaging metadata is not added.
- **RPL-08**: on non-Linux systems grading raises `IsolationConfigurationError` with a clear
  message, and the test suite skips sandbox tests (pure codec/extractor tests still run).
- **RPL-11**: the candidate child and the test-suite grading subprocess run with `-B`.
- CODE-05 (root uid pool per process; uid 65534 under an unmapped user namespace) and CODE-07
  (extraction and codec edge cases) are documented in README Limits, not changed.
- Checks: 1,346 of 1,346 supplied reference cells accepted, no score change from 0.1.2
  (`results/securegrade-013-references-2026-11-14.json`); the 411 securegrade replay cells (300
  controls, 47 class a, 64 class b) unchanged (`results/securegrade-013-recheck-2026-11-14.md`).
  0.1.3 was not used for any training run.

## 0.1.2 — 8 November 2026

- Set and verify `PR_SET_DUMPABLE=0` in the grading parent before any child, once per PID,
  with thread/fork-safe initialization; never restore or toggle it per completion.
- Validate explicit required controls before candidate execution. Defaults require parent
  nondumpability, no-new-privileges, all six resource limits, and Landlock. Optional required
  namespace/uid controls fail closed. Configuration errors propagate through the TRL wrapper.
- Preserve a trusted bootstrap readiness report separately from candidate-controlled traffic.
- Add fresh-parent synthetic memory controls and reference compatibility evidence in
  `results/memread-2026-11-08.md`. Honest-answer grading rules are unchanged; claims about
  unchanged observed scores are limited to the supplied reference checks recorded there.
- Training used **0.1.0** for the original/core runs and **0.1.1** for the H hole-pair runs.
  0.1.2 is new hardening and was not used for those training results.
- **0.1.2 Yama, Docker and root deployments are untested.** The historical 0.1.1 RunPod
  root self-check is separate runtime evidence, not a 0.1.2 deployment test.

## 0.1.1 — 3 November 2026

- Limit BLAS/OpenMP threads so numpy can import under NPROC=0; encode numpy scalars as
  Python scalars. Arrays remain opaque. This version was used for the H hole-pair runs.

## 0.1.0

- Initial separate-process value grader used for the original/core training runs.
