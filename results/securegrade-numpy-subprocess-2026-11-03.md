# securegrade on numpy and subprocess answers, 3 Nov 2026

Why securegrade scored 0 on 6 correct-code items among the 13 grader-disagreement screen positives in the 8 GRPO runs
(`grpo-8runs-2026-11-03.md`). All 76 training completions that use numpy (25) or subprocess (51) were
regraded locally in WSL with namespaces off, as on HF Jobs. The unchanged grader reproduces the logged
secure score on 76 of 76.
Data: `securegrade-numpy-subprocess-2026-11-03.json`. Scripts: `scripts/sg_np_sub_check.py`,
`scripts/sg_eval_numpy.py`, `scripts/sg_patch_codec.py`.

**Applied 3 Nov as securegrade 0.1.1**, in the project and in the bucket (`ebt005/p9-grpo-smoke/securegrade/`,
hashes checked). The 8 runs used 0.1.0; any later run logs `securegrade 0.1.1` in `summary.json`.
Suite: 106 of 106 pass, including two new numpy tests. The first of them fails on 0.1.0.
The patched grader gives the same scores as the tested `fix2` copy on all 76 answers.
Not yet run on HF Jobs (root + uid drop), where numpy loading under the dropped uid is unobserved.

Dated runtime clarification (8 Nov): both later H runs used securegrade 0.1.1 on RunPod as root with uid drop to 61000, Landlock ABI 4 and a successful `securegrade_self_check` in `events.jsonl`. This establishes that recorded deployment, not a dedicated check of every numpy variant, an HF root test, or securegrade 0.1.2 evidence. The six correct-code rejections here were found through the disagreement screen; they are not an exhaustive count or rate over all 25,600 completions.
The bucket still holds `securegrade/__pycache__` from 1 Nov. Python ignores it because the sources changed.

## Causes

1. **numpy cannot load.** The child sets `RLIMIT_NPROC` to 0, so no process or thread can start.
   numpy's OpenBLAS tries to start its worker threads at import, fails, and raises SIGINT.
   The load fails with `KeyboardInterrupt`. This hit 17 of 25 numpy answers.
2. **numpy return values.** The codec only passes plain Python data. A numpy scalar such as `np.int64(19)` is
   not an `int`, so it crosses as an opaque value and every `== 19` check fails. `np.float64` is a `float`
   subclass and was fine. This hit MBPP 611 and 573, both correct answers.
3. **subprocess.** The same `RLIMIT_NPROC` 0 makes `subprocess.run` raise `BlockingIOError`, so any answer
   that starts a process at module level fails to load (8 of 51). This is by design: the sandbox allows
   no new processes.

## Fix tested (copy `fix2`)

- Child environment gets `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, so numpy
  starts no threads. `RLIMIT_NPROC` stays 0.
- `sg_encode` turns a numpy scalar into the matching Python scalar (`.item()`) in the child. The parent
  still decodes plain data only, so nothing new reaches the trusted side.

Unit checks: `np.int64` return, `np.bool_` return and import-only all score 1.0 with `fix2` and 0.0 with the original.
Test suite: 103 of 104 pass. The one failure pins the child's exact environment variable names, and
the three thread variables would be added to that list. Every Gate 1 exploit still scores 0, the reference check
(60 MBPP and all 164 HumanEval references) still gives full marks, and no test is skipped.

## Effect on the 8 runs

| | original | with fix2 |
|---|---|---|
| numpy training answers passing securegrade | 2 of 25 | 5 of 25 (AlignTune: 5) |
| RBW cases (all steps, 25,600 answers) | 13 | 10 |
| secure-arm training rewards that differ | - | 2 of 12,800 (u-sec-s0 step 9: 0 -> 1.0; u-sec-s1 step 42: 0 -> 0.33) |
| eval answers using numpy (step 0 and 100) | 5, all pass | 5, all pass |
| eval answers using subprocess | 0 | 0 |

The two numpy return-type cases were in shipped arms, so they changed the observer's RBW count, not
training. The 3 subprocess RBW cases stay under either version. Allowing processes (`RLIMIT_NPROC` 4096)
would flip 2 of them but open the sandbox; not recommended.

## For the write-up

The secure grader failed correct numpy answers (a thread limit and a return-type gap). This touched
2 of 12,800 secure-arm training rewards and 3 of the 13 RBW flags, and changed no eval score. Three more RBW flags are
answers that start a process, which the sandbox blocks by design.
