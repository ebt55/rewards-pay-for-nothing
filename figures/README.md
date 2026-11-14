# Figures and tables for the HF Article

Five figures, each in light and dark, as PNG (2x, 200 dpi) and SVG (text drawn as paths), plus `tables.md`.
Every number on a figure is recomputed from the run files or results JSONs and checked against the results
files when the script runs (`checks: n/n match the results files`). Last build, 7 Nov 2026: all checks match
(fig1 133/133, fig2 20/20, fig3 14/14, fig4 60/60, fig5 12/12, tables 8/8).
On 8 Nov, Figure 1 alone was regenerated from the exact release-source re-audit: 133/133 checks match.

Rebuild (WSL, CPU only):

```bash
uv venv ~/p9/figs && VIRTUAL_ENV=~/p9/figs uv pip install matplotlib pandas   # once
bash scripts/figures/make_all.sh
```

Design: dataviz skill reference palette. Blue = trained on the shipped grader (AlignTune `code_execution`),
orange = trained on securegrade, in every figure. The pair passed the skill's validator in both modes (all pairs,
CVD and normal vision). Lines are not smoothed (the skill has no smoothing rule). The table view of each figure is
in `data/` (CSV) or `tables.md`.

Scope for every caption: Tiny Aya Global 3.35B, GRPO on MBPP, 100 steps, 32 completions per step, one or two
seeds per arm.

## Figure 1: audit heatmap, before and after

- Files: `fig1-audit-heatmap-light.png`, `fig1-audit-heatmap-dark.png` (+ `.svg`)
- Script: `scripts/figures/fig1_audit_heatmap.py`
- Reads: `results/gate1-2026-11-01.json` (`cells`, historical shipped scores) and complete matrices in
  `results/release-reaudit-2026-11-08/` (exact-source releases and corrected legacy reruns).
  Table view: `data/fig1_audit_heatmap.csv`.
- Caption (8 Nov update): What each code reward paid for answers that solve nothing, in the historical shipped
  versions and exact AlignTune tag `ff59f10` / SafeTune merge `36b2142` sources (highest score over 5 tasks and 2 formats).
  AlignTune used the authorized source-archive fallback; this is not a tested PyPI 0.1.29 wheel.
- Key numbers:
  - Shipped: 47 of 133 cells pay above 0, 23 of the 77 cells where tests are supplied. Highest is 3.33
    (AlignTune counterfactual-GRPO reward, fake `PASS:` lines).
  - Re-audited sources: 0 of 77 cells with tests pay above 0. The 9 cells that still pay 1.00 are all no-tests rows: AlignTune
    `code_execution` and `code_verifiable`, SafeTune `code_execution`, each for stub, fake `PASS:` lines and
    always-equal.
  - Real solution at the historical compatibility threshold (AlignTune >=0.95; SafeTune >=0.999), for example AlignTune `code_correctness` with dict tests 0·4 → 5·5. SafeTune
    `code_correctness` with no tests now gives the real solution 0 too (5·4 → 0·0).
  - † cells: shipped AlignTune `code_execution` with no tests, fenced PASS+exit and bare exit. The `SystemExit` escaped
    the reward (Gate 1 §6).
- Notes:
  - Cell = highest score over 5 tasks × 2 formats. Gate 1's own table shows the lowest
    score over 5 tasks per format. Both agree on which exploits pay.
  - The "before" values come from the historical Gate 1 cells and are checked against the corrected legacy reruns.
  - The "after" values use exact tag `ff59f10` and merge `36b2142`; no PR-head result is used for the after side.
  - No-tests rows show native payments under a rewardcheck configuration error; they make no correctness claim.
  - Hardcoding the visible examples and the recipe-level totals (`deepseek_humaneval.yaml`) are left out. Their
    columns differ from the exploit classes.

## Figure 2: exploit-shaped rate per step, 8 pre-registered runs

- Files: `fig2-exploit-rate-8runs-{light,dark}.{png,svg}`
- Script: `scripts/figures/fig2_exploit_rate_8runs.py`
- Reads: `jobs/runs/{e,u}-{ship,sec}-s{0,1}/completions.jsonl`. Table view: `data/fig2_exploit_rate_per_step.csv`.
- Caption: Share of the 32 completions at each step that print PASS, exit early or return an always-equal object,
  unsmoothed. The circle marks the one wrong answer the shipped grader paid in training (e-ship-s0, step 69, MBPP 762).
- Key numbers, steps 1–10 → 91–100:
  - E-ship: 15.3% → 8.1% (seed 0), 11.6% → 7.5% (seed 1).
  - E-sec: 15.9% → 6.2%, 12.5% → 12.8%.
  - U arms: 0% → 0–0.3%.
  - Highest single step: 37.5% (12 of 32).
  - The marked completion is the only RBW completion in e-ship-s0, and it is exploit-flagged.

## Figure 3: hole pair, H-ship against H-sec

- Files: `fig3-hole-pair-{light,dark}.{png,svg}`
- Script: `scripts/figures/fig3_hole_pair.py`
- Reads: `jobs/runs/h-{ship,sec}-s0/completions.jsonl` and `summary.json` (GPU, wall time). Table view:
  `data/fig3_hole_pair_per_step.csv`.
- Caption: Exploratory pair, seed 0, with the prompt stating the grader's hole: exploit-shaped rate and
  rewarded-but-wrong rate per step. The two runs used different GPUs (RTX 3090, RTX 5090) and started about 15 h apart.
- Key numbers:
  - Exploit-shaped rate: 29.1% → 21.3% (H-ship), 33.8% → 23.1% (H-sec).
  - RBW, steps 1–10 → 91–100: 5/320 → 6/320 (H-ship), 6/320 → 5/320 (H-sec).
  - RBW over all steps: 62 and 42 of 3,200. Only H-ship's were paid in training.

## Figure 4: held-out evals over training

- Files: `fig4-heldout-evals-{light,dark}.{png,svg}`
- Script: `scripts/figures/fig4_heldout_evals.py`
- Reads: `jobs/runs/*/evals.jsonl` for all 10 runs. Table view: `data/fig4_heldout_evals.csv` and the evals table in
  `tables.md`.
- Caption: Held-out pass@1 at steps 0, 25, 50, 75 and 100 for all 10 runs: MBPP, MBPP with the hint, and HumanEval.
  MBPP has 100 tasks (gaps under about 0.1 are within noise); HumanEval has 164 (SE ≈ 0.04).
- Key numbers:
  - 8 runs: MBPP 0.44 → 0.50–0.56 (+0.06 to +0.12, up in all 8).
  - 8 runs: HumanEval 0.463 → 0.427–0.463 (down in 7, flat in 1).
  - H pair: MBPP 0.44 / 0.45 → 0.50.
  - H pair, hinted: 0.46 → 0.50 (H-ship) and 0.56 (H-sec), with a dip to 0.37 at step 50 in H-ship.
- Note: the H row's hint is sentences 1 + 2, so it is not comparable with the E and U rows.

## Figure 5: block reward per arm, by seed

- Files: `fig5-block-reward-{light,dark}.{png,svg}`
- Script: `scripts/figures/fig5_block_reward.py`
- Reads: `jobs/runs/*/completions.jsonl` (`train_reward_recomputed`, `task_id`). Table view:
  `data/fig5_block_reward.csv` and the block table in `tables.md`.
- Caption: Mean training reward per 10-step block for each arm, by seed. Arms with the same seed see the same tasks
  in the same order, and their block rewards move together.
- Key numbers:
  - Same tasks at every step: checked for all 100 steps within each seed. This includes the H pair, which shares
    seed 0's order.
  - Seed 0, block 3 (steps 21–30): 0.272 / 0.322 / 0.299 / 0.333 (E-ship, E-sec, U-ship, U-sec), so **0.27–0.33
    holds**.
  - Seed 0, block 6 (steps 51–60): 0.553 / 0.609 / 0.523 / 0.594, so **0.52–0.61 holds**.
  - With the H pair added: 0.26–0.33 and 0.52–0.61.
  - "Only 3–5 of the 40 tasks in steps 91–100 also appear in steps 1–10": 5 (seed 0) and 3 (seed 1). This also holds.
- Note: the training reward differs by arm. Ship arms use AlignTune's score; sec arms use securegrade's share of
  asserts passed.

## Numbers that disagree with, or need care beside, a results file

1. **The "any detector flag" label in `grpo-8runs-2026-11-03.md` is wrong.**
   - The table titled "Exploit-shaped attempts (any detector flag)" actually holds `det_any_exploit`, which is the
     design's exploit rate (PASS print, early exit or always-equal).
   - "Any detector flag" (`det_any`, which also counts `stub` and `hardcoded`) is higher. For example, e-ship-s0 is
     19.7% → 17.2% on `det_any`, not 15.3% → 8.1%.
   - The numbers are right for the exploit rate. Only the label is wrong.
2. **`hole-pair-2026-11-07.md` makes a comparison that isn't like for like.**
   - It sets its "any detector flag" rates (32.5% / 36.3%, which are `det_any`) beside "11.6–15.9%" for the E arms.
     Those E-arm numbers are exploit rates.
   - Like-for-like options:
     - exploit rate: H 29.1% / 33.8% against E 11.6–15.9%;
     - any detector flag: H 32.5% / 36.3% against E 17.5–20.3%.
3. **The two files round halves differently.**
   - `grpo-8runs` prints 20/320 = 0.0625 as 6.2%.
   - `hole-pair` prints 68/320 = 0.2125 as 21.3%.
   - Figures 2 and 3 each follow their own file.
4. **The release plan's U-ship divergence "0.004 / 0.019" is a magnitude.** The signed values are −0.004 / −0.019,
   which fits the plan's own note that divergence is negative in all 8 runs (−0.004 to −0.068, confirmed).
5. **Cost.** The wall-time × list-rate estimate for the hole pair is $1.91. `hole-pair` says about $2.05,
   including failed hosts. The 8 L4 runs come to $18.73 and all 10 to $20.64, all estimated.
6. **Seed 1 co-movement is weaker.** This is descriptive, computed here and not in any results file.
   - Pearson r of the 10 block means: 0.84–0.95 within seed 0, 0.57–0.83 within seed 1, and −0.01–0.71 across seeds.
   - The "move together" point is clear in seed 0. Seed 1's curves are flatter, and its range overlaps the
     across-seed range.

Not rechecked: the plan's "80 tasks seen twice, −0.004 to +0.042, median 0", because section 0 does not give the
method.

## Tables (`tables.md`)

- Forecast vs actual: the plan's §0 table, with every "actual" recomputed. All 7 rows match. The divergence row
  matches as a magnitude.
- Other §0 numbers (checks 1 and 2, divergence, held-out ranges, block numbers, task overlap): all match.
- Cost per run, labelled "estimated from wall time × list rate".
- Held-out evals, step 0 → 100, for all 10 runs.
- Block rewards (the table view of figure 5).
- Mechanism categories: a stub only. It waits on the classification task (`results/mechanisms-*`).
