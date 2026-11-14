"""Assemble the new dated C report from completed, local verification artifacts."""
import argparse
import hashlib
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "memread-2026-11-08"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-log", required=True, type=pathlib.Path)
    args = parser.parse_args()
    canary = json.loads((OUT / "canary.json").read_text())
    references = json.loads((OUT / "references-012.json").read_text())
    log = args.pytest_log.read_text()
    check = re.search(r"(\d+) passed in ([\d.]+)s", log)
    if not check or "FAILED" in log or "ERROR" in log:
        raise SystemExit("a passing full pytest log is required")
    if not canary["all_controls_passed"] or references["rejected_reference_cells"]:
        raise SystemExit("required control/reference verification failed")
    if references["observed_historical_score_changes"] or references["observed_011_score_changes"]:
        raise SystemExit("observed reference score change requires review")
    shutil.copyfile(args.pytest_log, OUT / "pytest-full.log")
    files = sorted((ROOT / "securegrade").glob("*.py")) + sorted((ROOT / "securegrade" / "tests").glob("*.py"))
    files += [ROOT / "securegrade" / "README.md", ROOT / "securegrade" / "CHANGELOG.md"]
    files += sorted((ROOT / "scripts").glob("memread_*.py")) + sorted((ROOT / "scripts").glob("sg_012_*.py"))
    # The upstream note is a private draft, not part of the public repo; hash it only when present.
    files += [p for p in [ROOT / "private" / "memread-upstream-note.md"] if p.exists()]
    result = {
        "date": "2026-11-08", "version": "0.1.2", "evidence_label": "verified on the specified non-root WSL runtime",
        "runtime": canary["runtime"], "matrix": canary["rows"],
        "interpreters": {"reference_and_canary": {"path": sys.executable,
                         "resolved_path": str(pathlib.Path(sys.executable).resolve()),
                         "version": sys.version.split()[0], "executable_sha256": digest(pathlib.Path(sys.executable))},
                         "pytest": {"path": str(pathlib.Path.home() / "p9/at-0129/bin/python"),
                         "resolved_path": str((pathlib.Path.home() / "p9/at-0129/bin/python").resolve()),
                         "executable_sha256": digest((pathlib.Path.home() / "p9/at-0129/bin/python"))}},
        "default_required_controls": ["parent_nondumpable", "no_new_privs", "rlimits", "landlock"],
        "verified_isolation_seen": list({json.dumps(row["isolation"], sort_keys=True): row["isolation"]
                                         for row in references["rows"]}.values()),
        "pytest": {"passed": int(check.group(1)), "seconds": float(check.group(2)),
                   "interpreter": str(pathlib.Path.home() / "p9/at-0129/bin/python"), "program_timeout_s": 1200},
        "references": {key: references[key] for key in (
            "tasks", "reference_cells", "rejected_reference_cells", "observed_historical_score_changes",
            "observed_011_score_changes", "historical_comparison", "frozen_011_comparison", "fixture_sha256", "seconds")},
        "execution": {"candidate_platform": "WSL child processes only", "nice": 19,
                      "cuda_visible_devices": "", "omp_num_threads": 4, "openblas_num_threads": 1,
                      "reference_workers": 2, "maximum_test_workers": 4},
        "scope_limits": ["Yama, Docker and root deployments of 0.1.2 untested",
                         "591 supplied references do not establish universal correct-answer coverage",
                         "Historical training used 0.1.0/core and 0.1.1/H, not 0.1.2",
                         "No static pipe or fixed hash-seed availability hardening in this change",
                         "No real grading data scanned or extracted by the paired controls"],
        "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in files},
        "artifacts_sha256": {str(p.relative_to(ROOT)): digest(p) for p in (
            OUT / "canary.json", OUT / "references-012.json", OUT / "pytest-full.log")},
    }
    (ROOT / "results" / "memread-2026-11-08.json").write_text(json.dumps(result, indent=2) + "\n")
    table = ["| Landlock | Parent dumpable | API | Matched | errno | Observation |",
             "|---|---|---|---|---|---|"]
    for row in canary["rows"]:
        table.append(f"| {'on' if row['landlock'] else 'off'} | {int(row['dumpable'])} | {row['api']} | "
                     f"{row['matched']} | {row['errno']} | {row.get('error') or 'known canary read'} |")
    markdown = f"""# securegrade 0.1.2: parent memory protection and fail-closed setup

Verified observations on 8 November 2026: WSL2 `{canary['runtime']['kernel']}`, uid
{canary['runtime']['uid']}, Yama ptrace-scope interface `{canary['runtime']['yama_ptrace_scope']}`.
No GPU, installs, network, training reruns, publication or external contact were used for C.

## What changed

The parent sets and checks `PR_SET_DUMPABLE=0` once per process PID, before any child or
namespace probe. Thread/fork-safe initialization never restores or toggles production
dumpability; later drift is a configuration error. This permanent caller-process state
change is documented in `securegrade/README.md`.

Default requirements are parent nondumpability, no-new-privileges, all six resource limits,
and Landlock. Required network/PID namespaces and uid drop are explicit options. Unknown,
disabled or unavailable required controls fail before candidate execution. Requested root
drop cannot fail open. A trusted bootstrap reports readiness before setup/candidate code;
the parent validates and preserves it before releasing execution. Candidate-controlled
frames after release cannot attest a configuration failure. The exported
`IsolationConfigurationError` propagates through `score`, `self_check` and the TRL wrapper
instead of becoming a zero reward. Startup failures clean up partial resources.

## Paired synthetic controls

Four fresh synthetic parents span Landlock on/off × parent dumpable on/off, with a forked
same-uid reader testing both APIs (eight cases). Readers receive a known synthetic canary
address and size. No heap scan, expected grading answer, or real secret is involved.
Both natural positive controls (Landlock off/dumpable on) must read the known bytes.
Every other case must deny access with an explicit errno; Landlock setup must succeed
before claiming its effect. Landlock was on at ABI 1. The results show its ptrace-related
protection also covers `process_vm_readv` on this runtime; it is not merely a `/proc` path
restriction. Parent nondumpability adds an independently measured boundary with Landlock off.

{chr(10).join(table)}

Raw evidence: `memread-2026-11-08/canary.json`; source hashes and runtime capabilities are
recorded there and in the companion aggregate JSON. Production grading dumpability was
never toggled for these comparisons.

## Compatibility and regressions

- Full existing suite plus isolation and synthetic regressions: **{check.group(1)} passed**
  in {check.group(2)} seconds. Clean interpreter: `~/p9/at-0129/bin/python`; no mixed dependency
  path was used for this accepted full run.
- All **591 supplied references passed** in both fenced and bare forms; the additional
  164 HumanEval body-plus-prompt checks passed too: **{references['reference_cells']} / {references['reference_cells']} cells**,
  **0 rejected reference cells**, {references['seconds']} seconds with two workers.
- No observed reference-score change: all 1,182 corresponding cells match B's frozen
  securegrade 0.1.1 baseline; all 1,346 variants match the historical `sg_fn_rate` output.
  Comparisons and fixture/source hashes are in `memread-2026-11-08/references-012.json`.
- The new driver reuses `scripts/sg_fn_rate.py`'s grading logic with cached tasks only.
  Historical `results/securegrade_fn.json` and B's baseline artifacts were not overwritten.

Reference and standalone-canary interpreter: `{sys.executable}` (Python {sys.version.split()[0]}).
Resolved interpreter paths and executable SHA-256 values, package/test/driver source hashes,
fixture hash, and raw-artifact hashes are recorded in the companion aggregate JSON.

Regressions cover once-per-PID initialization under threads/fork, initialization failure
and drift, invalid/disabled/unavailable required controls, bootstrap control failure before
setup/candidate side effects, untrusted post-execution configuration frames, TRL exception
propagation, requested root-drop startup failure, and partial pipe cleanup. Root failure
paths are simulated; they are not a successful root deployment test.

An earlier diagnostic tools-interpreter run lacked pytest. Reusing existing pytest via a
temporary module path then gave 16 passing regressions and one mistaken matrix expectation:
it had expected Landlock-on `process_vm_readv` to succeed. That assertion was corrected to
require the established Landlock denial. The accepted clean full run includes this correction.

## Scope and upstream context

Training results used **0.1.0** for original/core runs and **0.1.1** for the H hole pair.
This **0.1.2** hardening changes no honest-answer grading rule; the unchanged-score evidence
is limited to the supplied references above. It does not prove universal correct-answer
coverage or robustness to every possible exploit.

B's pinned-source re-audit separately found the existing private memory-read probe rejected
by AlignTune tag `ff59f10` (requested 0.1.29; source-install distribution metadata 0.1.10)
in 20/20 cells. One further result is withheld pending private disclosure.
The earlier AlignTune head control paid in 20/20 cells. Those are specific source/runtime
observations, not claims about every current release or runtime. See
`release-reaudit-2026-11-08.md`. The new paired controls contain no copy of the real probe.

**Yama, Docker and root deployments of 0.1.2 remain untested.** The recorded 0.1.1 RunPod
root self-check is separate historical runtime evidence, not evidence for all numpy
variants or for 0.1.2. No static pipe/availability or fixed hash-seed collision hardening
was included; those remain documented concerns, not newly reproduced findings here.
The classes-only upstream note is a private draft (not part of this repo), **unsent**.
"""
    (ROOT / "results" / "memread-2026-11-08.md").write_text(markdown)
    print(json.dumps({"report": "results/memread-2026-11-08.md", "pytest_passed": int(check.group(1)),
                      "reference_cells": references["reference_cells"], "matrix_cases": len(canary["rows"])}))


if __name__ == "__main__":
    main()
