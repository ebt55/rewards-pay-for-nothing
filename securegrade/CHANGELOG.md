# CHANGELOG

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
