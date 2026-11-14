# scripts/

The scripts behind every report in `results/`. File names are kept as the reports cite them, so this index groups
them by purpose instead. Most scripts expect WSL2 Ubuntu, the venvs under `~/p9/` described in `notes/INSTALL.md`,
and CPU only (`CUDA_VISIBLE_DEVICES=''`, `nice -n 19`). Several read raw outputs that are not in this repo (see
"Not in this repo" at the end). Dated scripts are kept as run; later reports supersede earlier ones.

## Main entry points

| what | command (from the repo root, inside WSL) | report |
|---|---|---|
| Gate 1 audit of aligntune 0.1.28 / safetune 0.1.10 | `bash scripts/run_all.sh` | `results/gate1-2026-11-01.md` |
| M1: shipped vs patched AlignTune vs securegrade | `bash scripts/run_m1.sh` | `results/m1-2026-11-02.md` |
| Release re-audit of the exact upstream fixes | `release_prepare.py`, then `release_run.py --suite gate1\|references --target <t>`, then `release_report.py` | `results/release-reaudit-2026-11-08.md` |
| Replay of training completions through the released graders | `python scripts/replay_release.py prepare`, `grade --target <t>`, `report` | `results/replay-release-2026-11-14.md` |
| Claim arithmetic from the run logs | `python -I -B scripts/claim_diagnostics.py` | `results/claim-diagnostics-2026-11-08.md` |
| Figures 1-5 and `figures/tables.md` | `bash scripts/figures/make_all.sh` | `figures/README.md` |
| README visuals | `python -B scripts/figures/make_readme_visuals.py` (matplotlib, Pillow) | `figures/readme/README.md` |
| Your own reward (not a script here) | `python3 -m rewardcheck.selfcheck ...` | `harness/README.md` |

## Gate 1 audit (1 Nov 2026)

- `run_all.sh`: runs the whole Gate 1 audit and builds the report.
- `inv.sh`: runs a command inside one of the WSL venvs (`at`, `st`, `at-patched`, `tools`) at low priority, no GPU.
- `install_aligntune.sh`, `install_safetune.sh`, `setup_tools_venv.sh`: create the venvs listed in `notes/INSTALL.md`.
- `fetch_tasks.py`: writes the five benchmark tasks to `exploits/tasks.json`.
- `make_exploits.py`: writes the benign exploit completions to `exploits/exploits.json`.
- `gate1_run.py`: scores every exploit x task x format cell with the installed package's code rewards.
- `recipe_sim.py`: simulates AlignTune's HumanEval GRPO recipe end to end, no model.
- `path_check.py`, `path_check.sh`: checks rewards that launch a bare `python` from PATH.
- `sql_check.py`: what AlignTune's `sql_verifiable` reward pays for.
- `systemexit_check.sh`, `systemexit_trl_driver.py`: does a completion that exits end a TRL GRPO reward step.
- `make_report.py`: builds `results/gate1-2026-11-01.json` and `results/gate1-tables-2026-11-01.md`.
- `github_keyword_scan.py`: keyword scan of dumped upstream issues and PRs (the dumps are not in this repo).
- `versions.py`: prints installed package versions; used by several reports.
- Small one-off helpers, not cited by any report: `probe_import.py` (registry listing and import time),
  `pivot.py` (prints a pivot of a raw Gate 1 file), `check_files.sh` (parse-checks the project's Python files).

## M1: patched AlignTune and securegrade (1-2 Nov 2026)

- `run_m1.sh`: runs all of M1 and builds the report.
- `m1_fn_rate.py`: AlignTune false negatives on all 591 MBPP-sanitized and HumanEval references.
- `m1_securegrade.py`: the Gate 1 matrix graded by securegrade.
- `make_m1_report.py`: builds `results/m1-2026-11-02.json`.
- `rerun_patched_m1.sh`, `rerun_securegrade_m1.sh`, `install_aligntune_patched.sh`: partial re-runs after a fix.

## Upstream PR checks (3 Nov 2026, historical PR heads)

`pr40_*` checked AlignTune PR #40 (head `61d89e4`); `pr32_*` checked SafeTune PR #32 (head `54c80f0`, repeated at
final head `538c833`). Reports:
`results/aligntune-pr40-check-2026-11-03.md`, `results/safetune-pr32-check-2026-11-03.md`. The release re-audit
supersedes them for the merged code.

- `*_common.py`: puts the PR clone first on `sys.path` and checks it loaded.
- `*_gate1.py`, `*_fn_rate.py`, `*_scans.py`: the Gate 1 matrix, reference false negatives and dataset scans on the PR.
- `*_systemexit_check.sh`, `*_systemexit_trl_driver.py`, `pr32_trl.py`, `pr40_crash_driver.py`: run-ending checks under TRL.
- `pr40_recipe.py`, `pr40_baseline_aplus.py`: recipe simulation on the PR and a 0.1.28 baseline for one case.
- `*_tables.py`, `*_report_json.py`: tables and the bundled report JSON.
- `*_probes.sh`: runners for probe scripts that are withheld until the open issues are fixed. Without them they
  stop with exit status 2 and a message; the reports describe the probe classes.

## securegrade checks

- `sg_fn_rate.py`: securegrade on all 591 references plus exploit scores; writes `results/securegrade_fn.json`.
- `sg_smoke.py`: quick smoke test of `securegrade.score` on a few hand cases (not cited by a report).
- `sg_eval_numpy.py`, `sg_np_sub_check.py`, `sg_patch_codec.py`: the numpy/subprocess regrade in
  `results/securegrade-numpy-subprocess-2026-11-03.md`.
- `sg_012_references.py`, `sg_012_report.py`: securegrade 0.1.2 reference check and the report
  `results/memread-2026-11-08.md`. The report step reads `canary.json` (HF dataset); the script that produced it is withheld.

## Training runs and their analysis (2-7 Nov 2026)

The trainer itself is in `jobs/`. These scripts launch runs or summarise their logs (`jobs/runs/<run>/`).

- `runpod_pods.py`, `runpod_wait.py`: create, watch and end RunPod pods for the hole pair (API key read from a file).
- `prepare_hole_pair.py`: builds the hole-pair hint file (`design/HOLE-PAIR-2026-11-04.md`).
- `summarize_8runs.py`, `split_flagged_8runs.py`, `rbw_texts.py`: numbers in `results/grpo-8runs-2026-11-03.md`.
- `summarize_hole_pair.py`, `hole_dossier.py`: numbers and hand-read dossier for `results/hole-pair-2026-11-07.md`.
- `classify_mechanisms.py`: exploit-mechanism classifier (`results/mechanisms-spec-2026-11-07.md`, `results/mechanisms-2026-11-07.md`).
- `claim_diagnostics.py`: offline arithmetic for `results/claim-diagnostics-2026-11-08.md`.

## Release re-audit (8 Nov 2026)

Exact AlignTune tag `ff59f10` and SafeTune merge `36b2142`, plus securegrade 0.1.1. Outputs are in the HF dataset
under `results/release-reaudit-2026-11-08/`.

- `release_prepare.py`: downloads, installs (new venvs, `--no-deps`) and hashes the exact source archives (provenance JSONs).
- `release_run.py`: bounded Gate 1 and reference runs per target.
- `release_native_controls.py`: reference/stub controls for each package's native test columns.
- `release_runtime.py`, `release_interpreter_check.py`: runtime facts and interpreter selection.
- `release_preserve_baseline.py`: snapshot of the tested securegrade 0.1.1 source.
- `release_provenance_compare.py`: compares the upstream fixtures and tests with this repo's fixtures.
- `release_report.py`: checks every artifact is complete, then writes the report JSON and markdown.

## Replay (14 Nov 2026)

- `replay_release.py`: replays the logged exploit-shaped and control completions through the released graders.

## Figures (`figures/`)

`make_all.sh` runs `fig1_audit_heatmap.py` to `fig5_block_reward.py` and `make_tables.py` (shared code in
`_common.py`). `make_article_visuals.py` draws the explanatory article figures in `figures/article-visuals/`.
`make_readme_visuals.py` draws the README visuals in `figures/readme/` (the rewardcheck terminal GIF, the replay
before/after chart and the explainer) from `results/replay-release-2026-11-14.json` and the captured selfcheck output;
it never runs the harness. See `figures/readme/README.md`.

## Not in this repo

- Raw run outputs: `results/raw_*.json`, `results/m1/`, `results/aligntune-pr40/`, `results/safetune-pr32/`,
  `results/path_check.jsonl`, `results/systemexit_trl.txt`, `results/recipe_sim.json`, `results/sql_check.json`,
  `notes/logs/`, `results/github/`. Scripts write them; they are not published. The bundled report JSONs that
  cite them are in the HF dataset.
- Report JSONs (`results/*.json`, `results/release-reaudit-2026-11-08/`, `results/memread-2026-11-08/`): in the
  HF dataset under `results/`. Copy them into `results/` to re-run the report scripts.
- Training logs (`jobs/runs/<run>/`): in the HF dataset under `runs/<run>/`.
- Withheld scripts: the PR probe scripts (`pr32_probes.py`, `pr40_probes.py`, `probe_texts.py`), the release
  re-audit's residual-class runner (`release_residual.py`) and the securegrade 0.1.2 memory canary
  (`memread_canary.py`). They are held back while related upstream issues are open.
- Upstream paths such as `tests/fixtures/code_rewards/exploits.json` refer to files in the AlignTune or SafeTune
  repositories, not here.
