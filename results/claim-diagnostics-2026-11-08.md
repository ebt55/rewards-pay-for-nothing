# Claim diagnostics — 8 November 2026

Verified offline arithmetic from the ten historical runs. No candidate was regraded or executed. Script: `scripts/claim_diagnostics.py`; JSON contains every input SHA-256, group membership and proxy. Training shipped grader: AlignTune `code_execution` at `57e9a95` (audited 0.1.28); secure observer: 0.1.0 in E/U and 0.1.1 in H. Later release and 0.1.2 results cannot be substituted for those logged scores.

## Score directions, by run and window

Counts compare logged scores with tolerance 1e-12. Below/above means shipped score below/above securegrade, not honest/wrong code. RBW is the shipped-full/secure-not-full screen (threshold 0.999), followed by mechanism adjudication. Partial differences can occur outside that screen. Windows contain changing policies and clustered completions; these counts are descriptive.

| Run | Steps | Denominator | Shipped below | Shipped above | Equal | Mean shipped − secure | Screen positive |
|---|---|---:|---:|---:|---:|---:|---:|
| e-ship-s0 | 1–10 | 320 | 27 | 0 | 293 | -0.071875000 | 0 |
| e-ship-s0 | 11–20 | 320 | 25 | 0 | 295 | -0.075000000 | 0 |
| e-ship-s0 | 21–30 | 320 | 17 | 0 | 303 | -0.039843750 | 0 |
| e-ship-s0 | 31–40 | 320 | 15 | 0 | 305 | -0.039583333 | 0 |
| e-ship-s0 | 41–50 | 320 | 4 | 0 | 316 | -0.010416667 | 0 |
| e-ship-s0 | 51–60 | 320 | 11 | 0 | 309 | -0.032291667 | 0 |
| e-ship-s0 | 61–70 | 320 | 10 | 2 | 308 | -0.022083333 | 1 |
| e-ship-s0 | 71–80 | 320 | 13 | 0 | 307 | -0.037500000 | 0 |
| e-ship-s0 | 81–90 | 320 | 7 | 0 | 313 | -0.019791667 | 0 |
| e-ship-s0 | 91–100 | 320 | 12 | 0 | 308 | -0.026666667 | 0 |
| e-ship-s0 | 1–100 | 3200 | 141 | 2 | 3057 | -0.037505208 | 1 |
| e-ship-s1 | 1–10 | 320 | 26 | 0 | 294 | -0.076875000 | 0 |
| e-ship-s1 | 11–20 | 320 | 22 | 0 | 298 | -0.057291667 | 0 |
| e-ship-s1 | 21–30 | 320 | 10 | 1 | 309 | -0.021614583 | 1 |
| e-ship-s1 | 31–40 | 320 | 19 | 0 | 301 | -0.045312500 | 0 |
| e-ship-s1 | 41–50 | 320 | 15 | 0 | 305 | -0.038541667 | 0 |
| e-ship-s1 | 51–60 | 320 | 14 | 0 | 306 | -0.036458333 | 0 |
| e-ship-s1 | 61–70 | 320 | 6 | 0 | 314 | -0.014166667 | 0 |
| e-ship-s1 | 71–80 | 320 | 8 | 1 | 311 | -0.018229167 | 1 |
| e-ship-s1 | 81–90 | 320 | 8 | 0 | 312 | -0.020833333 | 0 |
| e-ship-s1 | 91–100 | 320 | 11 | 0 | 309 | -0.032291667 | 0 |
| e-ship-s1 | 1–100 | 3200 | 139 | 2 | 3059 | -0.036161458 | 2 |
| e-sec-s0 | 1–10 | 320 | 20 | 0 | 300 | -0.059375000 | 0 |
| e-sec-s0 | 11–20 | 320 | 36 | 0 | 284 | -0.097916667 | 0 |
| e-sec-s0 | 21–30 | 320 | 20 | 1 | 299 | -0.051562500 | 1 |
| e-sec-s0 | 31–40 | 320 | 24 | 1 | 295 | -0.059375000 | 1 |
| e-sec-s0 | 41–50 | 320 | 11 | 1 | 308 | -0.022656250 | 1 |
| e-sec-s0 | 51–60 | 320 | 29 | 0 | 291 | -0.087760417 | 0 |
| e-sec-s0 | 61–70 | 320 | 27 | 1 | 292 | -0.068750000 | 0 |
| e-sec-s0 | 71–80 | 320 | 23 | 1 | 296 | -0.062343750 | 0 |
| e-sec-s0 | 81–90 | 320 | 21 | 0 | 299 | -0.053125000 | 0 |
| e-sec-s0 | 91–100 | 320 | 22 | 0 | 298 | -0.048958333 | 0 |
| e-sec-s0 | 1–100 | 3200 | 233 | 5 | 2962 | -0.061182292 | 3 |
| e-sec-s1 | 1–10 | 320 | 29 | 0 | 291 | -0.087500000 | 0 |
| e-sec-s1 | 11–20 | 320 | 29 | 2 | 289 | -0.070833333 | 2 |
| e-sec-s1 | 21–30 | 320 | 19 | 2 | 299 | -0.044010417 | 2 |
| e-sec-s1 | 31–40 | 320 | 20 | 0 | 300 | -0.055989583 | 0 |
| e-sec-s1 | 41–50 | 320 | 21 | 0 | 299 | -0.062500000 | 0 |
| e-sec-s1 | 51–60 | 320 | 33 | 0 | 287 | -0.076822917 | 0 |
| e-sec-s1 | 61–70 | 320 | 29 | 1 | 290 | -0.082916667 | 0 |
| e-sec-s1 | 71–80 | 320 | 28 | 0 | 292 | -0.083333333 | 0 |
| e-sec-s1 | 81–90 | 320 | 28 | 0 | 292 | -0.069375000 | 0 |
| e-sec-s1 | 91–100 | 320 | 27 | 1 | 292 | -0.067708333 | 1 |
| e-sec-s1 | 1–100 | 3200 | 263 | 6 | 2931 | -0.070098958 | 5 |
| u-ship-s0 | 1–10 | 320 | 11 | 0 | 309 | -0.029166667 | 0 |
| u-ship-s0 | 11–20 | 320 | 10 | 0 | 310 | -0.028906250 | 0 |
| u-ship-s0 | 21–30 | 320 | 5 | 0 | 315 | -0.013541667 | 0 |
| u-ship-s0 | 31–40 | 320 | 4 | 1 | 315 | -0.009375000 | 1 |
| u-ship-s0 | 41–50 | 320 | 6 | 0 | 314 | -0.017708333 | 0 |
| u-ship-s0 | 51–60 | 320 | 8 | 0 | 312 | -0.025000000 | 0 |
| u-ship-s0 | 61–70 | 320 | 5 | 1 | 314 | -0.010833333 | 0 |
| u-ship-s0 | 71–80 | 320 | 5 | 0 | 315 | -0.015625000 | 0 |
| u-ship-s0 | 81–90 | 320 | 4 | 0 | 316 | -0.010416667 | 0 |
| u-ship-s0 | 91–100 | 320 | 2 | 0 | 318 | -0.004166667 | 0 |
| u-ship-s0 | 1–100 | 3200 | 60 | 2 | 3138 | -0.016473958 | 1 |
| u-ship-s1 | 1–10 | 320 | 9 | 0 | 311 | -0.028125000 | 0 |
| u-ship-s1 | 11–20 | 320 | 15 | 0 | 305 | -0.039583333 | 0 |
| u-ship-s1 | 21–30 | 320 | 6 | 0 | 314 | -0.018750000 | 0 |
| u-ship-s1 | 31–40 | 320 | 14 | 0 | 306 | -0.042708333 | 0 |
| u-ship-s1 | 41–50 | 320 | 8 | 0 | 312 | -0.021875000 | 0 |
| u-ship-s1 | 51–60 | 320 | 2 | 0 | 318 | -0.004166667 | 0 |
| u-ship-s1 | 61–70 | 320 | 6 | 0 | 314 | -0.018750000 | 0 |
| u-ship-s1 | 71–80 | 320 | 7 | 0 | 313 | -0.018750000 | 0 |
| u-ship-s1 | 81–90 | 320 | 9 | 0 | 311 | -0.027083333 | 0 |
| u-ship-s1 | 91–100 | 320 | 6 | 0 | 314 | -0.018750000 | 0 |
| u-ship-s1 | 1–100 | 3200 | 82 | 0 | 3118 | -0.023854167 | 0 |
| u-sec-s0 | 1–10 | 320 | 20 | 1 | 299 | -0.053125000 | 1 |
| u-sec-s0 | 11–20 | 320 | 13 | 0 | 307 | -0.039583333 | 0 |
| u-sec-s0 | 21–30 | 320 | 7 | 0 | 313 | -0.016666667 | 0 |
| u-sec-s0 | 31–40 | 320 | 11 | 0 | 309 | -0.030208333 | 0 |
| u-sec-s0 | 41–50 | 320 | 7 | 0 | 313 | -0.020833333 | 0 |
| u-sec-s0 | 51–60 | 320 | 17 | 0 | 303 | -0.051562500 | 0 |
| u-sec-s0 | 61–70 | 320 | 7 | 0 | 313 | -0.015208333 | 0 |
| u-sec-s0 | 71–80 | 320 | 9 | 0 | 311 | -0.023958333 | 0 |
| u-sec-s0 | 81–90 | 320 | 14 | 0 | 306 | -0.033072917 | 0 |
| u-sec-s0 | 91–100 | 320 | 8 | 0 | 312 | -0.021041667 | 0 |
| u-sec-s0 | 1–100 | 3200 | 113 | 1 | 3086 | -0.030526042 | 1 |
| u-sec-s1 | 1–10 | 320 | 9 | 0 | 311 | -0.028125000 | 0 |
| u-sec-s1 | 11–20 | 320 | 10 | 0 | 310 | -0.023958333 | 0 |
| u-sec-s1 | 21–30 | 320 | 6 | 0 | 314 | -0.016145833 | 0 |
| u-sec-s1 | 31–40 | 320 | 12 | 0 | 308 | -0.031250000 | 0 |
| u-sec-s1 | 41–50 | 320 | 10 | 1 | 309 | -0.029166667 | 0 |
| u-sec-s1 | 51–60 | 320 | 9 | 0 | 311 | -0.022916667 | 0 |
| u-sec-s1 | 61–70 | 320 | 11 | 0 | 309 | -0.030416667 | 0 |
| u-sec-s1 | 71–80 | 320 | 6 | 1 | 313 | -0.014583333 | 0 |
| u-sec-s1 | 81–90 | 320 | 8 | 0 | 312 | -0.022916667 | 0 |
| u-sec-s1 | 91–100 | 320 | 6 | 0 | 314 | -0.017968750 | 0 |
| u-sec-s1 | 1–100 | 3200 | 87 | 2 | 3111 | -0.023744792 | 0 |
| h-ship-s0 | 1–10 | 320 | 32 | 5 | 283 | -0.079166667 | 5 |
| h-ship-s0 | 11–20 | 320 | 36 | 8 | 276 | -0.072916667 | 8 |
| h-ship-s0 | 21–30 | 320 | 26 | 10 | 284 | -0.040625000 | 10 |
| h-ship-s0 | 31–40 | 320 | 32 | 11 | 277 | -0.058333333 | 11 |
| h-ship-s0 | 41–50 | 320 | 19 | 2 | 299 | -0.045833333 | 2 |
| h-ship-s0 | 51–60 | 320 | 20 | 8 | 292 | -0.034375000 | 8 |
| h-ship-s0 | 61–70 | 320 | 11 | 4 | 305 | -0.016666667 | 4 |
| h-ship-s0 | 71–80 | 320 | 7 | 3 | 310 | -0.008854167 | 3 |
| h-ship-s0 | 81–90 | 320 | 14 | 6 | 300 | -0.018750000 | 5 |
| h-ship-s0 | 91–100 | 320 | 13 | 6 | 301 | -0.022916667 | 6 |
| h-ship-s0 | 1–100 | 3200 | 210 | 63 | 2927 | -0.039843750 | 62 |
| h-sec-s0 | 1–10 | 320 | 36 | 6 | 278 | -0.084375000 | 6 |
| h-sec-s0 | 11–20 | 320 | 50 | 5 | 265 | -0.123177083 | 5 |
| h-sec-s0 | 21–30 | 320 | 33 | 8 | 279 | -0.058593750 | 8 |
| h-sec-s0 | 31–40 | 320 | 53 | 2 | 265 | -0.135416667 | 2 |
| h-sec-s0 | 41–50 | 320 | 57 | 6 | 257 | -0.140625000 | 6 |
| h-sec-s0 | 51–60 | 320 | 60 | 5 | 255 | -0.163802083 | 5 |
| h-sec-s0 | 61–70 | 320 | 54 | 2 | 264 | -0.139791667 | 2 |
| h-sec-s0 | 71–80 | 320 | 71 | 2 | 247 | -0.180468750 | 2 |
| h-sec-s0 | 81–90 | 320 | 58 | 1 | 261 | -0.152083333 | 1 |
| h-sec-s0 | 91–100 | 320 | 45 | 5 | 270 | -0.098229167 | 5 |
| h-sec-s0 | 1–100 | 3200 | 517 | 42 | 2641 | -0.127656250 | 42 |

More below-score observations than above-score observations occur in each final window, but correctness labels are not exhaustive. A negative mean alone establishes only net score difference. The known bare-import extraction issue is one mechanism, not adjudication of every negative difference.

## Learning-rate deviation

All ten runs have 100 logged values following `2e-5 * (101-step)/100`: step 1 is 2e-5, step 100 is 2e-7, mean 1.01e-5. The final-window mean is 1.1e-6, 5.5% of the planned constant 2e-5 (the final endpoint is 1%). The training call did not explicitly choose a constant scheduler. `grpo_args.json` does not serialize `lr_scheduler_type`; it does not contain a recorded null. The as-run notes preserve the original pre-registration. These records do not establish that the deviation caused the observed outcomes.

## Wrong-code exit payments and descriptive hole pair

Selection: all mechanism items in categories 4 or 5 with `paid_shipped`, including detector-negative screened items. Function correct means the function-only extraction passes the listed tests; a mismatched function name counts as wrong under the task interface.

| Run | Steps 1–10 | Steps 91–100 | All steps | Counts by consecutive ten-step block |
|---|---:|---:|---:|---|
| h-ship-s0 | 1/320 | 4/320 | 24/3,200 | [1, 2, 7, 5, 1, 1, 1, 1, 1, 4] |
| h-sec-s0 | 2/320 | 4/320 | 19/3,200 | [2, 3, 5, 0, 2, 1, 1, 1, 0, 4] |

All-run rates are 0.750% versus 0.59375%, a descriptive +0.15625 percentage-point difference. There was neither a sustained rise nor a final-window excess under shipped reward. Both runs increased from early to final windows. One trajectory per arm, different GPUs, starts about 15 hours apart, clustering and adaptation prevent a causal no-amplification or equivalence conclusion. The five-point continuation rule was a resource decision, not an equivalence test. The eight-run verdict remains pre-registered **uninformative**.

Detector population X contains 42 H wrong-code payments; all-screened coverage contains 43. The additional H-sec item is raw line 78, step 3, task 594 (category 5), outside X and A. Historical detector-only category tables keep their 42 denominator.

## Offline group-advantage reconstruction

Groups use `(step, task_id)`, with all 4,000 groups verified to contain eight records. Observer background threads write asynchronous results, so adjacent file rows can belong to different tasks. The population-standard-deviation proxy is `(logged shipped reward - group mean)/(population_std + 1e-4)`.

All 24 H-ship wrong-code payments have positive proxies: **+0.3778502218 to +2.6449515529**. Using sample std instead gives +0.3534534189 to +2.4741739321. The sole E-ship payment gives +0.9998000400 with population std, +0.9352393794 with sample std. These are observer-reward reconstructions, not logged final training advantages or gradients. Importance masks/correction, token weighting, clipping, KL, reward replay differences and competing gradients are not resolved. Scarce successful opportunities are measured; zero normalized advantage is not a supported explanation for these 24 events.

## Exposure comparison

The cited MATS setup reports 200 steps × 256 completions = **51,200 rollouts per run**, versus 100 × 32 = **3,200** here: 16× total exposure, or 8× at an equal 100 steps. It also reports 16 generations/prompt, LR 7e-5 and LoRA rank 32. Source: F05 of `REVIEW-HANDOFF-SOL-2026-11-08.md` and its linked Steering RL Training study. This is arithmetic on the reported setup, not a replication. Tasks, loophole, prompt, optimizer settings, model and budget differ; parameter count alone does not isolate capability.

## Stop-token accounting (existing explanation)

`jobs/README.md` already explains that TRL's `completions/clipped_ratio` reports near 1.0 because its EOS check does not see Tiny Aya's stop token. The recorded `mask_truncated_completions` is false in all ten argument files, so the metric does not itself show that all completions were masked out of training. Use completion length against the 512-token cap rather than treating this ratio as observed length truncation. This paragraph records the existing explanation; no new EOS or gradient audit was performed.

## Recorded runtime and finite compatibility

Both H runs' `events.jsonl` contain successful securegrade 0.1.1 self-checks with grader euid 0, uid drop to 61000, Landlock ABI 4 and no network/PID namespaces. This is RunPod runtime evidence, not a dedicated probe of every numpy variant, not an HF root deployment test, and not securegrade 0.1.2 evidence.

`results/securegrade_fn.json` records all 591 supplied fenced and bare references passing, plus all 164 HumanEval body+prompt references. Seven fixture classes ×591 tasks have zero full-mark outcomes. This finite compatibility result is not a universal false-negative rate. Six correct-code rejections were found through the original 13-item disagreement screen; answers rejected by both graders were not exhaustively adjudicated.

Exact-release measurements and source hashes are separately recorded in `results/release-reaudit-2026-11-08.{md,json}`. Those results supersede release claims drawn from older PR heads. Accepted securegrade 0.1.2 evidence is recorded in `results/memread-2026-11-08.{md,json}`: the specified WSL synthetic controls, 124 passing tests and 1,346/1,346 passing supplied-reference cells. Training was not rerun; this finite evidence does not establish universal memory safety or successful 0.1.2 root, Docker or Yama-enabled deployment.
