# securegrade 0.1.2 and 0.1.3 on every logged training answer, 14 Nov 2026

**Why.** The external review (CODE-01) found that securegrade before 0.1.3 could give 1.0 to a loop test
that passed once and then crashed, exited or hung. Training used 0.1.0 (core runs) and 0.1.1 (H pair) as
the secure arms' reward and as every run's `secure_all` observer. This re-scores all of them.

**Scope.** All 32,000 logged answers of the 10 runs (`jobs/runs/*/completions.jsonl`), MBPP sanitized
`test_list`, the same call as training's `secure_all` (`securegrade.score(text, test_list, setup_code="")`).
Script: `scripts/sg_013_training_rescore.py`. Raw: `securegrade-training-rescore-2026-11-14.json`
(ids and scores only, no answer text). WSL, CPU only, nice 19, 4 workers, about 9 minutes per version.

## Result

| | Answers | Full score (≥ 0.999) |
|---|---:|---:|
| Logged in training (0.1.0 / 0.1.1; HF Jobs for the core runs, RunPod for the H pair) | 32,000 | 12,700 |
| securegrade 0.1.2 (WSL) | 32,000 | 12,703 |
| securegrade 0.1.3 (WSL) | 32,000 | 12,703 |

- **No training answer was overpaid.** Every answer with full marks in training keeps full marks under
  0.1.3 (0 of 12,700 lose it), and no answer scores lower under 0.1.3 than it did in training. The loop-test
  bug and the other 0.1.3 fixes changed no training score.
- **0.1.2 vs 0.1.3: 2 differences, both noise.** Both answers call `random`. Re-scored twice more per
  version, they moved within one version (h-ship-s0:238 gave 0.33, 0.67, 0.33 under 0.1.2; e-sec-s1:2537
  gave 0.33, 0.0, 0.0 under 0.1.3).
- **Logged vs 0.1.3: 5 differences, all scored higher now.** Four import `numpy` (u-ship-s0:1098,
  u-sec-s0:273, e-ship-s1:2385, u-sec-s1:1341). They scored 0.0 when logged in training (core runs, securegrade 0.1.0 on HF Jobs) and pass here.
  Three of them are among the six hand-labelled numpy items already in `scripts/replay_release.py`
  (`SIX_FN`). The fifth is the `random` answer e-sec-s1:2537 above. One of the four (u-sec-s0:273, a
  securegrade arm) is correct code that the training reward paid 0.0: the error ran against the model, not
  for it.
- 0 scoring errors in 64,000 calls.

## What this means for the write-up

The securegrade bugs fixed in 0.1.3 did not touch any training reward or `secure_all` value, so the
training analysis and the rewarded-but-wrong population stand as published.
