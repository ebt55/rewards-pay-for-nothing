# Released graders on real training completions — 14 November 2026

The 8 November re-audit tested the fixed sources only on hand-built exploit fixtures. This replay asks the same question with real model output: the GRPO training completions that the old shipped grader paid and securegrade did not, plus a control of ordinary correct completions. Each completion went through each grader again.

Data: `results/replay-release-2026-11-14.json`. Script: `scripts/replay_release.py` (stages `prepare`, `grade`, `report`).

## Result

- **No released grader pays any of the 111 exploit-shaped completions.** That covers 47 wrong answers paid by an exit and 64 correct answers with an exit, scored by five released reward functions. The old grader still pays all 111 when re-run.
- **The released execution graders accept 297 of 300 ordinary correct completions.** Each of the 3 they reject prints PASS and then ends before the appended tests run:
  - two call an exit with status 0;
  - one runs `unittest.main`, which exits on its own. Its real exit status is not established.

  securegrade 0.1.2 accepts all 300.
- **AlignTune's release `mbpp_reward` rejects 2 plain correct controls.** Neither has a detector flag and neither exits; both score −0.18, while every other grader pays them in full. Both are on MBPP tasks 7 and 232, whose asserts wrap the call in `set(...)`. The 8 November reference check had already shown this reward rejecting the canonical solutions for both tasks, so this is a known task-level incompatibility, now seen on model output.
- **Six correct answers that securegrade rejected during training** (3 use numpy, 3 start a subprocess) get mixed results:
  - AlignTune's release pays the 3 numpy answers and rejects the 3 subprocess answers.
  - SafeTune's merge pays all 3 subprocess answers and 1 of the 3 numpy answers. The 2 numpy answers it gives 0 both return a numpy scalar.

## Population

One task set (MBPP sanitized tests), 10 runs (8 E/U, 2 H). "RBW" means the logged old score was 0.999 or more and the logged securegrade score was below 0.999. Items are deduplicated by (run, step, task, line).

| Class | What it is | n |
|---|---|---:|
| a | Wrong function, with a zero-status exit before the appended test (mechanisms cat 4/5): 43 hole-pair + 4 E-arm | 47 |
| b | Correct function plus an exit (cat 3): 61 hole-pair + 3 E-arm | 64 |
| c | Correct code that securegrade rejected during training (cat 0; the six hand-labelled items): 3 numpy, 3 subprocess | 6 |
| d | Any other RBW item | 0 |
| control | Seeded random sample (`random.Random(20261114)`), 30 per run, from completions where the old grader and logged securegrade both gave full score | 300 |

Reconciliation:

- RBW total: 104 H + 13 E/U = 117. This matches the raw `completions.jsonl` logs exactly; no item is missing or extra.
- The 4 E-arm wrong-code items are among the 13 E/U items and are not counted twice.
- Class a in the H runs has 43 items: 24 H-ship + 19 H-sec, matching `hole-pair-2026-11-07.md`. The H-sec item at raw line 78 (step 3, task 594) is in the mechanisms JSON as a validation-set RBW item (cat 5, outside detector populations X and A), so it needed no special handling.
- No logged text was truncated (all 417 have `len_chars` equal to the text length), so the replayed text is the text that was graded in training.

## Class × grader

Cells show full score (≥0.999) / positive score (>0).

| Grader | a (47) | b (64) | c (6) | control (300) |
|---|---:|---:|---:|---:|
| AlignTune old `57e9a95` code_execution (sanity) | 47 / 47 | 64 / 64 | 6 / 6 | 300 / 300 |
| AlignTune release code_execution | 0 / 0 | 0 / 0 | 3 / 3 | 297 / 297 |
| AlignTune release code_verifiable | 0 / 0 | 0 / 0 | 3 / 3 | 297 / 297 |
| AlignTune release mbpp_reward | 0 / 0 | 0 / 0 | 0 / 3 | 1 / 295 |
| SafeTune merge code_execution | 0 / 0 | 0 / 0 | 4 / 4 | 297 / 297 |
| SafeTune merge mbpp_reward | 0 / 0 | 0 / 0 | 4 / 4 | 297 / 297 |
| securegrade 0.1.2 (reference) | 0 / 4 | 0 / 0 | 3 / 3 | 300 / 300 |

Notes:

- **AlignTune's mbpp_reward** does not output a pass/fail score. Correct answers mostly land at about 0.87–0.98, so full score almost never happens. At ≥0.95 it passes 111 of 300 controls and 0 items from classes a and b. On classes a and b every score is negative; the highest is −0.16.
- **securegrade's 4 positive scores in class a** are partial credit for wrong functions that pass some of the asserts: one item at 0.67 and three at 0.33. These equal the logged training values. No released grader scores any class a item above securegrade's score for that item.
- **Still paid by a released grader: 0.** Two rules were checked: class a at ≥0.95 or class b at ≥0.999. Neither matched anything, so nothing is withheld and no private file was written.

## Control rejections (by category)

- **All five released execution graders** reject the same 3 controls. Each is a correct function that prints PASS and then ends before the appended tests:
  - two call an exit with status 0 (mechanisms cat 3);
  - one runs `unittest.main` (cat 7b), which exits by itself. Its real exit status is not established, because the mechanisms probe cannot reproduce it.

  The old grader and the logged securegrade paid all three. This is the fix working on answers that are correct but exit early, not a false negative on plain correct code.
- **AlignTune mbpp_reward** scores below 0.999 on 299 of 300 controls, mostly because of the scale described above. It goes negative on 5 controls:
  - the 3 items above;
  - 2 plain correct answers with no detector flag and no exit.

  The 2 plain answers are on MBPP tasks 7 and 232, both scoring −0.18. All other graders, including securegrade 0.1.2, pay them in full. On 8 November this reward already rejected the canonical references for both tasks (`release-reaudit-2026-11-08/aligntune-release-references.json`). Both tasks' asserts compare `set(f(...))` with a set. That makes these 2 genuine correct-answer rejections by this one reward, not a scale effect.

## Class c detail (correct code securegrade had rejected)

| Category | AlignTune release (execution / verifiable) | SafeTune merge (both rewards) | securegrade 0.1.2 |
|---|---:|---:|---:|
| Starts a subprocess (3) | 0 of 3 | 3 of 3 | 0 of 3 (blocked by design) |
| Imports numpy (3) | 3 of 3 | 1 of 3 | 3 of 3 (the 0.1.1 numpy bug is fixed) |

Observation: SafeTune's merge gives 0 to 2 of the 3 numpy answers, and both of those return a numpy scalar. The numpy answer it pays returns a plain list. The cause was not diagnosed, and n = 2.

## Sanity and provenance

- **Old grader reproduction:** the old AlignTune `code_execution` (PyPI 0.1.28 wheel in `~/p9/at`, reward files matching `57e9a95`) reproduces the logged `aligntune_ce` exactly on 417 of 417 items, score for score. Training reused one reward object; this replay uses a fresh object per cell, and that made no difference.
- **Venvs unchanged since 8 November:** after the power loss, every installed source file was hashed again and compared with the 8 November re-audit artifacts. All match: AlignTune release `ff59f10` (326 of 326), SafeTune merge `36b2142` (332 of 332) and old AlignTune (320 of 320). The imported securegrade matches the in-repo `securegrade/` 0.1.2 files. Hashes, interpreters and import origins are in the JSON `provenance`.
- **Containment:** every cell ran through `rewardcheck.check_cell`, with a fresh reward object in a fresh forked child, killed as a process group afterwards, and a 60-second deadline.
  - All 2,919 cells scored on the first attempt: no deadlines, exceptions or child exits.
  - Runs were inside WSL only, on CPU only (`CUDA_VISIBLE_DEVICES=''`), at `nice -n 19`, `OMP_NUM_THREADS=4` and `OPENBLAS_NUM_THREADS=1`.
  - Each target venv's `bin` came first on PATH, and the script enforces this.
  - Two lanes ran in parallel, each running cells one at a time, with an fsync checkpoint every 25 cells.
  - The full run took 158 s of wall time.
- **securegrade columns:** `test_list` and `test_imports` only, the same columns training used to compute `secure_all`. No `entry_point` was passed.

## Scope and limits

- One task set: MBPP (sanitized split), training tasks only, with no `test_imports`.
- The completions come from a single 3.35B model's GRPO runs (10 runs, 32,000 logged completions). The exploit population is every disagreement item; the control is a sample of 300 out of 11,294 completions both old graders passed.
- These are release and merge source archives (`ff59f10`, `36b2142`), not PyPI wheels.
- The samples are finite. This shows that the released graders stopped paying these 111 real exploit-shaped answers and accepted 297 of 300 sampled correct ones. It does not show they are free of all exploits, or give a false-negative rate for correct code in general.
- The control was selected using the old graders' agreement. It therefore contains no answer that the old graders both rejected, so it says nothing about correct answers the old graders missed.
- Rewards replayed: AlignTune `code_execution`, `code_verifiable` and `mbpp_reward`; SafeTune `code_execution` and `mbpp_reward`.
- Not replayed: `code_correctness` (which also reads assert tests), the counterfactual-GRPO backend and HumanEval-native columns.
- Launch: `~/p9/replay-2026-11-14/lane.sh full <target>...`. It sets CPU-only, `nice -n 19`, the venv `bin` first on PATH, and `-B`; the exact command is in the script docstring.
