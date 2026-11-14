# Rewards that pay for nothing

**Code-execution rewards in two RL post-training libraries paid full marks to answers that solve nothing. Both libraries merged fixes one day after a private report, and the released graders now pay 0 of 111 exploit-shaped answers from our training logs that the old grader scored in full. Those answers came from runs whose prompt described the grading rule or stated the exit hole; the unhinted runs produced none.**

`MIT` · `Python 3.12` · `Linux / WSL2` · `tools: standard library only` · [full write-up](WRITEUP.md) · [experimental numbers, traced](CLAIMS.md)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/readme/replay-before-after-dark.png">
  <img alt="Early-exit answers from hinted training runs: the old grader paid 47 of 47 wrong-code and 64 of 64 correct-code answers; released graders paid 0 of each and 297 of 300 correct controls" src="figures/readme/replay-before-after-light.png" width="820">
</picture>

Two tools come out of the project:

- **`rewardcheck`**: point it at your reward function and it tells you, in a few seconds, whether the reward pays answers that solve nothing.
- **`securegrade`**: a grader that compares returned values and ignores printed output and exit codes.

## The bug in 20 seconds

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/readme/how-the-trick-works-dark.png">
  <img alt="Left: a grader that pays on exit code 0 runs the answer and the tests as one program; the answer calls exit(0), the tests never run, and the reward is 1.0. Right: a value-out grader keeps the tests, calls the answer in a fresh process, gets no value back, and the reward is 0.0." src="figures/readme/how-the-trick-works-light.png" width="820">
</picture>

- A code reward runs the model's answer against tests and pays when the tests pass.
- If the reward trusts anything the answer controls, the answer can collect full marks without solving the task.
- We found three routes: exit before the tests run, print the success line the grader looks for, or return an object that equals everything.

A policy trained on such a reward is paid for the trick while its training curve looks healthy.

<details>
<summary>The same non-answer under two graders (15-second animation)</summary>

<img alt="A program ends before the appended tests run, yet the historical grader awards 1.0. The same answer ends inside securegrade's fresh interpreter; the caller has nothing to compare and awards 0.0. A reference solution returns data, the caller compares it with the expected values, and it earns 1.0." src="figures/article-visuals/same-nonanswer-astra.gif" width="820">

Historical AlignTune 0.1.28 `code_verifiable`, fenced code, assert tests. This is not current-release behaviour. [Static version](figures/article-visuals/same-nonanswer-astra-poster.png).

</details>

## What we found

- **Six shipped reward implementations paid answers that solve nothing.** Four in AlignTune 0.1.28 and two in SafeTune 0.1.10 each paid 1.0 to at least one non-answer on all five demonstration tasks. [Audit report](results/gate1-2026-11-01.md)
- **Fixed upstream in a day, with credit.** Reported privately on 2 November 2026; AlignTune PR #40 and SafeTune PR #32 merged on 3 November. AlignTune's released security test says it is adapted from the report. [Re-audit of the released sources](results/release-reaudit-2026-11-08.md)
- **The fixes stop the hand-made exploits.** With tests supplied, positive scores fall from 23 of 77 display cells to 0 of 77. [Re-audit](results/release-reaudit-2026-11-08.md)
- **The released graders pay 0 of 111 exploit-shaped answers from training.** A 3.35B model wrote them during our GRPO runs, but only when prompted: 104 come from two runs whose prompt stated the exit hole, 7 from runs whose prompt described the grading rule, and none from the unhinted runs. 47 are wrong code and 64 correct code, each exiting before the tests. The old grader gives all 111 a full score; it was the training reward for 63 of them, and only logged for the other 48. Each of five released reward paths pays none. [Replay report](results/replay-release-2026-11-14.md)
- **297 of 300 ordinary correct answers are still accepted** by each of the four released pass/fail paths (120 of 120 from unhinted runs). The 3 rejected print PASS and end before the tests run; 2 are correct functions whose exit sits under a `__main__` guard, a shape that both training-time graders passed. [Replay report](results/replay-release-2026-11-14.md)
- **The training study is uninformative.** Eight pre-registered 100-step GRPO runs compared the shipped reward with a hardened one; two exploratory runs followed. Both pre-registered under-training checks failed, so it does not show that training amplifies the exploit, and it does not rule that out. [Training report](results/grpo-8runs-2026-11-03.md), [pre-registration](design/RUNS-2026-11-02.md)

<details>
<summary>Before and after, per reward and exploit class (heatmap)</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/fig1-audit-heatmap-dark.png">
  <img alt="Heatmap of what each code reward paid for answers that solve nothing, in the historical shipped versions and in the fixed sources. With tests supplied, 23 of 77 cells paid before and 0 of 77 after." src="figures/fig1-audit-heatmap-light.png" width="820">
</picture>

Highest score over 5 tasks and 2 formats per cell. The cells that still pay are rows with no tests supplied; see [Status and limits](#status-and-limits). Details in [`figures/README.md`](figures/README.md).

</details>

## Check your own reward in 5 minutes

<img alt="Terminal recording: rewardcheck runs against a naive reward and prints FAIL, with print_pass_exit, bare_exit and always_equal each paid in 10 of 10 cells. It then runs against securegrade and prints PASS, with every class at 0 of 10 and 10 of 10 references accepted." src="figures/readme/demo-rewardcheck.gif" width="560">

Real output, trimmed. [Static version](figures/readme/demo-rewardcheck-poster.png).

Use Linux, or WSL on Windows (tested with Python 3.12). **Never run this on a Windows host**: the reward under test executes the exploit fixtures. Nothing needs installing; the harness is standard library only.

**1. Run the example that should fail.** From the repository root:

```sh
export PYTHONPATH="$PWD/harness"
nice -n 19 python3 -m rewardcheck.selfcheck --factory harness/examples/naive_reward.py:make_reward --tests-column test_cases
```

The naive reward pays 1.0 on exit code 0. Expected output, in brief (exit status 1; the time varies):

```text
Answers that solve nothing (gated; paid = score >= 0.999; >stub = score > 0.05 and above
the stub's score on the same task)
  class                 paid  >stub  partial  no score
  empty                0/10       0        0         0
  prose                0/10       0        0         0
  stub                 0/10       0        0         0
  print_pass_exit     10/10       0        0         0   PAID
  bare_exit           10/10       0        0         0   PAID
  fake_pass_lines      0/10       0        0         0
  always_equal        10/10       0        0         0   PAID
  os_exit             10/10       0        0         0   PAID
Correct references (control): 10/10 accepted (score >= 0.999; fenced 5/5, bare 5/5)
...
FAIL (1.7 s)
```

**2. Run the example that should pass.** The same suite against `securegrade`:

```sh
nice -n 19 python3 -m rewardcheck.selfcheck --factory harness/examples/securegrade_reward.py:make_reward --tests-column test_list --entry-point-column entry_point --setup-column test_imports
```

Every class shows 0 of 10 paid, all 10 references are accepted, and the last line is `PASS` (exit status 0).

**3. Run it on yours.** Put a zero-argument factory in a file, for example `my_reward.py`:

```python
def make_reward():
    def reward_fn(completions, test_cases, **kwargs):
        ...  # one float per completion
    return reward_fn
```

Then run `python3 -m rewardcheck.selfcheck --factory path/to/my_reward.py:make_reward` in the Python environment where your reward's dependencies are installed.

| Option | Meaning |
|---|---|
| `--tests-column NAME` | column your reward reads tests from (default `test_cases`; e.g. `test_list`, `reference`) |
| `--test-format asserts\|dicts` | `["assert f(1) == 2", ...]` (default) or `[{"input": ..., "expected_output": ...}, ...]` |
| `--entry-point-column NAME` | also pass the function name, e.g. `entry_point` |
| `--setup-column NAME` | also pass the task's setup code, as one list of setup lines per completion like MBPP's `test_imports` (`[[""]]` for these tasks) |
| `--min-reference-score X` | a reference is accepted at score X or above (default 0.999; lower it for a reward that blends in a style or format term) |
| `--scratch DIR`, `--out FILE` | scratch directory (default: a new temp dir) and JSON report (default `<scratch>/report.json`) |
| `--limit N`, `--timeout S`, `--time-budget S` | first N of the 5 tasks; per-cell deadline (30 s); overall budget (1,800 s) |

Exit status: 0 pass; 1 if any non-answer is paid, any non-answer other than the stub scores above the stub (and above 0.05), or any reference scores below `--min-reference-score`; 2 if it could not run. If no reference is accepted, the column names or test format usually do not match your reward.

A pass proves only that these fixtures were not paid. Full details: [`harness/README.md`](harness/README.md). Clean-copy check of this quick start: [transcript](harness/QUICKSTART-CHECK-2026-11-14.md).

## Use the hardened grader

```python
from securegrade import score
r = score(completion_text, ["assert add(1, 2) == 3"])       # MBPP-style assert list
r.score, r.passed, r.total, r.all_passed

from securegrade.trl_reward import secure_code_reward      # drop-in TRL reward function
```

Each answer runs in a fresh Python interpreter. Tests and expected values stay in the caller, which compares the values the answer returns. `securegrade.self_check()` reports which isolation layers are active and raises if a required one is missing.

**Limits.** Linux only, and Landlock is required by default. Version 0.1.3 is untested under root, inside Docker and on kernels with Yama enabled. It is not a general sandbox. Read "Required controls" and "Limits" in [`securegrade/README.md`](securegrade/README.md) before relying on it.

## A checklist for anyone writing code rewards

1. **Feed it a stub that should fail.** If a function that returns `None` scores above zero, the tests are not arriving.
2. **Feed it a correct reference.** If it scores below full, the tests or imports are wrong.
3. **Refuse rows with no tests.** A reward that pays when tests are missing pays for nothing.
4. **Never trust what the answer controls**: its exit status, its printed output, or the equality of objects it returns.
5. **Run each answer in its own process**, so one answer cannot end the batch or change another's score.
6. **Check the names the recipe uses** (`test` or `test_cases`) against the names the reward reads.

## What's in this repo

<img alt="A training loop connects MBPP prompts, Tiny Aya Global with a LoRA adapter, one selected reward callback and GRPO. Below, securegrade keeps tests and expected values in the caller; only arguments and returned data cross the fresh-interpreter boundary. rewardcheck separately audits the grader libraries." src="figures/article-visuals/architecture-astra.png" width="640">

| Path | What |
|---|---|
| [`WRITEUP.md`](WRITEUP.md) | the full write-up: method, results, limits, cost |
| [`CLAIMS.md`](CLAIMS.md) | experimental claims with their scope, sample size and source |
| [`harness/`](harness/) | `rewardcheck`; own README, quick start and MIT licence |
| [`securegrade/`](securegrade/) | the hardened grader; own README, CHANGELOG and MIT licence |
| [`exploits/`](exploits/) | the exploit suite (`exploits.json`) and benchmark tasks (`tasks.json`: 5 tasks; `tasks_all.json`: all MBPP-sanitized and HumanEval tasks) |
| [`jobs/`](jobs/) | the GRPO trainer, container entry scripts, hack detectors, fallback grader, elicitation texts, `requirements-lock.txt`. See [`jobs/README.md`](jobs/README.md). |
| [`scripts/`](scripts/) | audit drivers, PR checks, release re-audit (`release_*.py`), replay (`replay_release.py`), securegrade 0.1.2 and 0.1.3 checks (`sg_012_*.py`, `sg_013_*.py`), report builders, figure scripts |
| [`tests/`](tests/) | Gate 1 regression tests (they assert the measured behaviour of the audited wheels) |
| [`baseline/`](baseline/) | step-0 baseline scripts (code only) |
| [`design/`](design/) | the pre-registration and design notes, kept as written; dated appendices only |
| [`results/`](results/) | reports (`*.md`). The JSON files they cite are in the dataset repo (below). |
| [`figures/`](figures/) | figures (light and dark, PNG and SVG), their data as CSV, `tables.md`, `readme/` and `article-visuals/` |
| [`patches/aligntune/`](patches/aligntune/) | a patch against AlignTune `57e9a95` (MIT) with regression tests and AlignTune's notice |
| [`patches/safetune/`](patches/safetune/) | a prose description of SafeTune fixes and our own tests that call the installed package. No SafeTune source. |
| [`notes/`](notes/) | install notes for the audit environment |

Artifacts kept outside this repo:

| Artifact | Where |
|---|---|
| Run logs, all 32,000 training completions with both graders' scores, evals, result JSONs | HF dataset [`ebt005/p9-reward-hacking-logs`](https://huggingface.co/datasets/ebt005/p9-reward-hacking-logs) |
| Ten step-100 LoRA adapters for Tiny Aya Global (3.35B) | HF model repo [`ebt005/p9-tiny-aya-grpo-adapters`](https://huggingface.co/ebt005/p9-tiny-aya-grpo-adapters) |

## Reproduce

Everything was run on Linux (WSL2 Ubuntu 24.04 and HF Jobs / RunPod containers), Python 3.12. The audit is CPU only.

**Tests.** pytest is the only install. In the same shell as the quick start, from the repository root, make a venv and run the harness tests (28 tests):

```sh
python3 -m venv .venv    # needs python3-venv on Debian/Ubuntu; else: rm -rf .venv && uv venv --seed .venv
. .venv/bin/activate
pip install pytest
nice -n 19 python -m pytest harness/tests -q
```

Then, inside that venv, the securegrade and harness suites together:

```bash
PYTHONPATH="$PWD:$PWD/harness" python -m pytest -q securegrade/tests harness/tests
```

One securegrade test is held back from this repo, so the securegrade 0.1.3 suite here has 150 tests (148 pass and 2 skip in a venv without numpy), one fewer than the full 0.1.3 suite (151 tests with the held-back one). With the harness: 176 passed, 2 skipped.

**Audit, re-audit and replay.** These need the audited packages in their own virtualenvs (see [`notes/INSTALL.md`](notes/INSTALL.md), `scripts/install_*.sh`, `scripts/release_prepare.py`, and [`scripts/README.md`](scripts/README.md)). The helper scripts expect the virtualenvs under `~/p9/` and `uv` at `~/.local/bin/uv`. Several scripts and tests read result JSONs and run files that are published in the dataset repo, not here (`results/gate1-2026-11-01.json`, `results/release-reaudit-2026-11-08/`, `jobs/runs/<run>/`, which is `runs/<run>/` there); copy them into place first. The replay is `scripts/replay_release.py` (stages `prepare`, `grade`, `report`).

**Training.** [`jobs/README.md`](jobs/README.md) has the launch commands. They mount a private HF storage bucket that holds `jobs/` and `securegrade/`; set your own bucket name in place of the one in those commands, in `jobs/run_train.sh` and in `jobs/runpod_start.sh`.

## Status and limits

This is a research artifact. Read a report's limits before reusing its numbers.

- **Counterexamples, not prevalence.** The audit uses five demonstration tasks and a fixed set of fixtures. It shows the failures exist, not how common they are.
- **Source archives on WSL2.** The release checks used the exact source archives (AlignTune tag `ff59f10`, SafeTune merge `36b2142`), not PyPI wheels or a clean machine.
- **The replay is narrow.** MBPP only, one 3.35B model, five reward paths, and one mechanism: every early-exit answer came from a hinted prompt. The control was drawn from answers both old graders passed, so it gives no false-negative rate for correct code in general.
- **Training is uninformative** by the pre-registered rule. The learning rate also decayed linearly from 2e-5 to 2e-7 when the plan said constant; see the dated appendix in [`design/RUNS-2026-11-02.md`](design/RUNS-2026-11-02.md). Two later runs that state the hole in the prompt are exploratory ([report](results/hole-pair-2026-11-07.md)). Training used securegrade 0.1.0 and 0.1.1, not 0.1.2.
- **Rows with no tests can still be paid.** If a row reaches the reward without tests, AlignTune's `code_execution` and `code_verifiable` and SafeTune's `code_execution` can still pay a stub. AlignTune's own regression test documents this for `code_execution`. `rewardcheck` reports it as a configuration error. The fix is the caller's: refuse to score a row with no tests.
- **One further result is withheld pending private disclosure.**

## Related work

The exploit techniques are not new, and no priority is claimed for them. [Mareš 2021](https://ioinformatics.org/journal/v15_2021_37_52.pdf) covers grader isolation in programming contests, [Berkeley's benchmark audit](https://rdi.berkeley.edu/blog/trustworthy-benchmarks/) covers shared-process tampering in benchmarks, and [arXiv 2606.16062](https://arxiv.org/abs/2606.16062) covers weak task tests in code-RL environments.

Others filed public reports of the same tricks against other code graders in parallel with this work: [verl #8656](https://github.com/verl-project/verl/issues/8656), [LiveCodeBench #165](https://github.com/LiveCodeBench/LiveCodeBench/issues/165) and [human-eval #71](https://github.com/openai/human-eval/issues/71).

## Licences

- Code in this repo: MIT ([`LICENSE`](LICENSE); `harness/` and `securegrade/` carry their own copies).
- `patches/aligntune/`: a diff of AlignTune, which is MIT ([`patches/aligntune/NOTICE`](patches/aligntune/NOTICE)).
- SafeTune is under the Lexsi Labs Source Available License (LSAL v1.2). This repo contains no SafeTune source; `patches/safetune/tests/` only imports the installed package.
- `exploits/tasks*.json` contain MBPP (CC-BY-4.0) and HumanEval (MIT) tasks.

## Citation

```bibtex
@misc{rewards_pay_for_nothing_2026,
  title        = {Rewards that pay for nothing: auditing code-execution rewards in RL post-training libraries},
  author       = {{rewards-pay-for-nothing contributors}},
  year         = {2026},
  howpublished = {\url{https://github.com/ebt55/rewards-pay-for-nothing}}
}
```

Built for the Lexsi Labs AI Safety and Alignment Hackathon (Nov 2026).
