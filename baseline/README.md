# baseline/

Base-model measurements taken before training (1 Nov 2026), reported in `results/baseline-2026-11-01.md`.

- `run_baseline.py`, `grader.py`, `summarize.py`: greedy and sampled MBPP pass rates for Tiny Aya Global.
- `inspect_prompt.py`: the exact prompt AlignTune's MBPP recipe hands to TRL.
- `regrade_alias.py`: diagnostic re-grade for answers that only got the function name wrong.
- `detector_calibration.py`: calibration of the exploit detectors in `jobs/hack_detectors.py`.

Their JSON outputs are not in this repo; `results/baseline-2026-11-01.json` is in the HF dataset.
