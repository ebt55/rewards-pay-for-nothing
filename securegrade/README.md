# securegrade 0.1.2

A code-execution reward that grades **values**, not printed text or exit codes. MIT,
standard library only, Linux. Written for the P9 audit; imports nothing from
AlignTune or SafeTune.

```python
from securegrade import score, self_check
r = score(completion_text, ["assert add(1, 2) == 3"])
r = score(completion_text, he["test"], entry_point=he["entry_point"], prompt=he["prompt"])
# r.score, r.passed, r.total, r.all_passed, r.format_ok, r.failures, r.detail

from securegrade.trl_reward import secure_code_reward, make_secure_code_reward
# TRL columns: test_list (+ test_imports/test_setup_code), or test + entry_point.
# make_secure_code_reward(mode="all_pass") returns strict 1/0 grades.
```

## Execution and isolation

The caller runs trusted dataset tests. Each candidate runs in a fresh isolated Python
interpreter, receives arguments through proxies, and returns type-tagged JSON data.
Expected values and test programs stay in the caller. Decoding builds fresh built-in
values, so candidate-defined equality methods do not run in the judge. Non-data returns
cross as an opaque truth value, never an equal value. Numpy scalars convert to their
Python values; numpy arrays do not cross. Code extraction retains imports in bare
answers and supports fenced and HumanEval body-only answers.

A score is the fraction of non-trivial assertions passed; no successful candidate call
means zero credit. `all_passed` requires every counted assertion. Candidate exceptions,
load errors and timeouts remain wrong answers. Printed output and exit codes do not
give credit. The grading rules are unchanged by 0.1.2.

**Before any child, including a namespace probe, the grading parent sets
`PR_SET_DUMPABLE=0` and checks it.** Initialization is thread-safe, once per process PID,
and reinitialized after fork. Later calls verify the state and refuse to proceed if it
has drifted. This permanently changes the caller process's dumpability: core dumps and
ordinary same-uid debugger/memory attachment are restricted. securegrade never restores
or toggles it per completion. Reducing the required-control set cannot turn it off.
Privileged processes are outside this same-uid protection claim.

| Control | Implementation / reporting |
|---|---|
| Parent memory protection | Checked, permanent nondumpability before any child |
| Fresh interpreter and state | `python -I`, temp cwd, new session; process group killed on close/timeout |
| Wall time | Parent deadline, default 10 seconds |
| Resource limits | Checked CPU, AS (default 1 GiB), FSIZE (10 MB), NOFILE (64), NPROC (0), CORE (0) |
| Privileges | Checked `PR_SET_NO_NEW_PRIVS`; when root and `drop_privileges=True`, Popen drops groups/gid/uid to a separate live-child uid in 61000-61999 |
| Environment / stdin | Minimal environment, no inherited tokens/proxies; BLAS/OpenMP threads 1; stdin becomes `/dev/null` |
| Filesystem | Landlock: Python installation read/execute, temp cwd read/write, `/dev/null`; ABI reported |
| Network / PID | Optional user/network namespace and PID namespace when the probe succeeds; availability reported separately |

A trusted bootstrap installs controls and sends a readiness report **before dataset setup
or candidate code executes**. The parent validates requirements, preserves that report,
and then releases execution. Later candidate-controlled frames cannot become trusted
configuration failures or overwrite the verified isolation report. This is a setup gate,
not authentication of arbitrary candidate protocol messages.

## Required controls and configuration failures

`IsolationConfigurationError` means isolation could not be established; it propagates
from `score`, `self_check`, and the TRL wrapper, including threaded batches. It must not
be recorded as a numeric wrong-answer reward. Interpreter/bootstrap startup failure also
raises this error before candidate execution. A requested root uid drop cannot fail open.

```python
from securegrade import DEFAULT_REQUIRED_CONTROLS, IsolationConfigurationError
from securegrade.trl_reward import make_secure_code_reward

# Defaults: parent_nondumpable, no_new_privs, rlimits, landlock.
required = DEFAULT_REQUIRED_CONTROLS | {"network_namespace", "pid_namespace"}
reward = make_secure_code_reward(required_controls=required, max_workers=2)
self_check(required_controls=required)  # raises if a required control is unavailable
```

The same `required_controls` argument is accepted by `score` and `self_check`.
Supported names are `parent_nondumpable`, `no_new_privs`, `rlimits` (all six limits),
`landlock`, `network_namespace`, `pid_namespace`, and `uid_drop`. Unknown names, required
but explicitly disabled controls, and unavailable required namespaces are configuration
errors. `uid_drop` requires a root grader with `drop_privileges=True`. Disabling
`fs_isolation` requires explicitly removing `landlock` from the required set. An explicit
reduced set is a caller decision to accept fewer controls; parent protection remains on.

Network/PID isolation is attempted by default but is not a default requirement, since
some environments do not support unprivileged namespaces. Inspect
`GradeResult.detail["isolation"]` or require these controls explicitly. No unavailable
namespace is reported as enforced. `self_check()` returns good/bad-program checks and
the verified isolation report when setup succeeds.

## Verified scope and historical versions

The 8 Nov 2026 controls and compatibility checks use a non-root WSL2 Linux 5.15 runtime
without a Yama ptrace-scope interface. See `results/memread-2026-11-08.md` and its raw
artifacts for the exact source hashes, controls, eight synthetic canary cases, and supplied
reference results. The memory matrix uses fresh synthetic parents and a known address;
it never scans grading data. Landlock and nondumpability are varied only in those
synthetic parents. These observations do not establish universal correct-answer coverage.

Training used 0.1.0 for the original/core runs and 0.1.1 for the H hole-pair runs. The
recorded 0.1.1 RunPod root self-check is historical runtime evidence, distinct from this
0.1.2 check and from coverage of every numpy return variant. **0.1.2 Yama, Docker and
root deployments remain untested.** No training job was changed or rerun for this release.
A root deployment also needs its interpreter and libraries readable/executable by the
dropped uid; an interpreter under a mode-700 `/root` path will not work.

## Limits

- Landlock is required by default. Opting out permits filesystem access as the child uid,
  including dataset caches. Parent nondumpability does not isolate arbitrary files.
- ABI 1 (this WSL kernel) does not cover truncate, chmod, chown, utime or extended
  attributes. ABI 3 adds truncate coverage; chmod remains outside this policy.
- Without namespaces, network access and visibility/signalling of other processes remain
  possible according to uid permissions. Parent nondumpability does not prevent signals.
- No seccomp filter, cgroup, or aggregate disk quota is provided; FSIZE is per file.
- Candidate protocol traffic remains untrusted. The static pipe/availability and fixed
  hash-seed collision concerns were not reproduced as new findings or fixed in 0.1.2.
- Trusted test programs execute in the caller and can consume its global RNG state.
- In-place argument mutation does not update the judge's copy; none of the 591 supplied
  references needed it in the recorded checks.
- Visible-example hardcoding can pass visible tests. Keep tests hidden where appropriate.
- Constant answers may earn partial credit on falsy/None expectations. The historical
  compile-only stub earned partial credit on 22 tasks (mean 0.013 MBPP, 0.018 HumanEval),
  never full marks. Use `mode="all_pass"` to suppress partial credit.
