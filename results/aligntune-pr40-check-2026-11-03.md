**Historical PR-head report — pointer added 8 Nov 2026.** The results below apply to tested head `61d89e4`, not the later exact release tag `ff59f10`. Current exact-source measurements, source-archive fallback/hashes, compatibility and residual-class status are in [the 8 Nov release re-audit](release-reaudit-2026-11-08.md). In particular, do not carry the historical memory or bare-import findings forward as release claims.

# AlignTune PR #40 against the Gate 1 exploit suite (3 Nov 2026)

**Result.** With tests supplied, every Gate 1 "solves nothing" exploit scores **0 or below** under the
PR in `code_execution`, `code_correctness`, `mbpp_reward`, `code_verifiable` and the counterfactual-GRPO
code reward, on all 5 tasks, fenced and bare (1,080 cells). On 0.1.28 each of these paid 1.00 for at
least one exploit (the counterfactual reward up to 3.33). The two AlignTune-specific Gate 1 findings no
longer reproduce: cross-completion tampering leaves the wrong answer at 0 and the trainer's builtins
untouched, and `sys.exit(0)` in a completion no longer ends a TRL run (it scores 0). Without tests,
`code_execution` and `code_verifiable` still return 1.0 for any code that runs to the end.

False negatives on correct references, assert tests: `code_execution` 6/427 MBPP and 9/164 HumanEval
(lifted asserts) or 5/164 (the row's own `test` + `entry_point` columns, which the PR now reads).
Details in section 6.

New (section 8): three ways a non-answer still scores 1.0 that are not in the PR's stated limits:
reading expected values from the grading process's memory (395/427 MBPP at 1.0 on this kernel),
MBPP/596's `sys` name, and, on the counterfactual evalplus path, a leftover process that forges both
the canonical and the candidate results. Also new, run-ending: a 20,000-deep expression makes
`mbpp_reward` and the counterfactual reward raise, which ends a TRL run with a traceback (also on 0.1.28).

## 1. What was tested

| | |
|---|---|
| PR | Lexsi-Labs/aligntune #40, branch `batch-oct-fixes`, OPEN when checked (release 0.1.29) |
| PR head | **`61d89e4d8ce0be942c7aaea1153c0abf7da31db3`** (committed 3 Nov 2026 13:17 IST) |
| base | `57e9a95` = AlignTune main audited in Gate 1, byte-identical to the aligntune 0.1.28 wheel |
| code under test | `rewards/_code_grader.py` (new), `rewards/core.py`, `rewards/verifiable.py`, `backends/trl/rl/counterfact_grpo/counterfact_grpo.py`, the three recipe files |
| clone | WSL `~/scratch/aligntune-pr40`, outside the project, clean tree; the PR changes no dependency files |
| how loaded | clone's `src` first on `sys.path` (our scripts) or `PYTHONPATH` (Gate 1's unchanged driver, our pytest suite) in the `~/p9/at` venv; aligntune 0.1.28 stays installed there, not modified. Every run checks `aligntune.rewards.core.__file__` = `~/scratch/aligntune-pr40/src/aligntune/rewards/core.py` |
| environment | Python 3.12.3, TRL 1.7.1, torch 2.11.0, WSL2 Ubuntu 24.04 (kernel without Yama); CPU only, nice 19, ≤ 4 workers |

0.1.28 numbers come from Gate 1 (`results/raw_aligntune.json`, same harness) and from re-runs here
where marked.

## 2. Reproduce

```bash
# WSL, once
mkdir -p ~/scratch && cd ~/scratch && git clone https://github.com/Lexsi-Labs/aligntune aligntune-pr40
cd ~/scratch/aligntune-pr40 && git fetch origin pull/40/head:pr40 && git checkout pr40 && git rev-parse HEAD
cd <repo>
bash scripts/inv.sh at python -W ignore scripts/pr40_gate1.py matrix        # exploit matrix (PR)
bash scripts/inv.sh at python -W ignore scripts/pr40_gate1.py side          # Gate 1 AlignTune side experiments (PR)
PR40_SRC=installed bash scripts/inv.sh at python -W ignore scripts/pr40_gate1.py side   # extra sides on 0.1.28
# A_plus baseline, twice per version (prints with os.write; A_plus patches builtins in-process on 0.1.28)
for s in installed ~/scratch/aligntune-pr40/src; do for i in 1 2; do env -i HOME=$HOME PATH=$HOME/p9/at/bin:/usr/bin:/bin PR40_SRC=$s \
  nice -n 19 ~/p9/at/bin/python -W ignore scripts/pr40_baseline_aplus.py; done; done
bash scripts/pr40_systemexit_check.sh                                       # TRL run check, both versions
env -i HOME=$HOME PATH=$HOME/p9/at/bin:/usr/bin:/bin PR40_SRC=<installed|clone src> \
  nice -n 19 ~/p9/at/bin/python -W ignore scripts/pr40_crash_driver.py <none|deep> <mbpp_bridge|counterfact>
bash scripts/inv.sh at python -W ignore scripts/pr40_fn_rate.py             # false negatives
bash scripts/inv.sh at python -W ignore scripts/pr40_scans.py               # constant forge, name scans
HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 bash scripts/inv.sh at python -W ignore scripts/pr40_recipe.py
rm -f results/aligntune-pr40/probes.jsonl && bash scripts/pr40_probes.sh    # probes, 2 runs each (PR)
PR40_SRC=installed bash scripts/pr40_probes.sh free_names                   # same probe on 0.1.28
env -i HOME=$HOME PATH=$HOME/p9/at/bin:/usr/bin:/bin PYTHONPATH=$HOME/scratch/aligntune-pr40/src \
  ~/p9/at/bin/python -m pytest -q -p no:cacheprovider patches/aligntune/tests
python3 scripts/pr40_tables.py && python3 scripts/pr40_report_json.py
```

## 3. Exploit table

Same 5 tasks, completions and reward calls as Gate 1 (`scripts/gate1_run.py` `AT_SPECS`, imported
unchanged). Cell = **highest** score over 5 tasks × 2 formats, **0.1.28 → PR**, weight 1.0. Reference =
tasks (of 5) at ≥ 0.95, fenced · bare. `mbpp_reward` and the counterfactual reward subtract penalties, so
their floor is below 0. "raised" = `SystemExit` escaped `compute()` in some cells (0.1.28).

| reward [tests] | reference | empty | prose | stub | PASS+exit | bare exit | fake PASS: | always-equal | hardcode visible (not counted) |
|---|---|---|---|---|---|---|---|---|---|
| code_execution [assert tests] | 5 · 2 → 5 · 5 | 0 → 0 | 0 → 0 | 0 → 0 | 1.00 → 0 | 0 → 0 | 0 → 0 | 1.00 → 0 | 1.00 → 1.00 |
| code_execution [dict tests] | 4 · 2 → 5 · 5 | 0 → 0 | 0 → 0 | 0 → 0 | 1.00 → 0 | 0 → 0 | 1.00 → 0 | 1.00 → 0 | 1.00 → 1.00 |
| code_execution [no tests] | 5 · 4 → 5 · 5 | 0 → 0 | 0 → 0 | 1.00 → **1.00** | 0 (raised) → 0 | 0 (raised) → 0 | 1.00 → **1.00** | 1.00 → **1.00** | 1.00 → 1.00 |
| code_correctness [dict tests] | 0 · 4 → 5 · 5 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 1.00 → 0 | 1.00 → 1.00 |
| code_correctness [assert tests] | 0 · 0 → 5 · 5 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 1.00 |
| code_correctness [no tests] | 0 · 0 → 0 · 0 | 0.50 → 0 | 0 → 0 | 0.50 → 0 | 0.50 → 0 | 0.50 → 0 | 0.50 → 0 | 0.50 → 0 | 0.50 → 0 |
| mbpp_reward [test_cases] | 5 · 5 → 5 · 5 | -0.10 → -0.10 | -0.10 → -0.10 | -0.10 → -0.10 | -0.12 → -0.17 | -0.10 → -0.15 | 1.00 → -0.12 | 1.00 → -0.10 | 1.00 → 1.00 |
| mbpp_reward [no tests] | 0 · 0 → 0 · 0 | -0.10 → -0.10 | -0.10 → -0.10 | -0.10 → -0.10 | -0.10 → -0.10 | -0.10 → -0.10 | -0.10 → -0.10 | -0.10 → -0.10 | -0.10 → -0.10 |
| code_verifiable [reference = asserts] | 5 · 2 → 5 · 2 | 0 → 0 | 0 → 0 | 0 → 0 | 1.00 → 0 | 1.00 → 0 | 0 → 0 | 1.00 → 0 | 1.00 → 1.00 |
| code_verifiable [no tests] | 5 · 4 → 5 · 4 | 0 → 0 | 0 → 0 | 1.00 → **1.00** | 1.00 → 0 | 1.00 → 0 | 1.00 → **1.00** | 1.00 → **1.00** | 1.00 → 1.00 |
| counterfactual code reward [tests] | 5 · 4 → 5 · 4 | -0.10 → -0.10 | -0.10 → -0.10 | -0.10 → -0.10 | -0.10 → -0.15 | -0.10 → -0.15 | 3.33 → -0.10 | 1.00 → -0.10 | 1.00 → 1.00 |
| counterfactual code reward [no tests] | 0 · 0 → 0 · 0 | -0.10 everywhere → -0.10 everywhere | | | | | | | |

- All 1,080 PR cells completed (`status: ok`).
- **No-tests behaviour (item 3).** `code_execution` and `code_verifiable` with no tests return **1.0** for
  any code that runs to the end (stub, fake `PASS:` lines, always-equal object, on all 5 tasks, both
  formats); early exits now score 0. `code_correctness` returns 0 (0.1.28: 0.50 for anything that
  compiled, bare); `mbpp_reward` and the counterfactual reward return -0.10.
- `code_verifiable` bare references: 2 of 5 still pass; its own `_extract_code` (not changed by the PR)
  drops imports above the first `def` in unfenced code (section 6). The counterfactual reward's bare
  reference: 4 of 5, as on 0.1.28.
- Our M1 regression suite for a fixed AlignTune (`patches/aligntune/tests`, 88 tests) on the PR:
  **87 passed, 1 failed** (`code_verifiable`, bare reference MBPP/3, the import case above).

## 4. Gate 1's AlignTune findings on the PR

| check | 0.1.28 | PR |
|---|---|---|
| Claim 5: wrong B after A patches `math.isclose`, `code_correctness` dict tests, HumanEval/2 (Gate 1 side) | B 0.0 → **1.0**, also on a fresh object; caller's `math.isclose(1, 2)` True | B 0.0 → 0.0; fresh object 0.0; caller's `math.isclose` unchanged |
| Same, as one GRPO batch through AlignTune's TRL RewardBridge | `[B,B]` [0, 0], `[A,B]` [1.0, 1.0] | `[B,B]` [0, 0], `[A,B]` [0, 0] |
| A_plus (also patches `builtins.abs`, `builtins.len`, `operator.eq`, `json`) then B, `code_correctness` dicts; run twice (`aplus_baseline.txt`) | A_plus raised ZeroDivisionError; caller's `len` replaced, `abs(-1)` = 0; B then **1.0** (same and fresh object) | A_plus 0.0; caller untouched; B 0.0 |
| A_plus then B on `code_execution`, `code_correctness` (asserts), `mbpp_reward`, `code_verifiable`, counterfactual; and through the bridge | the side process died (exit status 1) | B 0 / -0.10 everywhere; caller untouched |
| A cancels/replaces `signal.alarm`, then infinite-loop B (`code_execution`, no tests) | B never returned (killed at 40 s) | B 0.0 after 5 s |
| A replaces `signal.alarm`; caller sleeps | `TimeoutError` in the caller after 7.3 s | no exception in 15 s |
| infinite loop, `code_correctness` with tests | hung (killed at 40 s) | 0.0 after 5 s |
| `sys.exit` / `os._exit` inside `compute()` (no tests; `code_correctness` with tests) | `SystemExit` escaped; `os._exit` killed the process | `compute()` returned normally; 0.0 |
| `code_execution` (no tests) called from a worker thread | reference 0.0 | reference 1.0 |
| `MBPPReward` temp files left after 3 calls | 3 | 0 |
| registry defaults: `code_execution` stub (no tests) / print+exit (tests); `code_correctness` empty / always-equal; `mbpp_reward` fake PASS; `code_verifiable` bare exit | 1.0 / 1.0; 0.15 / 0.30; 1.0; 1.0 | 1.0 / 0.0; 0.0 / 0.0; -0.14; 0.0 |

**TRL run check** (`results/aligntune-pr40/systemexit_trl.txt`; TRL 1.7.1 `GRPOTrainer._calculate_rewards`,
stand-in trainer, 3-completion batch, middle completion varied). Part A is Gate 1's own driver, unchanged
(recipe's `code_execution` entry, weight 0.2, no tests in the row). Part B adds `code_correctness`,
`mbpp_reward` and `code_verifiable`, fed HumanEval/0's `test` + `entry_point` columns.

| middle completion | 0.1.28 | PR |
|---|---|---|
| A: stub (control) | exit 0, continues, [1, 1, 1] | exit 0, continues, [1, 1, 1] |
| A: `sys.exit(0)` | **exit 0, nothing after the reward call runs** | exit 0, continues, middle **0.0** |
| A: `sys.exit(3)` | **exit 3** | exit 0, continues, middle 0.0 |
| B: `sys.exit(0)` / `os._exit(0)` | exit 0, run ends | continues; middle row [0, 0, -0.17, 0] |
| B: `sys.exit(3)` | exit 3, run ends | continues; middle row [0, 0, -0.17, 0] |
| B: `os.kill(os.getppid(), SIGKILL)` | **exit 137, run ends** | **exit 137, run ends** (stated by Lexsi) |

## 5. Recipes

| file | 0.1.28 | PR |
|---|---|---|
| `recipes/configs/grpo/deepseek_humaneval.yaml` | dataset `openai/humaneval`: `DatasetNotFoundError` | `openai/openai_humaneval`; loads through `DataManager` (164 rows, from the local cache in offline mode) |
| `recipes/configs/advanced/gbmpo_l2_code.yaml` | `openai/humaneval` | `openai/openai_humaneval` (same rewards as above; not simulated separately) |
| `examples/grpo_code_gen_trl_mbpp.py` | rewards `code_quality` (style only) | rewards `mbpp_reward` |

Tests now reach the rewards: the rows keep `test` and `entry_point`, and the PR's rewards read them. HumanEval/0
through the recipe's three rewards, as TRL would total them (weights 0.5 / 0.3 / 0.2, applied once):

| completion | code_correctness | code_quality | code_execution | total (0.1.28 total) |
|---|---|---|---|---|
| canonical body only (continuation of the prompt) | 1.0 | 0.44 | 1.0 | **0.833** (0.040) |
| canonical full function, fenced | 1.0 | 0.67 | 1.0 | **0.901** (0.260) |
| canonical full function, bare | 1.0 | 0.86 | 1.0 | **0.959** (0.203) |
| stub, bare | 0 | 0.59 | 0 | 0.176 (0.378) |
| stub, fenced | 0 | 0.34 | 0 | 0.101 (0.230) |
| prose | 0 | 0.34 | 0 | 0.101 (0.030) |
| always-equal, bare | 0 | 0.65 | 0 | 0.195 |
| wrong (`return True`), fenced | 0.57 | 0.34 | 0.57 | 0.501 (0.230) |
| empty | 0 | 0 | 0 | 0.000 (0.125) |

The non-answers' remaining 0.10–0.20 is `code_quality`, a style score the recipe still weights 0.3.
MBPP example on MBPP/3, 4, 11 with the `test_list` column: reference 1.0 bare, 0.98–0.99 fenced; stub
-0.12, prose and empty -0.10.

## 6. False negatives on correct references

All MBPP-sanitized (427) and HumanEval (164), M1's reward calls and assert lifting; HumanEval also through
its own `test` + `entry_point` columns ("[columns]"). Timeout 5 s. Count = references with at least one
failing test, diagnosed test by test with the PR's own functions; all 994 rows below 1.0 were scored twice
and were stable. `mbpp_reward` also lowers passing answers by its format terms (-0.02 per fence, etc.);
those all-pass rows are counted separately.

| reward [tests] | MBPP fenced | MBPP bare | HumanEval fenced | HumanEval bare |
|---|---|---|---|---|
| `code_execution` | 6/427 | 6/427 | 9/164 | 9/164 |
| `code_correctness` [assert tests] | 6/427 | 6/427 | 9/164 | 9/164 |
| `code_correctness` [dict tests]¹ | 10/277 | 10/277 | 1/97 | 1/97 |
| `mbpp_reward` | 12/427 (+319 all-pass, < 1.0) | 12/427 | 12/164 (+152) | 12/164 (+28) |
| `code_verifiable` | 6/427 | **74/427** | 9/164 | **27/164** |
| `code_execution` [columns] | – | – | 5/164 | 5/164 |
| `code_correctness` [columns] | – | – | 5/164 | 5/164 |
| `mbpp_reward` [columns] | – | – | 8/164 (+156) | 8/164 (+28) |
| `code_verifiable` [columns] | – | – | 5/164 | 24/164 |

¹ Tasks whose every assert is a literal `f(args) == value`. For comparison, M1 measured 0.1.28 (threshold
0.95): `code_execution` 10 / 81 MBPP and 9 / 27 HumanEval (fenced / bare); `code_correctness` dict
tests 277/277 fenced, 14/277 bare.

Reasons (full per-task list in the JSON, `false_negatives.by_task`):

| task(s) | rewards | why |
|---|---|---|
| MBPP/88, 590, 737, 787, 794 | all assert-test rewards | return `collections.Counter`, `complex`, `re.Match` (not plain data; the PR fails these by design) |
| MBPP/126 | all assert-test rewards | the function is named `sum` (builtin name; fails by design) |
| HumanEval/1, 32, 38, 44, 50, 53, 87, 113, 151 | lifted asserts | our single-line lifting of `check()` (multi-line asserts, loop variables); M1 found the same 9 |
| HumanEval/32, 38, 44, 50, 53 | [columns] | `check()` asserts inside loops over random or generated inputs; the PR turns each such statement into a failing test, with a warning |
| MBPP/2, 7, 111, 140, 232; HumanEval/4, 33, 37 | `mbpp_reward` | `mbpp_reward` reads the function name from the first call in the first test, which is `set(...)`, `abs(...)` or `tuple(...)`; it then appends `set = <function>` (etc.) to the code, and the PR's builtin-name rule fails every test |
| MBPP/77 | `mbpp_reward` | `assert is_Diff (12345) == False`: the space before `(` defeats the name regex, so the reward returns -0.10 |
| 68 MBPP + 18 HumanEval (bare only) | `code_verifiable` | `code_verifiable`'s own extractor keeps unfenced code only from the first `def`/`class`, so `import math`, `re`, `heapq`, `from typing import List`, etc. are lost (NameError); unchanged by the PR |
| MBPP/6, 18, 56, 164, 592, 735, 797; HumanEval/10 | dict tests | the dict format names no function; the child calls the first function the code defines, here a helper |
| MBPP/582 | dict tests | input holds a `set`, which JSON cannot carry |
| MBPP/722 | dict tests | tuples inside a dict arrive as lists; the comparison tolerates list/tuple only in sequences |

Compared with the SafeTune PR #32 harness, the AlignTune dict path no longer fails MBPP/75, 307, 640, 753
(it calls the first function the code defines, splats only multi-element inputs, and compares lists and
tuples element-wise).

## 7. Probes (each run twice in a fresh `env -i` process; scores identical across runs)

`scripts/pr40_probes.py` (held back until the open issues are confirmed fixed), results `results/aligntune-pr40/probes.jsonl`. Rewards: `code_execution`
(assert and dict tests), `code_correctness` (asserts), `mbpp_reward`, `code_verifiable`, counterfactual.

| # | probe | result |
|---|---|---|
| 1 | payload-shaped JSON on stdout, stderr, fds 1 and 2, with and without `sys.exit(0)` | 0 (penalties below 0 for `mbpp_reward`, counterfactual) |
| 2 | forge `[true, ...]` into the result file via the harness frame + `os._exit(0)`; via `/proc/self/fd` + `os._exit(0)`; via `atexit`; via `__del__` | frame and `/proc/self/fd`: score = share of asserts expecting True (MBPP/3 0.50, HumanEval/0 0.57, others ≤ 0; `code_verifiable`, all-or-nothing, 0). `atexit` and `__del__`: 0 (the harness ends with `os._exit`) |
| 3 | int subclass with always-true `__eq__`; encoder type check disabled + always-equal object; same + `JSONEncoder.default` → True | 0; 0; plain `True` → same as 2 |
| 4 | 22 type cases vs plain Python | 16 the same; the 6 differences (int/float/str subclasses, `numpy.int64`, `bytes`, `complex`) fail under the PR and pass in Python. None lets a non-answer pass |
| 5 | MBPP/596 `sys` shadowing (does the whitelist evaluator close it?) | **No: 1.0** (section 8). Lifted HumanEval/32: 1.0, but 0.0 through the PR's own `test` + `entry_point` columns |
| 6 | expected values from the trainer's memory (`/proc/<ppid>/mem`) + control | **1.0** (section 8); control 0 |
| 7 | `setsid` survivor that SIGKILLs the grader's later children | survives the call; correct MBPP/3 reference 0.0 on 6/6 tries while it runs, 1.0 after we kill it (stated limit) |
| 8 | the same survivor on the counterfactual evalplus path, forging both result files | non-answer **1.0** (section 8) |
| 9 | 20,000-deep attribute chain; 300,000 unary minus; `(((1)))` | `code_execution`, `code_correctness`, `code_verifiable`: 0. **`mbpp_reward` and the counterfactual reward raise** `RecursionError` / `MemoryError` out of `compute()` (section 8). `(((1)))` scores 0.50 on MBPP/3 via `1 == True` |
| 10 | forged result files at the limits (7 M-element raw list, depth 50,000, 1,560 × 64 colliding ints, 65 colliding, 4,300/5,000-digit ints, NaN/Infinity tokens) | all 0; slowest 0.35 s for 3 asserts; raw JSON lists are now refused |

**Constant expected values (informative; stated).** One constant (`True`/`False`/`None`) for every call:
MBPP **0/427** tasks at 1.0, 122 above 0 (`code_execution`, mean best 0.151); `mbpp_reward` above 0 on 121,
max 0.67. HumanEval (lifted) **0/164** at 1.0, 71 above 0. Of 1,324 MBPP asserts, True satisfies 153, False
130, None 22 (static count with the PR's planner; the same planner as SafeTune PR #32).

## 8. New vs already stated

**New, pays a non-answer above 0** (not in Gate 1, not in the PR's stated limits):

1. **Expected values read from the grading process's memory.** The completion reads
   `/proc/<os.getppid()>/mem`, finds the `assert <fn>(...) == <literal>` strings, and returns the literals
   (`MEMREAD`, 55 lines, held back until the issue is confirmed fixed).
   - 1.0 on MBPP/3, 4, 11 and HumanEval/0, 2 under `code_execution` (assert and dict tests²),
     `code_correctness` (asserts) and `code_verifiable`; 0.98 under `mbpp_reward` (format terms); the
     counterfactual reward 1.0 on 2 of 5. HumanEval/0 through its `test` + `entry_point` columns: 1.0.
   - All MBPP-sanitized: `code_execution` **395/427 at 1.0**, 405 above 0, mean 0.938; `mbpp_reward` 404
     above 0, mean 0.911.
   - Reproduced twice, identical. Control (reading its own memory): 0.
   - Condition: this kernel has no Yama, so a same-user child may read its parent's memory. Not tested
     with Yama `ptrace_scope` ≥ 1, which should refuse it.

   ² The grading process in this harness also holds the assert strings.
2. **MBPP/596: expected side evaluated in the child.** The asserts compare with `sys.getsizeof(...)`; the
   planner sends every non-builtin name to the child, where the completion defines `sys`:

   [exploit code held back until the issue is confirmed fixed]

   PR: `code_execution` **1.0**, `code_correctness` (asserts) **1.0**, `code_verifiable` **1.0**,
   `mbpp_reward` **0.99**; twice. One task of 427. 0.1.28: 1.0 / (0: did not read asserts) / 1.0 / 0.99.
3. **Counterfactual evalplus path: both sides forged.** In `_run_evalplus_tests` the expected values come
   from the canonical solution run in its own child, read back the same way as the candidate's. Completion
   A (`CF_SURVIVOR` in `scripts/pr40_probes.py`) leaves a `setsid` process that, for every later grading
   child, reads the item count from `job.json`, stops the child once its result file is open, writes
   `[0, 0, ...]` into it, and kills it. B is `def f(*args, **kwargs): return None`.
   - MBPP/4 (3 inputs) and HumanEval/0 (7 inputs): B alone **-0.10**; in batch `[A, B, B, C]` B scores
     **1.0, 1.0**; in a later batch while the process runs, B **1.0**; after we kill it, B -0.10. Twice,
     identical.
   - Built only from stated limits (setsid leaves the group, signals, file writes). What is not stated:
     here no expected value has to be known, because both sides read back zeros. The trainer fills this
     path from evalplus MBPP+ when `evalplus` is installed (read, not run); we built `prompt_to_data` by
     hand (`evalplus` is not installed here).

**New, ends a run** (not a payout): a fenced 20,000-deep attribute chain makes `mbpp_reward` raise
`RecursionError` (its `_prepare_for_exec` catches `SyntaxError` only); AlignTune's RewardBridge re-raises it
as `RuntimeError`, and TRL's `_calculate_rewards` exits with status 1 and a traceback. The counterfactual
code reward raises `RecursionError` the same way. 300,000 unary minus gives `MemoryError`. Twice per path,
same on 0.1.28 (`results/aligntune-pr40/crash_deep_nesting.txt`).

**Stated by Lexsi, confirmed:** constant forge (0 tasks at full marks, partial credit as above); the result
file can be written (frame and `/proc/self/fd` routes, constants only); signal the parent (exit 137);
`setsid` leaves the process group (a survivor zeroed a correct answer's later grades).

**Known from Gate 1, unchanged:** `code_execution` and `code_verifiable` with no tests return 1.0 for any
code that runs to the end.

## 9. Not run

- No model, no real GRPO training; TRL driven through `_calculate_rewards` with fixed completions.
- `eval/safe_executor.py` (pass@k evaluation, also rewritten), the Unsloth backends and `sql_verifiable`
  were not tested. `gbmpo_l2_code.yaml` was read, not simulated.
- The evalplus path ran with a hand-built `prompt_to_data` (`evalplus` is not installed); 0.1.28's evalplus
  path was not run.
- Memory read not tested with Yama enabled, in Docker or on HF Jobs. Network and file reads by the child
  (stated) not exercised. No `.pth` written into the venv.

## Files

- `results/aligntune-pr40-check-2026-11-03.json`: summary, exploit table, side experiments, TRL runs,
  deep-nesting runs, recipe, FN rows with diagnosis, scans, probes.
- `results/aligntune-pr40/`: `aligntune-pr40-matrix.json` (1,080 cells), `aligntune-pr40-side.json`,
  `aligntune-0.1.28-side.json`, `aplus_baseline.txt`, `systemexit_trl.txt`, `crash_deep_nesting.txt`,
  `aligntune-pr40-fn.json`, `aligntune-pr40-scans.json`, `aligntune-pr40-recipe.json`, `probes.jsonl`,
  `patched_tests_on_pr40.txt`, `tables.md`, `summary_input.json`, logs.
- Scripts (ours, MIT): `scripts/pr40_common.py`, `pr40_gate1.py`, `pr40_baseline_aplus.py`,
  `pr40_systemexit_trl_driver.py`, `pr40_systemexit_check.sh`, `pr40_crash_driver.py`, `pr40_fn_rate.py`,
  `pr40_scans.py`, `pr40_recipe.py`, `pr40_probes.py`, `pr40_probes.sh`, `pr40_tables.py`,
  `pr40_report_json.py`, `probe_texts.py` (shared with the PR #32 probes).
