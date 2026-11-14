# patches/

Fixes for the upstream code rewards, written during the audit (1-2 Nov 2026) and measured in `results/m1-2026-11-02.md`.
These are this project's own fixes. The fixes merged upstream (AlignTune PR #40, SafeTune PR #32) are checked
separately in the PR-check reports and in `results/release-reaudit-2026-11-08.md`.

- `aligntune/`: a diff against AlignTune `57e9a95` (MIT), the scripts that built it, and 88 regression tests.
- `safetune/`: prose only (SafeTune is under LSAL, so no SafeTune code is copied) plus tests that call an installed safetune.

Both test folders need their own venv with the target package installed; see each README.
