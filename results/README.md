# results/

Dated reports, one per study step, written when each step finished and kept as written. Later reports supersede
earlier ones where they say so: the 3 Nov PR-check reports are historical PR heads, superseded for the merged code by
`release-reaudit-2026-11-08.md`. `CLAIMS.md` at the repo root maps each claim to the report and JSON behind it.

| report | what |
|---|---|
| `gate1-2026-11-01.md`, `gate1-tables-2026-11-01.md` | audit of the code rewards in aligntune 0.1.28 and safetune 0.1.10 |
| `baseline-2026-11-01.md` | Tiny Aya Global on MBPP before training |
| `smoke-2026-11-01.md` | GRPO smoke run on HF Jobs |
| `m1-2026-11-02.md` | shipped vs patched AlignTune vs securegrade |
| `aligntune-pr40-check-2026-11-03.md`, `safetune-pr32-check-2026-11-03.md` | checks of the two upstream fix PRs (historical heads) |
| `securegrade-numpy-subprocess-2026-11-03.md` | securegrade regrade of numpy and subprocess answers |
| `grpo-8runs-2026-11-03.md` | the eight pre-registered GRPO runs (verdict: uninformative) |
| `hole-pair-2026-11-07.md`, `hole-pair-second-read-2026-11-07.md` | the exploratory hole pair and a blind second read |
| `mechanisms-spec-2026-11-07.md`, `mechanisms-2026-11-07.md` | exploit-mechanism classifier spec and results |
| `release-reaudit-2026-11-08.md` | re-audit of the exact released fixes and securegrade 0.1.1 |
| `claim-diagnostics-2026-11-08.md` | offline arithmetic behind dated corrections |
| `memread-2026-11-08.md` | securegrade 0.1.2 hardening evidence |
| `replay-release-2026-11-14.md` | training completions replayed through the released graders |
| `securegrade-013-recheck-2026-11-14.md` | securegrade 0.1.3 (14 Nov review fixes): the replay controls and exit answers re-scored; no cell changed |

The script for each report is named in it and indexed in `scripts/README.md`.

## Not in this repo

- The JSON files the reports cite (`results/*.json`, `results/release-reaudit-2026-11-08/`,
  `results/memread-2026-11-08/`) are in the HF dataset under `results/`. Copy them here to re-run a report script.
- Training logs cited as `jobs/runs/<run>/` are in the HF dataset under `runs/<run>/`.
- Raw intermediate outputs (`raw_*.json`, `m1/`, `aligntune-pr40/`, `safetune-pr32/`, `path_check.jsonl`,
  `systemexit_trl.txt`, `recipe_sim.json`, `sql_check.json`, `github/`) are not published; the bundled JSONs above
  carry their numbers.
- Also cited but not published: the blind spot-check files named in `mechanisms-spec-2026-11-07.md`, the review
  notes cited as the source of the MATS comparison in `claim-diagnostics-2026-11-08.md`, the residual-class runner
  `scripts/release_residual.py` and the external baseline folder named in `release-reaudit-2026-11-08.md`, and the
  withheld probe scripts named in the PR-check reports.
