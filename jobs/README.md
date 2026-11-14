# jobs/: GRPO runs on HF Jobs (P9)

> **Historical (added 14 Nov 2026).** This file was written before the training runs and is kept as written. The ten runs did launch and finish; their outputs (`jobs/runs/<run>/` locally) are in the HF dataset under `runs/<run>/`. Results: `results/grpo-8runs-2026-11-03.md` and `results/hole-pair-2026-11-07.md`.

**No real run has been launched.** Design, forecasts and the response to the Fable review are in `design/RUNS-2026-11-02.md` (v2). What has run so far:
- the 1 Nov smoke runs (`results/smoke-2026-11-01.md`);
- the 2-step dry runs of `grpo_train.py` (design §7).

## Files

| file | what |
|---|---|
| `grpo_train.py` | the trainer: AlignTune `create_rl_trainer` (TRL GRPO); arms `shipped` / `secure` (`example` unused); per-call test guards; independent per-completion re-scoring (`completions.jsonl`); evals `mbpp` / `mbpp_hint` / `humaneval` (never fatal); kill rules; local outputs uploaded with `HfApi`; model loaded from a local snapshot; `securegrade.self_check()` at start-up |
| `run_train.sh` | container entry: moves the token from the environment into a 0600 file, installs `requirements-lock.txt` + AlignTune `57e9a95` (`--no-deps`), `exec`s the trainer without the token in its environment |
| `hack_detectors.py` | M3 detectors (plain AST checks) |
| `grader.py` | fallback grader only (blocks PASS/exit, **not** always-equal). The trainer refuses to start without securegrade unless `--allow-fallback-grader` is passed (debug only) |
| `elicitation_text.txt` | **placeholder for Ebin.** Every real run needs it: E arms train on it, and all arms use it for the `mbpp_hint` eval |
| `dryrun_hint.txt` | placeholder string for dry runs only; never use it for a reported run |
| `requirements-lock.txt` | exact environment (frozen from the WSL venv, minus AlignTune and PyICU) |
| `grpo_smoke.py`, `run_smoke.sh`, `runs/` | 1 Nov smoke runs and all dry-run outputs |

## Launch gate (all must hold)

1. `securegrade/` passes its exploit suite, and `self_check()` passes in the container (`events.jsonl → securegrade_self_check`). Its `score()` drops privileges by default (`drop_privileges=True`); the trainer logs `privilege_drop_available` and `running_as_root`.
2. Ebin has replaced `<<EBIN_WRITES_THIS>>` in `elicitation_text.txt` with his own one or two sentences, written from AlignTune's `_run_assertion_test`.
3. Spend so far (job durations × $0.80/h) is under $18. About $0.80 had been spent before the real runs (smoke $0.45, dry runs $0.35).
4. Optional but recommended: pin the image by digest (`docker buildx imagetools inspect ghcr.io/astral-sh/uv:python3.12-bookworm`) and replace the tag below with `ghcr.io/astral-sh/uv@sha256:…`. Every job logs an `IMAGE_FINGERPRINT` line regardless.

## Sync code to the private bucket

Run from `<repo>` (PowerShell, `hf` CLI, logged in as ebt005):

```
hf buckets info ebt005/p9-grpo-smoke                      # must show "private": true
hf buckets sync .\jobs hf://buckets/ebt005/p9-grpo-smoke/jobs --exclude "runs/*" --exclude "__pycache__/*"
hf buckets sync .\securegrade hf://buckets/ebt005/p9-grpo-smoke/securegrade --exclude "__pycache__/*" --exclude "tests/__pycache__/*"
```

**Sync securegrade only when the Gate 1 agent says it is stable.** A sync taken mid-edit once shipped a version that failed to import.

The bucket is mounted **read-only** at `/in`. The trainer writes to `/tmp/run/<run>` in the container and uploads to `runs/<run>/` in the same bucket with `HfApi`: logs every 10 steps, adapters at each eval, everything at the end.

## Final run list and cost (L4 $0.80/h; planning 75 s/step, worst case 120 s/step)

| order | runs | per run | subtotal |
|---|---|---|---|
| 1 | e-ship-s0 + e-sec-s0 (launch in the same minute) | $2.01 ($2.97) | $4.02 |
| 2 | u-ship-s0 + u-sec-s0 | $2.01 ($2.97) | $4.02 |
| 3 | e-ship-s1 + e-sec-s1 | $2.01 ($2.97) | $4.02 |
| 4 | u-ship-s1 + u-sec-s1 | $2.01 ($2.97) | $4.02 |
| **core** | 8 runs | | **$16.08** ($23.76 worst case) |
| conditional | e-ship-s2 + e-sec-s2 | $2.01 | $4.02: **only if Lexsi grants extra credits** |

HF credit left is about $19.4. If the first pair shows 105–120 s/step, switch to the 6-run list: drop u-ship-s1 and u-sec-s1, keeping u-sec-s0 as E-sec's control. Above 120 s/step, also drop u-sec-s0 (design §4).

## Launch commands (do not run until the gate holds)

Every real run uses these flags, identical in all arms:

```
--flavor l4x1 --timeout 4h --secrets HF_TOKEN -v hf://buckets/ebt005/p9-grpo-smoke:/in:ro
```

Every run also passes `--eval-hint-file /in/jobs/elicitation_text.txt`. E runs add `--elicit-file` with the same file.

```
hf jobs run --flavor l4x1 --timeout 4h --secrets HF_TOKEN -v hf://buckets/ebt005/p9-grpo-smoke:/in:ro --name p9-e-ship-s0 -d ghcr.io/astral-sh/uv:python3.12-bookworm bash /in/jobs/run_train.sh e-ship-s0 --arm shipped --seed 0 --steps 100 --eval-hint-file /in/jobs/elicitation_text.txt --elicit-file /in/jobs/elicitation_text.txt
hf jobs run --flavor l4x1 --timeout 4h --secrets HF_TOKEN -v hf://buckets/ebt005/p9-grpo-smoke:/in:ro --name p9-e-sec-s0 -d ghcr.io/astral-sh/uv:python3.12-bookworm bash /in/jobs/run_train.sh e-sec-s0 --arm secure --seed 0 --steps 100 --eval-hint-file /in/jobs/elicitation_text.txt --elicit-file /in/jobs/elicitation_text.txt

hf jobs run --flavor l4x1 --timeout 4h --secrets HF_TOKEN -v hf://buckets/ebt005/p9-grpo-smoke:/in:ro --name p9-u-ship-s0 -d ghcr.io/astral-sh/uv:python3.12-bookworm bash /in/jobs/run_train.sh u-ship-s0 --arm shipped --seed 0 --steps 100 --eval-hint-file /in/jobs/elicitation_text.txt
hf jobs run --flavor l4x1 --timeout 4h --secrets HF_TOKEN -v hf://buckets/ebt005/p9-grpo-smoke:/in:ro --name p9-u-sec-s0 -d ghcr.io/astral-sh/uv:python3.12-bookworm bash /in/jobs/run_train.sh u-sec-s0 --arm secure --seed 0 --steps 100 --eval-hint-file /in/jobs/elicitation_text.txt

hf jobs run --flavor l4x1 --timeout 4h --secrets HF_TOKEN -v hf://buckets/ebt005/p9-grpo-smoke:/in:ro --name p9-e-ship-s1 -d ghcr.io/astral-sh/uv:python3.12-bookworm bash /in/jobs/run_train.sh e-ship-s1 --arm shipped --seed 1 --steps 100 --eval-hint-file /in/jobs/elicitation_text.txt --elicit-file /in/jobs/elicitation_text.txt
hf jobs run --flavor l4x1 --timeout 4h --secrets HF_TOKEN -v hf://buckets/ebt005/p9-grpo-smoke:/in:ro --name p9-e-sec-s1 -d ghcr.io/astral-sh/uv:python3.12-bookworm bash /in/jobs/run_train.sh e-sec-s1 --arm secure --seed 1 --steps 100 --eval-hint-file /in/jobs/elicitation_text.txt --elicit-file /in/jobs/elicitation_text.txt

hf jobs run --flavor l4x1 --timeout 4h --secrets HF_TOKEN -v hf://buckets/ebt005/p9-grpo-smoke:/in:ro --name p9-u-ship-s1 -d ghcr.io/astral-sh/uv:python3.12-bookworm bash /in/jobs/run_train.sh u-ship-s1 --arm shipped --seed 1 --steps 100 --eval-hint-file /in/jobs/elicitation_text.txt
hf jobs run --flavor l4x1 --timeout 4h --secrets HF_TOKEN -v hf://buckets/ebt005/p9-grpo-smoke:/in:ro --name p9-u-sec-s1 -d ghcr.io/astral-sh/uv:python3.12-bookworm bash /in/jobs/run_train.sh u-sec-s1 --arm secure --seed 1 --steps 100 --eval-hint-file /in/jobs/elicitation_text.txt
```

Seed 2 of the E-pair (conditional on extra credits) uses the same two E commands with `s2` and `--seed 2`.

## Watching, stopping, fetching

```
hf jobs ps -a
hf jobs logs <job_id> | Select-String "IMAGE_FINGERPRINT|INSTALL_SECONDS|EVAL|RUN_SUMMARY|Traceback|OutOfMemory"
hf jobs inspect <job_id>
hf jobs cancel <job_id>
hf buckets sync hf://buckets/ebt005/p9-grpo-smoke/runs/<run> .\jobs\runs\<run>
```

- About 10 min after start, `runs/<run>/steps.jsonl` should exist in the bucket. Cancel the job if no step has been logged 15 min after start-up.
- **Uploads, the first real run's check:** the upload fix (dry5-ship found `OfflineModeIsEnabled` blocking the bucket commit) was verified on CPU only. By step 10, `hf buckets list ebt005/p9-grpo-smoke/runs/<run> -R` must show files, and the log must have no `UPLOAD_FAILED` line. If it fails, cancel: training outputs would only exist inside the container.
- Do not quote TRL's `completions/clipped_ratio`. It reads 1.0 because TRL does not see Tiny Aya's stop token; use completion length against the 512 cap instead.
- An `EVAL` line should be in the log by step 25.

**Before reading any result**, check:
- `dataset_after_aligntune.json` shows `n_rows` = 321 in every run;
- `events.jsonl` has `securegrade_self_check` ok, `securegrade_isolation` and `running_as_root`;
- `summary.json` has `global_step` = 100.

## Dry runs (HF Jobs only; never the local GPU)

The local 3080 drives Ebin's display; a local GPU dry run hung the PC on 1 Nov. The post-review verification dry run:

```
hf jobs run --flavor l4x1 --timeout 17m --secrets HF_TOKEN -v hf://buckets/ebt005/p9-grpo-smoke:/in:ro --name p9-dry3-ship -d ghcr.io/astral-sh/uv:python3.12-bookworm bash /in/jobs/run_train.sh dry3-ship --arm shipped --seed 0 --steps 2 --eval-every 2 --eval-mbpp-n 20 --eval-humaneval 10 --eval-hint-file /in/jobs/dryrun_hint.txt --upload-every 1 --max-wall-minutes 14
```

Local checks are CPU only: `CUDA_VISIBLE_DEVICES=""`, `nice -n 19`, `OMP_NUM_THREADS=4`, at most 4 workers.
