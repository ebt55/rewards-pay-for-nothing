# tests/

`test_gate1.py` asserts the Gate 1 behaviour of the audited wheels (aligntune 0.1.28, safetune 0.1.10).
It is a historical regression test: it needs those wheels installed (`notes/INSTALL.md`) and
`results/gate1-2026-11-01.json`, which is in the HF dataset, copied into `results/`. Without that file it fails
at collection. The tests that run from a plain checkout are `harness/tests` and `securegrade/tests`.
