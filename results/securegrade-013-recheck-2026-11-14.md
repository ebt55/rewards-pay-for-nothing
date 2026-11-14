# securegrade 0.1.3 replay recheck, 14 Nov 2026

Re-scored with securegrade 0.1.3 (review fixes CODE-01/02/03/06): the 300 controls and the class a/b
items of `results/replay-release-2026-11-14.json`, through `rewardcheck.check_cell` exactly as the
0.1.2 replay did (test_list + test_imports, no entry_point). Raw: `securegrade-013-recheck-2026-11-14.json`.

| class | n | 0.1.2 full | 0.1.3 full | 0.1.2 positive | 0.1.3 positive | 0.1.2 mean | 0.1.3 mean |
|---|---|---|---|---|---|---|---|
| wrong code paid by an exit | 47 | 0 | 0 | 4 | 4 | 0.035461 | 0.035461 |
| correct code plus an exit | 64 | 0 | 0 | 0 | 0 | 0.0 | 0.0 |
| control: both old graders full score | 300 | 300 | 300 | 300 | 300 | 1.0 | 1.0 |

Cells whose status or score changed: **0** of 411.

Runtime: Python 3.12.3, kernel 5.15.167.4-microsoft-standard-WSL2, nice 19, CUDA_VISIBLE_DEVICES empty, 20.4 s.
