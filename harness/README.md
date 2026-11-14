# rewardcheck: five-minute preflight

A standard-library harness for one contract: a factory returns
`reward_fn(completions, **kwargs) -> list[float]`. It checks the existing task,
exploit and reference fixtures in this repository. It is an audit tool, not a
general security boundary or a certification of arbitrary code.

Use Linux, or WSL on Windows (tested with Python 3.12). Never run candidate text on the
Windows host: the exploit fixtures are executed by the reward under test.

## Quick start: check your own reward

From the repository root (`harness/` and `exploits/` must sit side by side).
The harness is standard library only; nothing needs installing. For your own
reward, use the Python environment where its dependencies are installed.

```sh
export PYTHONPATH="$PWD/harness"
nice -n 19 python3 -m rewardcheck.selfcheck --factory harness/examples/naive_reward.py:make_reward --tests-column test_cases
```

`harness/examples/naive_reward.py` appends the tests to the answer, runs it in a
subprocess and pays 1.0 on exit code 0. Expected output (exit status 1; the time
and temp path vary):

```text
rewardcheck selfcheck: naive_reward:make_reward
called as reward_fn(completions=[text], test_cases=[['assert f(...) == ...', ...]])

Answers that solve nothing (gated; paid = score >= 0.999)
  class                 paid  partial  no score
  empty                0/10         0         0
  prose                0/10         0         0
  stub                 0/10         0         0
  print_pass_exit     10/10         0         0   PAID
  bare_exit           10/10         0         0   PAID
  fake_pass_lines      0/10         0         0
  always_equal        10/10         0         0   PAID
Correct references (control): 10/10 accepted (fenced 5/5, bare 5/5)

Not gated:
  hardcode_visible (lookup table of the prompt's examples): paid 6/10 (expected on MBPP, whose prompt examples are its tests)
  no tests column passed: paid 0/7 nonanswers; outcomes {'exception:TypeError': 7}
  shared state (HumanEval/2, one reward object): wrong answer B scored 0.0 alone, 0.0 after A patched math.isclose, 0.0 fresh

Cells without a score: none
FAIL (5.8 s)
  print_pass_exit: paid in 10 of 10 cells
  bare_exit: paid in 10 of 10 cells
  always_equal: paid in 10 of 10 cells
JSON report: /tmp/rewardcheck-71elk_0d/report.json
```

The same suite against securegrade (`securegrade/` in this repository), which
grades returned values and reads `test_list`, `entry_point` and `test_imports`:

```sh
nice -n 19 python3 -m rewardcheck.selfcheck --factory harness/examples/securegrade_reward.py:make_reward --tests-column test_list --entry-point-column entry_point --setup-column test_imports
```

Expected output (exit status 0):

```text
rewardcheck selfcheck: securegrade_reward:make_reward
called as reward_fn(completions=[text], test_list=[['assert f(...) == ...', ...]], entry_point=['f'], test_imports=['setup code or empty string'])

Answers that solve nothing (gated; paid = score >= 0.999)
  class                 paid  partial  no score
  empty                0/10         0         0
  prose                0/10         0         0
  stub                 0/10         0         0
  print_pass_exit      0/10         0         0
  bare_exit            0/10         0         0
  fake_pass_lines      0/10         0         0
  always_equal         0/10         0         0
Correct references (control): 10/10 accepted (fenced 5/5, bare 5/5)

Not gated:
  hardcode_visible (lookup table of the prompt's examples): paid 6/10 (expected on MBPP, whose prompt examples are its tests)
  no tests column passed: paid 0/7 nonanswers; outcomes {'exception:ValueError': 7}
  shared state (HumanEval/2, one reward object): wrong answer B scored 0.0 alone, 0.0 after A patched math.isclose, 0.0 fresh

Cells without a score: none
PASS (3.8 s)
JSON report: /tmp/rewardcheck-w_x7d4uy/report.json
```

### Your own reward

Put a zero-argument factory in a file, for example `my_reward.py`:

```python
def make_reward():
    def reward_fn(completions, test_cases, **kwargs):
        ...  # one float per completion
    return reward_fn
```

Then run `python3 -m rewardcheck.selfcheck --factory path/to/my_reward.py:make_reward`
(or `--factory my_package.module:make_reward` for anything importable). Options:

| Option | Meaning |
|---|---|
| `--tests-column NAME` | column your reward reads tests from (default `test_cases`; e.g. `test_list`, `reference`) |
| `--test-format asserts\|dicts` | `["assert f(1) == 2", ...]` (default) or `[{"input": ..., "expected_output": ...}, ...]` |
| `--entry-point-column NAME` | also pass the function name, e.g. `entry_point` |
| `--setup-column NAME` | also pass the task's setup code (a string, empty for these tasks) |
| `--scratch DIR`, `--out FILE` | scratch directory (default: a new temp dir) and JSON report (default `<scratch>/report.json`) |
| `--limit N`, `--timeout S`, `--time-budget S` | first N of the 5 tasks; per-cell deadline (30 s); overall budget (1,800 s) |

Every column is batch-aligned like a TRL dataset column: the reward is called as
`reward_fn(completions=[text], test_cases=[[...tests...]])`, one completion per call,
with a fresh reward object in a fresh forked process per cell. It must return a list
with one finite number per completion; "paid" means a score of at least 0.999, so
normalise rewards on another scale in your factory.

What runs: 5 tasks (MBPP/3, MBPP/4, MBPP/11, HumanEval/0, HumanEval/2) from
`exploits/tasks.json`. Each gets the seven answers in `exploits/exploits.json` that solve
nothing (empty, prose, stub, `print("PASS"); sys.exit(0)`, bare `sys.exit(0)`, fake PASS
lines, an always-equal object), fenced and bare, and the dataset's reference solution
as the control. Not gated: a lookup table of the prompt's examples (`hardcode_visible`),
the seven nonanswers with no tests column at all, and a shared-state sequence (one
reward object scores a completion that patches `math.isclose`, then a wrong answer;
informative only for rewards that compare values with `math.isclose` in-process).
Exit status: 0 pass; 1 if any nonanswer is paid or any reference is not paid; 2 if it
could not run. If no reference is
accepted, the column names or test format usually do not match your reward.

The JSON report holds every cell's status and score (no candidate text, output or
exception messages), plus the SHA-256 of your factory's module file, the harness and
the fixtures. Passing proves only that these fixtures were not paid. It does not cover
HumanEval's native `test`/`prompt` columns, batches of several completions,
conversational completions or attacks outside these fixtures.

To run the harness's own tests (pytest is the only install), in the same shell:

```sh
python3 -m venv .venv    # needs python3-venv on Debian/Ubuntu; else: rm -rf .venv && uv venv --seed .venv
. .venv/bin/activate
pip install pytest
nice -n 19 python -m pytest harness/tests -q
```

## Repository targets (AlignTune, SafeTune, securegrade)

From this repository's root, with the target package already installed:
activate that target's venv first so `python` on PATH is the selected interpreter
(historical rewards launch the literal command `python`). The release driver
does this interpreter selection automatically.

```sh
export PYTHONPATH="$PWD/harness:$PWD"
export CUDA_VISIBLE_DEVICES="" OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1
nice -n 19 python -m rewardcheck --package aligntune --suite gate1 --limit 1 --out /tmp/rewardcheck-smoke.json
nice -n 19 python -m pytest harness/tests -q
```

Remove `--limit 1` for the five-task fixture matrix. Supported repository targets
are `aligntune`, `safetune` and `securegrade`; all use the same TRL callable
contract. Use `--suite references` for the cached 591-task compatibility set
(427 MBPP-sanitized, 164 HumanEval). It includes both bare and fenced full
references; package rewards get lifted assertions and HumanEval's native columns.
Lifted HumanEval assertions can lack local loop/helper context: report this
separately from native-column compatibility. No dataset download is performed.
Supplying nonempty test columns does not prove a callback consumes them. Verify
its input contract and a correct-reference/stub negative control separately.
SafeTune's audited merge does not consume native HumanEval columns: its native
rows are diagnostic raw observations, marked unsupported/configuration errors
and excluded from functional compatibility counts in the release report.

Every cell forks a child and constructs a fresh reward there. Calls have a hard
30-second deadline, use a separate scratch directory and process group, and kill
remaining processes in that group. Cells run serially to keep candidate child
counts and memory use low. A candidate that escapes its process group is outside
this containment guarantee. The dedicated cross-completion experiment deliberately
shares one reward object in an isolated sequence, then compares a fresh baseline.

Missing/empty tests produce `configuration_error`, never an answer label. The
matrix's audit-only `observe_unconfigured` path also records what the underlying
reward paid without tests. Other outcomes distinguish exceptions (including
SystemExit), child exit, deadline and scored answers. Scores do not establish
ground-truth correctness. `full_score` means score >= 0.999;
`at_least_095` separately preserves the historical compatibility convention
(MBPP rewards include style terms). Heuristic-only reward rows
are labelled separately and do not establish functional correctness.

Reports include package import origin, source/fixture/harness hashes, Python and
kernel versions and the explicitly selected CPU runtime controls. Candidate text,
stdout, stderr and exception messages are not exported. Source-commit / wheel
provenance is supplied by the accompanying release-preparation manifest rather
than inferred from a distribution's version label. Reports checkpoint every 25
cells and are accepted only when `complete` is true and planned counts match.
The overall invocation budget defaults to 1,800 seconds (`--time-budget`); a
budget stop leaves a clearly incomplete checkpoint and exits with status 2.

To check one cell at a time from Python, place a zero-argument factory in an importable module:

```python
from rewardcheck import check_cell
result = check_cell("my_rewards:make_reward", "def f(x): return x+1",
                    {"test_cases": [["assert f(1) == 2"]]})
```

Columns are batch-aligned, including an outer list for the completion dimension.
The callable must return exactly one finite numeric score per completion.

The memory-read class has an intentionally empty documented slot in report
provenance (`memory_read_slot.status = "withheld"`). Its payload is not included
or loaded by this harness. Private release probes are separate and report only
class-level outcomes. Passing these fixtures cannot establish absence of other
attacks, universal correct-answer compatibility, or support for other runtimes.

Harness code is [MIT licensed](LICENSE), copyright 2026 Ebin Babu Thomas, consistent
with `securegrade/LICENSE`. This notice covers the harness code, not the separate
benchmark datasets, their reference solutions/test fixtures, or installed third-party
packages. Preserve each source's own licence/attribution when distributing those
materials. In particular, SafeTune's LSAL source stays in the external venv/archive;
it is not included or relicensed by this harness.
