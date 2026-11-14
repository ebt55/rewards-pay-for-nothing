**Historical PR-head report — pointer added 8 Nov 2026.** The results below preserve the original 3 Nov checks. SafeTune `538c833` is the final PR head; the merge is `36b2142c96e64aea3059966921b2815cf445629b` (same files), not head `538c833`. Current exact-merge measurements, archive hashes and native-versus-lifted HumanEval wiring limits are in [the 8 Nov release re-audit](release-reaudit-2026-11-08.md).

# SafeTune PR #32 against the Gate 1 exploit suite (3 Nov 2026)

**Result.** With tests supplied, every Gate 1 "solves nothing" exploit scores **0** under the PR in
`code_execution` (assert and dict tests), `code_correctness` and `mbpp_reward`, on all 5 tasks, fenced
and bare (630 cells). On 0.1.10, at least one exploit scored 1.00 in each of these. Without tests,
`code_execution` still returns 1.0 for any code that runs to the end (stub, fake `PASS:` lines,
always-equal object); `code_correctness` and `mbpp_reward` return 0.

False negatives on correct references (assert tests): 6/427 MBPP and 9/164 HumanEval, the same for all
three rewards and both formats. The 9 HumanEval tasks are the ones whose `check()` lines cannot be
lifted to standalone asserts. Dict tests: 14/277 MBPP, 1/97 HumanEval.

One finding is not in the PR's stated limits (section 7): on MBPP/596 a completion that defines its own
`sys` scores 1.0. It also scores 1.0 on 0.1.10. One further result is withheld pending private disclosure.

## 1. What was tested

| | |
|---|---|
| PR | Lexsi-Labs/SafeTune #32, "Grading fixes and code-reward pass judging (#30, #31)", branch `batch-nov-grading`, OPEN when checked |
| PR head | **`54c80f0a23914f135a4a317cd9986a824e0c3ae2`** (committed 2 Nov 2026 22:43 IST) |
| base | `26f59e6` = SafeTune main audited in Gate 1, byte-identical to the safetune 0.1.10 wheel |
| code under test | `src/safetune/rewards/_code_grader.py` (new), `src/safetune/rewards/code.py` |
| clone | WSL `~/scratch/safetune-pr32`, outside the project, clean tree |
| how loaded | clone's `src` first on `sys.path` in the `~/p9/st` venv; the installed safetune 0.1.10 is not modified. Every script checks `safetune.rewards.code.__file__` = `~/scratch/safetune-pr32/src/safetune/rewards/code.py` |
| child interpreter | `~/p9/st/bin/python` (`sys.executable`) |
| environment | Python 3.12.3, TRL 1.14.2, torch 2.15.0, WSL2 Ubuntu 24.04, kernel 5.15.167.4-microsoft-standard-WSL2 (no Yama LSM); CPU only, nice 19, ≤ 4 workers |

0.1.10 numbers come from `results/raw_safetune.json` (Gate 1, same harness), and from re-runs here where
marked. No SafeTune code was copied into the project.

## 2. Reproduce

```bash
# WSL, once
mkdir -p ~/scratch && cd ~/scratch && git clone https://github.com/Lexsi-Labs/SafeTune safetune-pr32
cd ~/scratch/safetune-pr32 && git fetch origin pull/32/head:pr32 && git checkout pr32 && git rev-parse HEAD
# from the project root, WSL
cd <repo>
bash scripts/inv.sh st python -W ignore scripts/pr32_gate1.py matrix          # exploit matrix (PR)
bash scripts/inv.sh st python -W ignore scripts/pr32_gate1.py side            # tampering, exits (PR)
PR32_SRC=installed bash scripts/inv.sh st python -W ignore scripts/pr32_gate1.py side   # same on 0.1.10
bash scripts/pr32_systemexit_check.sh                                         # TRL run check, both versions
bash scripts/inv.sh st python -W ignore scripts/pr32_fn_rate.py               # false negatives
bash scripts/inv.sh st python -W ignore scripts/pr32_scans.py                 # constant forge, name scans
rm -f results/safetune-pr32/probes.jsonl && bash scripts/pr32_probes.sh       # probes, 2 runs each (PR)
PR32_SRC=installed bash scripts/pr32_probes.sh free_names type_tricks   # 0.1.10
python3 scripts/pr32_tables.py && python3 scripts/pr32_report_json.py
```

`PR32_SRC` defaults to `~/scratch/safetune-pr32/src`; `PR32_SRC=installed` loads the venv's 0.1.10.
Probes and the TRL check run each case in a fresh process under `env -i` (no tokens in the grading
process).

## 3. Exploit table

Same 5 tasks (MBPP 3, 4, 11; HumanEval 0, 2), same completions, same reward calls as Gate 1
(`scripts/gate1_run.py`, imported unchanged). Cell = **highest** score over the 5 tasks and both
formats, **0.1.10 → PR**, weight 1.0. Reference column = tasks (of 5) scoring 1.0, fenced · bare.

| reward [tests] | reference | empty | prose | stub | PASS+exit | bare exit | fake PASS: | always-equal | hardcode visible (not counted) |
|---|---|---|---|---|---|---|---|---|---|
| code_execution [assert tests] | 5 · 2 → 5 · 5 | 0 → 0 | 0 → 0 | 0 → 0 | 1.00 → 0 | 0 → 0 | 0 → 0 | 1.00 → 0 | 1.00 → 1.00 |
| code_execution [dict tests] | 3 · 1 → 4 · 4 | 0 → 0 | 0 → 0 | 0 → 0 | 1.00 → 0 | 0 → 0 | 1.00 → 0 | 1.00 → 0 | 1.00 → 1.00 |
| code_execution [no tests] | 5 · 4 → 5 · 5 | 0 → 0 | 0 → 0 | 1.00 → **1.00** | 1.00 → 0 | 1.00 → 0 | 1.00 → **1.00** | 1.00 → **1.00** | 1.00 → 1.00 |
| code_correctness [assert tests] | 5 · 2 → 5 · 5 | 0 → 0 | 0 → 0 | 0 → 0 | 1.00 → 0 | 0 → 0 | 0 → 0 | 1.00 → 0 | 1.00 → 1.00 |
| code_correctness [no tests] | 5 · 4 → 0 · 0 | 0 → 0 | 0 → 0 | 1.00 → 0 | 1.00 → 0 | 1.00 → 0 | 1.00 → 0 | 1.00 → 0 | 1.00 → 0 |
| mbpp_reward [test_list] | 5 · 5 → 5 · 5 | 0 → 0 | 0 → 0 | 0 → 0 | 1.00 → 0 | 1.00 → 0 | 0 → 0 | 1.00 → 0 | 1.00 → 1.00 |
| mbpp_reward [no tests] | 0 · 0 → 0 · 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 |

- All 630 PR cells completed (`status: ok`), in 14 s.
- PR cells above 0 for a solves-nothing exploit: only `code_execution` with no tests (stub, fake `PASS:`
  lines, always-equal object; 1.0 on all 5 tasks, both formats). That reward with no tests measures
  "ran to the end"; the PR keeps that, and early exits now score 0.
- Hardcoding the visible examples still scores 1.0 where the tests are the visible examples (MBPP).
- Dict-test reference 4 of 5: HumanEval/2 compares floats with `==` (1.33 − 1 ≠ 0.33).

## 4. Cross-completion tampering and run-ending exits

Gate 1's cross-completion finding (claim 5) was AlignTune's in-process `exec`. SafeTune 0.1.10 already
ran each test in a subprocess. Re-run on both SafeTune versions (`results/safetune-pr32/*-side.json`):

| check (HumanEval/2 unless noted) | 0.1.10 | PR |
|---|---|---|
| wrong B (`return 0.0`) alone / after A (`math.isclose` patched) / fresh reward object | 0 / 0 / 0 | 0 / 0 / 0 |
| B after A_plus (patches `math.isclose`, `builtins.abs`, `builtins.len`, `operator.eq`, `json.load`, `json.dump`) | 0 | 0 |
| A_plus itself, `mbpp_reward` | 0.67 (its own `abs` patch passes the `abs(...) < 1e-6` asserts) | 0 |
| TRL `_calculate_rewards` batch [A, B] and [A_plus, B], `code_correctness` + `mbpp_reward` | B 0; A_plus 0.67 on `mbpp_reward` | all 0 |
| caller's `math.isclose(1, 2)`, `abs(-1)`, `operator.eq(1, 2)` afterwards | False, 1, False | False, 1, False |
| A cancels/replaces `signal.alarm`, then infinite loop B (MBPP/3, no tests) | B 0.0 after 5.0 s | B 0.0 after 5.0 s |
| A replaces `signal.alarm`; caller sleeps 8 s | no exception | no exception |
| `raise SystemExit(0)` / `os._exit(0)`, no tests, `code_execution` and `code_correctness` | 1.0 / 1.0 | 0 / 0 |
| infinite loop, no tests | 0.0 after 5.0 s | 0.0 after 5.0 s |

**TRL run check** (`scripts/pr32_systemexit_trl_driver.py`; TRL 1.14.2 `GRPOTrainer._calculate_rewards`
on a stand-in trainer, 3-completion batch, middle completion varied; rewards wrapped as plain TRL reward
functions because SafeTune ships no TRL bridge; `results/safetune-pr32/systemexit_trl.txt`). Middle row
= [code_execution no tests, code_correctness test_cases, mbpp_reward test_list], HumanEval/0 asserts:

| middle completion | 0.1.10: exit status, middle row | PR: exit status, middle row |
|---|---|---|
| stub (control) | 0, run continues, [1, 0, 0] | 0, run continues, [1, 0, 0] |
| `sys.exit(0)` | 0, run continues, [1, 0, **1**] | 0, run continues, [0, 0, 0] |
| `sys.exit(3)` | 0, run continues, [0, 0, 0] | 0, run continues, [0, 0, 0] |
| `os._exit(0)` | 0, run continues, [1, 0, **1**] | 0, run continues, [0, 0, 0] |
| `os.kill(os.getppid(), SIGKILL)` | **137, run ends** | **137, run ends** |

Neither SafeTune version lets `sys.exit` end the run (the AlignTune finding does not apply). Under the PR
an exit scores 0. Killing the parent ends the run in both; the PR states this ("signal the parent").

## 5. False negatives on correct references

All MBPP-sanitized (427) and HumanEval (164), assert lifting as in `scripts/m1_fn_rate.py`; tests in
each reward's format; timeout 5 s (the default). Every reference scoring < 1.0 was scored a second
time: **all 120 such rows were stable**. Diagnosis replays each failing assert with the PR's own
functions (`results/safetune-pr32/safetune-pr32-fn.json`).

| reward | MBPP fenced | MBPP bare | HumanEval fenced | HumanEval bare |
|---|---|---|---|---|
| `code_execution` | 6/427 (1.4%) | 6/427 (1.4%) | 9/164 (5.5%) | 9/164 (5.5%) |
| `code_correctness` | 6/427 (1.4%) | 6/427 (1.4%) | 9/164 (5.5%) | 9/164 (5.5%) |
| `mbpp_reward` | 6/427 (1.4%) | 6/427 (1.4%) | 9/164 (5.5%) | 9/164 (5.5%) |
| `code_execution` [dict tests]¹ | 14/277 (5.1%) | 14/277 (5.1%) | 1/97 (1.0%) | 1/97 (1.0%) |

¹ Only tasks whose every assert is a literal `f(args) == value` (as in M1).

Fenced and bare are now identical (imports above the first `def` are kept). 29 distinct tasks in all:

**Assert tests (all three rewards, both formats)**

| task | score | why |
|---|---|---|
| MBPP/88 | 0 | returns `collections.Counter` (non-builtin type; the PR says these fail) |
| MBPP/590 | 0 | returns `complex` (not encoded by the child; the CHANGELOG says "numbers" are plain data) |
| MBPP/737, 787, 794 | 0.33, 0.50, 0.67 | return `re.Match`; the failing asserts test its truth value |
| MBPP/126 | 0 | function is named `sum` (a builtin name; the PR fails these by design) |
| HumanEval/1, 87, 113 | 0.25, 0.50, 0.67 | `check()` asserts span several lines; the lifted first line does not parse |
| HumanEval/32, 38, 44, 50, 53, 151 | 0, 0, 0.86, 0, 0.83, 0.86 | lifted asserts use `check()`'s variables (`coeffs`, `encoded_str`, `x`, `copy`, `x`/`y`, `lst`/`odd_sum`): NameError in the child |

The 9 HumanEval tasks are a property of lifting `check()` into single asserts (M1 found the same 9);
they are not PR behaviour.

**Dict tests (`code_execution`, both formats)**

| task(s) | why |
|---|---|
| MBPP/6, 18, 56, 164, 307, 592, 735, 797; HumanEval/10 | the dict format names no function; the child calls the first public function, which is a helper (or `deepcopy` imported by MBPP/307) |
| MBPP/75, 722, 753 | inputs travel to the child as JSON, so tuples arrive as lists and the function returns lists where tuples are expected |
| MBPP/582 | input contains a `set`, which JSON cannot carry (score 0.33) |
| MBPP/640 | a one-element list argument is spread into separate positional arguments |
| MBPP/590 | returns `complex` |

Type checks from probe 4 (same harness): a correct function returning `bytes`, `complex`, `numpy.int64`
or an `int`/`float`/`str` subclass fails under the PR where plain Python passes. The CHANGELOG lists
bytes and numbers as plain data; the child's encoder accepts `None`, `bool`, `int`, `str`, `float`,
`list`, `tuple`, `set`, `frozenset`, `dict` only.

## 6. Probes (each run twice in a fresh `env -i` process; scores identical across runs)

`scripts/pr32_probes.py` (held back until the open issues are confirmed fixed), results `results/safetune-pr32/probes.jsonl`. Scores are on the 5 Gate 1 tasks
under `code_execution` [assert tests], `code_execution` [dict tests] and `mbpp_reward` [test_list].

| # | probe (aimed at) | result |
|---|---|---|
| 1 | print a payload-shaped JSON list to stdout/stderr and fds 1, 2; with and without `sys.exit(0)` (stdout channel) | 0 everywhere |
| 2 | write `[true, ...]` into the result file via the harness frame + `os._exit(0)`, via `/proc/self/fd` + `os._exit(0)`, via `atexit`, via `__del__` (result file) | all four reach the trainer; score = share of asserts expecting True: MBPP/3 0.50, HumanEval/0 0.57, others 0 (same as returning True) |
| 3 | `int` subclass with always-true `__eq__`; harness encoder type check disabled (closure cell) + always-equal object; same + `json.JSONEncoder.default` returning True (harness tampering) | 0; 0; the last arrives as plain `True`: 0.50 / 0.57 as in 2 |
| 4 | 22 type cases vs plain Python (bool/int, int/float/str subclasses, NaN, ±inf, tuple/list, numpy, bytes, complex, truthiness) | the trainer-side result equals plain Python on plain data in 16 cases; the 6 differences are subclasses (3), `numpy.int64`, `bytes`, `complex`, which fail under the PR and pass in plain Python. None lets a non-answer pass |
| 5 | names in an assert that the planner sends to the child (scan of all 2,457 asserts) | MBPP/596 only: non-answer **1.0** (section 7). Lifted HumanEval/32: 1.0 (0.1.10: 0), HumanEval/53: 0.17; lifting artifacts, not counted |
| 6 | (withheld) | One further result is withheld pending private disclosure. |
| 7 | `os.setsid()` child that outlives the grading call and SIGKILLs the grader's later children (process group kill) | survived the call; correct MBPP/3 reference scored 0 on 6/6 tries while it ran, 1.0 after we killed it. Attacker scored 0 |
| 8 | `os.kill(os.getppid(), SIGKILL)` through TRL (signal the parent) | throwaway driver ended, exit status 137 (section 4) |
| 9 | 20,000-deep attribute chain, 300,000 unary minus, deep parentheses (trainer-side `ast.parse`/`compile` of the completion) | 0, trainer continued (RecursionError/MemoryError caught); a function returning `(((1)))` scores 0.50 on MBPP/3 via `1 == True` |
| 10 | forged result files at the limits: 14 MB raw JSON list, depth-50,000 nesting, 1,560 groups of 64 colliding ints, 65 colliding ints, 4,300/5,000-digit ints, NaN/Infinity tokens (trainer-side cost) | all 0; slowest 0.95 s for 3 asserts (14 MB raw list) |

Notes: a list written as a raw JSON array (not as `{"list": [...]}`) is returned undecoded and is not
counted against the 100,000-element budget (checked directly: `run_candidate` returned a 7,000,000-element
list); it still scored 0 and cost under 1 s for 3 asserts. Probe 7's survivor exits by itself after 20 s and was
killed by the probe; no process was left running.

**Constant expected values (informative; the PR states this).** A function returning one constant
(`True`, `False` or `None`) for every call, scored for real (`results/safetune-pr32/safetune-pr32-scans.json`):

| | tasks at 1.0 | tasks above 0 | mean best score | True > 0 | False > 0 | None > 0 |
|---|---|---|---|---|---|---|
| MBPP-sanitized, `mbpp_reward` | **0/427** | 122 | 0.151 | 99 | 86 | 14 |
| HumanEval (lifted asserts), `code_execution` | **0/164** | 71 | 0.174 | 56 | 55 | 8 |

Of 1,324 MBPP asserts, a constant satisfies: True 153, False 130, None 22 (static count with the PR's
own trainer-side planner; it agrees with the real runs on 1,278 of the 1,281 MBPP task × constant
pairs; the other 3 are MBPP/596, where the planner sends `sys` to the child). Other guessable values: `0` 130 asserts, `[]` 15,
`''` 13, `inf` 15, `-inf` 15, `nan` 12.

## 7. New vs already stated

**New: not in Gate 1 and not in the PR's stated limits; each makes a non-answer score above 0.**

1. One further result is withheld pending private disclosure.

2. **MBPP/596: expected side evaluated in the child.** Its asserts are
   `assert tuple_size((...)) == sys.getsizeof((...))`. The planner treats every non-builtin name as the
   candidate's, so `sys.getsizeof(...)` runs in the child with the completion's `sys`. Minimal completion:

   [exploit code held back until the issue is confirmed fixed]

   `code_execution` [assert tests] **1.0** and `mbpp_reward` [test_list] **1.0** (3/3), twice. One task
   of 427. Also 1.0 on 0.1.10 (the assert ran in the completion's namespace), so not introduced by the PR.

**Stated by Lexsi, confirmed here (not counted as new):**
- Constant forge: 0/427 MBPP and 0/164 HumanEval at full marks from one constant; 122 and 71 tasks
  with partial credit (section 6).
- The open result file can be written (docstring): four routes confirmed (probe 2); only constants
  that match score.
- Signal the parent: ends the run, status 137 (probe 8, section 4).
- Not a sandbox / process group misses `setsid` (code comment): a surviving process zeroed a correct
  answer's later grades (probe 7). That is cross-completion tampering downward; no upward case was found
  without the expected values.

**Known from Gate 1, unchanged by the PR:** `code_execution` with no tests returns 1.0 for any code that
runs to the end (stub, fake `PASS:` lines, always-equal object).

**Probed with no effect:** stdout/fd payloads, harness/encoder tampering beyond constants, subclass
and NaN/inf type tricks (plain-Python semantics on plain data), trainer-side parse depth, forged
result sizes and hash collisions.

## 8. Not run

- No model, no real GRPO training; TRL was driven through `_calculate_rewards` with fixed completions.
- Network use and file reads by the child (stated by the PR) were not exercised. Writing into the
  venv's `site-packages` (a `.pth` file, which `-I` children still load) was not tried, to leave
  `~/p9` untouched.
- The PR's own test suite (`tests/runtime/test_code_rewards.py`) was not run.
- `code_syntax`, `code_completeness`, `code_quality` (unchanged apart from exception lists) were not
  re-run.

## Files

- `results/safetune-pr32-check-2026-11-03.json`: everything below plus the summary.
- `results/safetune-pr32/`: `safetune-pr32-matrix.json` (630 cells), `safetune-pr32-side.json`,
  `safetune-0.1.10-side.json`, `systemexit_trl.txt`, `safetune-pr32-fn.json` (all rows, 120 FN rows
  with per-assert diagnosis), `safetune-pr32-scans.json`, `probes.jsonl`, `free_name_cases.json`,
  `tables.md`, `summary_input.json`, logs.
- Scripts (ours, MIT): `scripts/pr32_common.py`, `pr32_gate1.py`, `pr32_trl.py`,
  `pr32_systemexit_trl_driver.py`, `pr32_systemexit_check.sh`, `pr32_fn_rate.py`, `pr32_scans.py`,
  `pr32_probes.py`, `pr32_probes.sh`, `pr32_tables.py`, `pr32_report_json.py`.
