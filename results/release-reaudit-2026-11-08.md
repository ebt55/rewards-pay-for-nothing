# Exact-source release re-audit — 8 November 2026

Verified observations on the source bytes, fixtures and WSL runtime below. The 3 November PR-head reports remain historical. This re-audit does not test a PyPI AlignTune 0.1.29 wheel.

## Source and runtime provenance

| Target | Exact source | Observed distribution metadata | Installed Python files matching source |
|---|---|---|---:|
| aligntune | `ff59f10f06b74b7529338d06cf513e48e0cb020a` | 0.1.10 | 326 |
| safetune | `36b2142c96e64aea3059966921b2815cf445629b` | 0.1.8 | 332 |

AlignTune 0.1.29 was unavailable from PyPI (HTTP 404), so the authorized exact-tag source archive was installed. `wheel_sha256` is null because no PyPI wheel was tested. SafeTune was installed from the authorized exact merge archive. Both active imports resolve under their new venvs, and every installed target Python file matches that archive byte for byte.

| Source archive | SHA-256 |
|---|---|
| aligntune | `d021eb9a98325a267d21664ec553ae1e049d61fc5fcafb19738598740a9c0507` |
| safetune | `a17fa765e9a305e771b48a93283b41060335d6322b89f1af5878376530f23419` |

The new venvs reuse existing dependency installations without installing/removing baseline packages; exact target packages live in the new venvs. Full versions and dependency requirement/resolution edges are in the provenance JSONs. AlignTune retains the historical baseline's missing `PyICU>=2.10` dependency override; the reward paths exercised here run without it. SafeTune has no unmet active dependency requirements in this environment. These are reward-path checks, not a clean-room full-package installation certification.

Runtime: WSL2 Ubuntu, kernel `5.15.167.4-microsoft-standard-WSL2`, x86-64, uid/gid 1000, no exposed Yama `ptrace_scope`. CPU only (`CUDA_VISIBLE_DEVICES=''`), nice 19, OMP 4, OpenBLAS 1. Cells run serially, each in a new process group with a fresh reward object and 30-second deadline. Harness invocations have a 1,800-second budget plus a 60-second outer allowance, with checkpoint/liveness updates. This is process containment for the supplied fixtures, not a general hostile-code sandbox guarantee.

Every run records actual package import origin, Python/kernel, runtime controls, and package/harness/fixture SHA-256 hashes. `runtime.json` and per-invocation runtime files add the selected interpreter facts. Fixture files are the existing `exploits/exploits.json`, `tasks.json` and cached `tasks_all.json`; no new dataset was downloaded.

## Existing exploit fixtures and no-tests behavior

Five tasks × nine existing completion classes × fenced/bare formats. The functional nonanswer subset contains seven `solves_nothing` classes. Heuristic reward rows are labelled separately and make no correctness claim.

| Exact source | Functional nonanswer cells with tests | Positive scores |
|---|---:|---:|
| aligntune-release | 490 | 0 |
| safetune-merge | 280 | 0 |
| securegrade-011 | 70 | 0 |

Missing and empty tests are `configuration_error` in rewardcheck, independently of the package's native payment. Native observations are retained for auditing: AlignTune `code_execution` / `code_verifiable` and SafeTune `code_execution` can still pay a stub without tests. A score without supplied tests is not evidence of task correctness. This release limitation is also documented by the upstream AlignTune regression test.

Cross-completion checks compare wrong completion B alone, A then B on one shared object, and B on a fresh isolated object. The release/merge checks leave B at zero; the legacy AlignTune check exposes the recorded state carry-over. Exact sequence scores are in the JSON.

Bare-import compatibility is path-specific: all five references in both formats pass the registered AlignTune functional rewards at >=0.95. The counterfactual-GRPO backend still rejects bare `HumanEval/2` (-0.1): 5/5 fenced and 4/5 bare canaries reach >=0.95, matching the historical PR-head pattern. SafeTune `code_execution[dicts]` accepts 8/10 canary format cells; its positional/list input contract is separate from assert-test compatibility.

## Supplied memory-read class (payload withheld)

The same existing private probe was executed only in bounded WSL children. Public artifacts retain class-level scores and hashes, not payload text or candidate output. The harness's public memory-read slot remains empty. These private checks use assert-test inputs: `test_cases` for execution/correctness/AlignTune MBPP and `reference` for AlignTune verifiable. HumanEval here uses the five-task fixture's lifted assertions; native HumanEval memory-read behavior is not separately established.

| Tested source | Reward/task cells | Positive scores | >=0.95 |
|---|---:|---:|---:|
| aligntune-residual | 20 | 0 | 0 |
| aligntune-premerge-control | 20 | 20 | 20 |

AlignTune's exact release source prevents payment for this supplied class on these five tasks, while the same probe obtains high scores on audited premerge head `61d89e4d8ce0be942c7aaea1153c0abf7da31db3`; the paired correct references remain accepted. This supersedes a claim that the PR-head memory result necessarily applies to the release. It does not establish universal memory isolation or identify an explicit denial mechanism: paired syscall/canary controls belong to the separate securegrade hardening work. One further result is withheld pending private disclosure.

## Correct-reference compatibility

All 591 supplied tasks are covered: 427 MBPP-sanitized and 164 HumanEval, in fenced and bare full-reference formats. Registered rewards follow the existing PR reference-check integration. HumanEval native columns include the trusted raw prompt; lifted assertions are reported separately because loops/helpers can lose context. The raw run mode `lifted` denotes assert-list input: MBPP uses its original assert list, while HumanEval assertions are lifted. `code_correctness[dicts]` covers only tasks expressible in the historical input/expected-output format. The backend above has five-task canary evidence, not a 591-task claim.

SafeTune's exact merge consumes `test_cases`/`test_list`, not native HumanEval `test` + `entry_point` + `prompt` columns. Its native-row scores are therefore retained only as unconfigured raw observations, excluded from functional compatibility counts and marked configuration errors. In particular, an execution-only reward can pay both a correct reference and a stub. One-task reference/stub controls confirm the wiring for both exact targets; see the native-control artifacts. SafeTune's assessed HumanEval compatibility here uses lifted assert inputs, with their stated limitations.

Full score means >=0.999. >=0.95 is a separate historical compatibility marker; for example an MBPP score of 0.98 satisfies the latter, not the former. These are finite supplied-reference results, not a universal false-negative rate.

| Target / reward / population / path / format | n | >=0.999 | >=0.95 |
|---|---:|---:|---:|
| aligntune-release / code_correctness[asserts] / humaneval / lifted / bare | 164 | 155 | 155 |
| aligntune-release / code_correctness[asserts] / humaneval / lifted / fenced | 164 | 155 | 155 |
| aligntune-release / code_correctness[asserts] / humaneval / native / bare | 164 | 164 | 164 |
| aligntune-release / code_correctness[asserts] / humaneval / native / fenced | 164 | 164 | 164 |
| aligntune-release / code_correctness[asserts] / mbpp / lifted / bare | 427 | 421 | 421 |
| aligntune-release / code_correctness[asserts] / mbpp / lifted / fenced | 427 | 421 | 421 |
| aligntune-release / code_correctness[dicts] / humaneval / lifted / bare | 97 | 96 | 96 |
| aligntune-release / code_correctness[dicts] / humaneval / lifted / fenced | 97 | 96 | 96 |
| aligntune-release / code_correctness[dicts] / mbpp / lifted / bare | 277 | 267 | 267 |
| aligntune-release / code_correctness[dicts] / mbpp / lifted / fenced | 277 | 267 | 267 |
| aligntune-release / code_execution / humaneval / lifted / bare | 164 | 155 | 155 |
| aligntune-release / code_execution / humaneval / lifted / fenced | 164 | 155 | 155 |
| aligntune-release / code_execution / humaneval / native / bare | 164 | 164 | 164 |
| aligntune-release / code_execution / humaneval / native / fenced | 164 | 164 | 164 |
| aligntune-release / code_execution / mbpp / lifted / bare | 427 | 421 | 421 |
| aligntune-release / code_execution / mbpp / lifted / fenced | 427 | 421 | 421 |
| aligntune-release / code_verifiable / humaneval / lifted / bare | 164 | 155 | 155 |
| aligntune-release / code_verifiable / humaneval / lifted / fenced | 164 | 155 | 155 |
| aligntune-release / code_verifiable / humaneval / native / bare | 164 | 164 | 164 |
| aligntune-release / code_verifiable / humaneval / native / fenced | 164 | 164 | 164 |
| aligntune-release / code_verifiable / mbpp / lifted / bare | 427 | 421 | 421 |
| aligntune-release / code_verifiable / mbpp / lifted / fenced | 427 | 421 | 421 |
| aligntune-release / mbpp_reward / humaneval / lifted / bare | 164 | 124 | 152 |
| aligntune-release / mbpp_reward / humaneval / lifted / fenced | 164 | 0 | 149 |
| aligntune-release / mbpp_reward / humaneval / native / bare | 164 | 128 | 156 |
| aligntune-release / mbpp_reward / humaneval / native / fenced | 164 | 0 | 153 |
| aligntune-release / mbpp_reward / mbpp / lifted / bare | 427 | 415 | 415 |
| aligntune-release / mbpp_reward / mbpp / lifted / fenced | 427 | 96 | 415 |
| safetune-merge / code_correctness / humaneval / lifted / bare | 164 | 155 | 155 |
| safetune-merge / code_correctness / humaneval / lifted / fenced | 164 | 155 | 155 |
| safetune-merge / code_correctness / humaneval / native / bare | 164 | not assessed | unsupported columns |
| safetune-merge / code_correctness / humaneval / native / fenced | 164 | not assessed | unsupported columns |
| safetune-merge / code_correctness / mbpp / lifted / bare | 427 | 421 | 421 |
| safetune-merge / code_correctness / mbpp / lifted / fenced | 427 | 421 | 421 |
| safetune-merge / code_execution / humaneval / lifted / bare | 164 | 155 | 155 |
| safetune-merge / code_execution / humaneval / lifted / fenced | 164 | 155 | 155 |
| safetune-merge / code_execution / humaneval / native / bare | 164 | not assessed | unsupported columns |
| safetune-merge / code_execution / humaneval / native / fenced | 164 | not assessed | unsupported columns |
| safetune-merge / code_execution / mbpp / lifted / bare | 427 | 421 | 421 |
| safetune-merge / code_execution / mbpp / lifted / fenced | 427 | 421 | 421 |
| safetune-merge / mbpp_reward / humaneval / lifted / bare | 164 | 155 | 155 |
| safetune-merge / mbpp_reward / humaneval / lifted / fenced | 164 | 155 | 155 |
| safetune-merge / mbpp_reward / humaneval / native / bare | 164 | not assessed | unsupported columns |
| safetune-merge / mbpp_reward / humaneval / native / fenced | 164 | not assessed | unsupported columns |
| safetune-merge / mbpp_reward / mbpp / lifted / bare | 427 | 421 | 421 |
| safetune-merge / mbpp_reward / mbpp / lifted / fenced | 427 | 421 | 421 |
| securegrade-011 / secure_code_reward / humaneval / native / bare | 164 | 164 | 164 |
| securegrade-011 / secure_code_reward / humaneval / native / fenced | 164 | 164 | 164 |
| securegrade-011 / secure_code_reward / mbpp / native / bare | 427 | 427 | 427 |
| securegrade-011 / secure_code_reward / mbpp / native / fenced | 427 | 427 | 427 |

Below-threshold task IDs, scores and containment outcomes are listed in the JSON; a low score on a supplied reference is a compatibility observation, not a claim that the reference is wrong.

## Historical reproduction and upstream fixture provenance

| Legacy target | Cells comparable with historical Gate 1 | Mismatches |
|---|---:|---:|
| aligntune-legacy | 1350 | 0 |
| safetune-legacy | 900 | 0 |

The first legacy diagnostic invocation omitted venv/bin from PATH, so legacy code that launches literal `python` could not execute its subprocess. Those files were superseded by reruns with venv/bin prepended; their hashes and the setup correction are retained in the final legacy runtime manifests. Only corrected reruns enter this report and Figure 1.

The AlignTune release's `tests/fixtures/code_rewards/exploits.json` is semantically identical to this project's fixture (nine entries, eight templates, seven special sequences); its task fixture is also semantically identical. Its security test module explicitly states that it was adapted from the author's private 2 November report and names the author/MIT. The tests exercise the same nonanswer, exit, spoofed-output and cross-completion classes, then add integration/confinement and other regression checks. This directly establishes matching fixture content and an explicit adaptation statement; it does not justify speculation about further provenance or intent. The exact SafeTune merge archive contains neither of those corresponding fixture/security-test files. No SafeTune source was copied into this MIT project.

Upstream source: [AlignTune fixture](https://github.com/Lexsi-Labs/aligntune/blob/ff59f10f06b74b7529338d06cf513e48e0cb020a/tests/fixtures/code_rewards/exploits.json), [AlignTune security tests](https://github.com/Lexsi-Labs/aligntune/blob/ff59f10f06b74b7529338d06cf513e48e0cb020a/tests/test_code_reward_security.py), [SafeTune exact merge](https://github.com/Lexsi-Labs/SafeTune/tree/36b2142c96e64aea3059966921b2815cf445629b). Content comparison hashes and test names are in `upstream-fixture-comparison.json`.

## Reproduction and limits

See `harness/README.md` for the five-minute quick start. `scripts/release_prepare.py` prepares provenance; `scripts/release_run.py` runs bounded Gate 1/reference checks; `scripts/release_report.py` rejects incomplete/incorrect-count artifacts before summarizing. `scripts/figures/fig1_audit_heatmap.py` reads the exact-source matrices for the after side. Private residual checks use existing local probes in `scripts/release_residual.py`; no payload is added to the public harness.

The exact tested securegrade 0.1.1 MIT source is preserved externally at `~/p9/build-release-sol/baselines/securegrade-0.1.1/securegrade/`, with a source-hash manifest matched to both completed baseline runs. The manifest is also recorded in `securegrade-011-source-snapshot.json`. The driver refuses a non-0.1.1 canonical source before writing artifacts under the `securegrade-011` label. Later hardening must retain these immutable baseline observations; reconstruction uses the snapshot in an isolated copy of the audit repository.

No GPU, cloud job, paid compute, publication, upload, maintainer contact, commit or push occurred. Existing historical reports and article prose are outside this report's edits. Docker, Yama-enabled kernels, root deployments and arbitrary candidate programs remain unverified here. The dependency reuse, source fallback and finite fixture denominators limit the claims.
