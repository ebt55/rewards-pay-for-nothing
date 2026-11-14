# AlignTune code-reward patch (against 57e9a95)

`aligntune-57e9a95-securegrade-fixes.diff` is a unified diff against AlignTune commit `57e9a95`
(GitHub `main` on 1 Nov 2026, identical to the 0.1.28 wheel for these files). AlignTune is MIT; so
is this patch and its tests. **Not submitted anywhere**: no PR, issue or comment was opened.

Files touched: `src/aligntune/rewards/core.py`, `src/aligntune/rewards/verifiable.py`, new
`src/aligntune/rewards/_code_sandbox.py`, both HumanEval recipes
(`recipes/configs/grpo/deepseek_humaneval.yaml`, `recipes/configs/advanced/gbmpo_l2_code.yaml`) and
`examples/grpo_code_gen_trl_mbpp.py`. 6 files, +502 / -385 lines.

How it was built: `git clone` of Lexsi-Labs/aligntune at `57e9a95` into `~/p9/src/aligntune-patched`,
small edits by hand, block edits by `apply_block_edits.py`, diff by `apply.sh`. The patched tree is
installed (non-editable, same dependency set as `~/p9/at`, PyICU excluded) in `~/p9/at-patched` by
`scripts/install_aligntune_patched.sh`. Regression tests: `tests/test_patched_rewards.py` (88 tests,
all pass on the patched install).

## What changed

| | before | after |
|---|---|---|
| where model code runs | `CodeExecutionReward` (no tests) and `CodeCorrectnessReward`: `exec()` in the trainer process | always a child `sys.executable -I` process: temp cwd, minimal env, RLIMIT CPU/AS 1 GiB/FSIZE/NPROC, wall timeout, process-group kill |
| what counts as a pass | "PASS" in stdout and exit 0 (`code_execution`); count of printed `PASS:` lines (`mbpp_reward`); exit 0 (`code_verifiable`); `==` in-process (`code_correctness`) | **values out**: the child returns only the values of the calls the asserts make, as plain data; the assert or the expected-output comparison runs in the trainer process. stdout and exit codes are ignored |
| non-data return values (e.g. `re.Match`) | compared in-process | only their truth value crosses, as an object that equals nothing (passes `assert f(x)`, never `==`) |
| stdlib modules the asserts use without importing (`math`, `sys`) | borrowed from the candidate's namespace | imported on the trusted side |
| `SystemExit` / `os._exit` | escaped `compute()` and ended a TRL run silently with status 0 | the child reports a failed run; nothing reaches the caller |
| comparison | bare `==` on whatever the candidate returned | only on decoded plain data (`is_plain` check in `_compare_outputs`) |
| `CodeCorrectnessReward` | no fence stripping; dict tests only; first callable in namespace; 0.5 × weight for anything that compiles, including the empty string | delegates to `CodeExecutionReward` (fences stripped; asserts, dicts or HumanEval tests); **0.0 with no tests** plus a one-time warning |
| extractor (bare code) | kept lines from the first `def`, dropping imports above it | starts at the first top-level `def`/`import`/`from`/`class`/`@` line |
| dict tests | first callable in globals (picked `typing.List`) | first public top-level `def` in the code |
| interpreter | `'python'` via PATH (`code_execution`), `/usr/bin/python3` (`code_verifiable`) | `sys.executable` |
| `MBPPReward` | `os.unlink` without `import os` (temp file leaked every call); `assert set(f(x))` parsed as testing `set` | `import os`; first non-builtin called name |
| where tests come from | only `test_cases` (no dataset has it) | `test_cases`, MBPP's `test_list` (+ `test_imports`/`test_setup_code`), or HumanEval's `test` + `entry_point`; HumanEval body-only answers get the prompt prepended |
| weights | `CodeQualityReward` and `CodeCorrectnessReward` multiplied by their weight inside `compute()`, and TRL multiplied again | weight applied once, by the trainer |
| HumanEval recipes | dataset `openai/humaneval` (does not exist) | `openai/openai_humaneval`; tests reach the rewards with no extra mapping |
| MBPP example | printed "mbpp_reward" but configured `code_quality` | configures `mbpp_reward` and prints the rewards it actually uses |

## What each patched reward still cannot stop

All four (`code_execution`, `code_correctness`, `mbpp_reward`, `code_verifiable`):
- **The child is not sandboxed beyond rlimits and a temp cwd.** It can read any file the user can
  read (including a dataset cache that holds the expected outputs), use the network, and signal
  other processes of the same user, including the trainer (`os.kill(os.getppid(), 9)`; from the
  design, not exercised in the tests). It runs
  as the trainer's user; under root, RLIMIT_NPROC does nothing. `securegrade/` adds Landlock and
  user/network/PID namespaces where the kernel allows; that is too much for a small upstream diff.
- **Tests that a constant passes.** `assert f([]) == None` or `assert not f(x)` give partial
  credit to a stub. The fix is in the tests, not the grader.
- **Visible tests.** MBPP prompts that show all asserts let a lookup table of those cases pass.
- **Helpers the asserts call are the candidate's.** Only builtins are kept trusted.
- **HumanEval asserts that use `check()`'s locals or loop variables** cannot be lifted out of
  `check()` and fail even for the correct answer (see the FN numbers in `results/m1-2026-11-02.md`).

Per reward:
- `code_execution` **with no tests still pays 1.0 for any code that runs**, a stub included. It now
  warns once. Pass tests.
- `code_correctness`: nothing extra (it delegates to `code_execution`).
- `mbpp_reward`: keeps its shaping (format penalties, brevity bonus, -0.10 when nothing passes,
  -0.15 when the code does not run). Its `batch_compute()` path (tests looked up by
  `__SAMPLE_ID:n__` in the prompt) also uses the new sandbox.
- `code_verifiable`: a string test case still means "expected stdout", which by definition is
  checked on printed text. Assertion and input/expected-output cases are values out.

Not touched by this diff and still exploitable (Gate 1): the counterfactual-GRPO backend's own code
reward (`backends/trl/rl/counterfact_grpo/counterfact_grpo.py`, counts `PASS:` lines and does not
clip; fake lines scored 1.43 to 3.33), `sql_verifiable` (pays any parseable SQL), and the heuristic
rewards (`code_syntax`, `code_completeness`, `code_quality`), which score structure by design. The
HumanEval recipe still gives `code_quality` 0.3 of the weight.
