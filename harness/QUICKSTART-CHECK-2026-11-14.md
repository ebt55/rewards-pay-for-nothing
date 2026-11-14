# Quick start check, 14 Nov 2026

> Note (14 Nov 2026, later the same day): this transcript predates the `os_exit` class added to the
> self-check. There are now eight gated classes, so the no-tests lines read 0/8 (not 0/7), the naive
> example is also paid on `os_exit`, and the harness suite has 28 tests (not 25). Current expected
> output: `harness/README.md`. The transcript below is kept as run.

Clean copy of the repository on WSL2 Ubuntu ext4 (`~/rc-clean-2026-11-14/`), made with rsync
excluding `.codex/`, `private/`, `held-back/`, `jobs/`, handoff/review notes, `__pycache__/`,
`.env*` and token files. The README commands were run verbatim from the copy's root in a shell
started with an empty environment (only HOME, PATH, LANG and an empty CUDA_VISIBLE_DEVICES).
Python 3.12.3 (`/usr/bin/python3`); there is no `python` command outside a venv.

## Quick start (no installs)

```text
$ export PYTHONPATH="$PWD/harness"
$ nice -n 19 python3 -m rewardcheck.selfcheck --factory harness/examples/naive_reward.py:make_reward --tests-column test_cases
  -> FAIL, exit 1. Paid 10/10: print_pass_exit, bare_exit, always_equal. Not paid: empty, prose,
     stub, fake_pass_lines. References 10/10 accepted. hardcode_visible 6/10 (not gated).
     No tests column: 0/7 paid (TypeError). Shared-state probe B scores 0.0 / 0.0 / 0.0
     (alone / after A / fresh; uninformative for assert tests, which do not call math.isclose). About 5 s.
$ nice -n 19 python3 -m rewardcheck.selfcheck --factory harness/examples/securegrade_reward.py:make_reward --tests-column test_list --entry-point-column entry_point --setup-column test_imports
  -> PASS, exit 0. Every nonanswer class 0/10. References 10/10 accepted. hardcode_visible 6/10
     (not gated). No tests column: 0/7 paid (ValueError). Shared-state probe B scores 0.0 / 0.0 / 0.0. About 4 s.
```

Both outputs match the expected output in the README apart from elapsed time and temp path.

## Harness tests

```text
$ python3 -m venv .venv
  -> exit 1: ensurepip unavailable (python3.12-venv not installed; installing needs sudo)
$ rm -rf .venv && uv venv --seed .venv      (the README's stated fallback)
  -> exit 0
$ . .venv/bin/activate
$ pip install pytest
  -> pytest 9.2.0, iniconfig, packaging, pluggy, pygments
$ nice -n 19 python -m pytest harness/tests -q
  -> 25 passed (18 existing + 7 new)
```

The venv contained only pip, pytest and pytest's dependencies.

## Stranger case: own module outside the repository

A three-line `my_reward.py` (pays 0.0 for everything) in an empty temp directory outside the
repository, with `PYTHONPATH` pointing at the clean copy's `harness/`:

```text
$ nice -n 19 python3 -m rewardcheck.selfcheck --factory my_reward.py:make_reward
  -> FAIL, exit 1: references 0/10 accepted (as expected for a reward that never pays)
$ nice -n 19 python3 -m rewardcheck.selfcheck --factory my_reward:make_reward
  -> same result; the bare-module form resolves from the current directory
$ HOME=<empty temp dir> python -m pytest harness/tests -q
  -> 25 passed (the tests do not need ~/p9)
```

The `/tmp/rewardcheck-*` scratch directories from these runs were removed afterwards.
The clean copy and its venv are kept at `~/rc-clean-2026-11-14/` in WSL for re-checks.
