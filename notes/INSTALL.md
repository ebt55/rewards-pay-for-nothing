# Install notes (Gate 1, 1 Nov 2026)

Everything runs in WSL2 Ubuntu 24.04 (glibc 2.39, kernel 5.15.167.4-microsoft), a non-root user,
Python 3.12.3, uv 0.11.16. No GPU was used (`CUDA_VISIBLE_DEVICES=""` everywhere). No model was downloaded.

## Virtualenvs (WSL home, not /mnt/c)

| venv | contents | how |
|---|---|---|
| `~/p9/at` | aligntune **0.1.28** + full dependency tree **minus PyICU** (272 packages: trl 1.7.1, vllm 0.22.1, torch 2.11.0, transformers 5.22.1, curatorkit 0.1.22, datasets 5.1.0) | `scripts/install_aligntune.sh` |
| `~/p9/st` | safetune **0.1.10** + full dependency tree (trl 1.14.2, torch 2.15.0, transformers 5.22.1) | `scripts/install_safetune.sh` |
| `~/p9/tools` | `datasets` only, used once to fetch the 5 tasks | `scripts/setup_tools_venv.sh` |

Wheel hashes (downloaded from files.pythonhosted.org, 1 Nov 2026):

- `aligntune-0.1.28-py3-none-any.whl` sha256 `a5ea661b228338f7a0ab0a467be93ac24c7c7461d30f9f76d42e7b5a9bea90bc` (uploaded 2026-10-07)
- `safetune-0.1.10-py3-none-any.whl` sha256 `973a720cc5a2274de9da2132920762eddf05f32f07ad087645e67aeae7f6118a` (uploaded 2026-10-21)

These are the latest versions on PyPI as of 1 Nov 2026.

## What went wrong and what I did

1. **aligntune, plain install failed.** `uv pip install aligntune==0.1.28` stopped on building
   `pyicu==2.17` (sdist only; needs `pkg-config` and ICU headers, `libicu-dev`). There is no
   passwordless sudo in this WSL, so I could not apt-install them. Log: `notes/logs/at_install.log`.
   AlignTune issue #37 (open, 25 Oct) reports that core install pulls PyICU, vLLM, etc.
2. **aligntune, second attempt worked.** Same command plus `--override notes/overrides-no-pyicu.txt`,
   an override whose marker is never true, so uv resolves and installs the complete dependency tree
   except PyICU. This is *not* `--no-deps`: vLLM, trl[vllm]==1.7.1 and everything else are installed.
   Log: `notes/logs/at_install2.log`.
   PyICU is imported only by `aligntune/core/tokenization/vocab/continued_bpe.py` and the bundled
   `tokenizer_extension/` package, neither of which the reward or GRPO code paths import.
3. **safetune** installed cleanly. Log: `notes/logs/st_install.log`.

## Things worth knowing about the wheels

- The aligntune wheel ships four extra top-level packages besides `aligntune`: `unsloth`,
  `unsloth_zoo`, `mergekit`, `tokenizer_extension`.
- `import aligntune.rewards.registry` takes ~21 s and imports vLLM. On import,
  `aligntune.core.rl.registries` tries to build the `rubric` reward and logs a warning that no
  `OPENAI_API_KEY` is set.
- Several rewards launch tests with `subprocess.run(['python', file])` (bare name). Stock Ubuntu
  24.04 has no `python`, only `python3`, so the venv must be **activated** (its `bin/` on PATH).
  `scripts/inv.sh` does this. `results/path_check.jsonl` shows the effect of not doing it.
- GitHub `main` matches the wheels for every file audited: aligntune main `57e9a95` (7 Oct) vs wheel
  for `rewards/core.py`, `rewards/verifiable.py`, `rewards/registry.py`, `core/rl/reward_handler.py`,
  `recipes/configs/grpo/deepseek_humaneval.yaml` (all identical); SafeTune main `26f59e6` (21 Oct)
  vs wheel for `rewards/code.py` (identical). The example `examples/grpo_code_gen_trl_mbpp.py` is
  not in the wheel; it was read from GitHub main.

## Running

```bash
# inside WSL (wsl -d Ubuntu), after the three venvs exist:
bash scripts/run_all.sh
```

That regenerates `exploits/exploits.json`, both raw result files, the recipe simulation, the
SystemExit / PATH / SQL checks, `results/gate1-2026-11-01.json`, `results/gate1-tables-2026-11-01.md`,
and runs `tests/test_gate1.py` (pytest). About 5 minutes. Needs network only for the recipe
simulation (Hugging Face datasets). Rewards' own temp files go to `~/p9/tmp`, never into this folder.

## Why plain pytest and not rewardlint

`rewardlint` 0.1.0 exists on PyPI (Apache-2.0, uploaded by its author on 3 Oct 2026). Its corpus and call
conventions target string-answer verifiers (`f(completion, reference)`, math-style answers such as
negation and "shotgun" lists). It has no code-execution corpus and no way to pass test cases, so
using it here would have meant writing the whole exploit corpus anyway. I did not install or run it.
