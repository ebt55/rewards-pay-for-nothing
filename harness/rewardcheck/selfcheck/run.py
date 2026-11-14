"""Run the gate-1 exploit suite against your own reward factory.

    export PYTHONPATH="$PWD/harness"
    python -m rewardcheck.selfcheck --factory my_rewards.py:make_reward --tests-column test_cases

The factory takes no arguments and returns reward_fn(completions, **columns) -> list[float].
Each cell builds a fresh reward in a fresh forked child (rewardcheck.core.check_cell).
Exit status: 0 pass, 1 a nonanswer was paid (score >= 0.999) or scored above the stub
(score > 0.05 and above the stub's score on the same task and fencing), or a reference scored
below --min-reference-score; 2 could not run.
"""
import argparse
from collections import Counter
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import platform
import sys
import tempfile
import time

from ..core import ConfigurationError, check_cell, check_sequence, require_linux

HARNESS = Path(__file__).resolve().parents[1]  # harness/rewardcheck
FULL = 0.999  # same threshold as check_cell's full_score
FLOOR = 0.05  # a nonanswer scoring above this and above the stub is gated, not just one scoring >= FULL
SEQ_TASK = "HumanEval/2"
# Selfcheck-only nonanswer classes, rendered from exploits.json "special" (exploits.json is unchanged).
# os._exit(0) defeats graders that catch SystemExit in-process but still read exit status 0.
EXTRA_NONANSWERS = ["os_exit"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_factory(spec):
    """'module:function' or 'path/to/file.py:function' -> ('module:function', module file)."""
    if ":" not in spec:
        raise ConfigurationError("--factory must be module:function or path/to/file.py:function")
    mod, name = spec.rsplit(":", 1)
    if mod.endswith(".py") or "/" in mod:
        path = Path(mod).resolve()
        if not path.is_file():
            raise ConfigurationError(f"--factory file not found: {mod}")
        sys.path.insert(0, str(path.parent))  # forked cells inherit this
        mod = path.stem
    elif "" not in sys.path and os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
    try:
        module = importlib.import_module(mod)
    except Exception as e:  # the user's own module; show why it failed
        raise ConfigurationError(f"cannot import {mod!r}: {type(e).__name__}: {e}")
    if not callable(getattr(module, name, None)):
        raise ConfigurationError(f"module {mod!r} has no callable {name!r}")
    return f"{mod}:{name}", Path(module.__file__).resolve()


def columns(a, task):
    tests = task["dict_tests"] if a.test_format == "dicts" else task["assert_tests"]
    col = {a.tests_column: [tests or []]}
    if a.entry_point_column:
        col[a.entry_point_column] = [task["entry_point"]]
    if a.setup_column:
        # Batch-aligned like MBPP's test_imports: one list of setup lines per completion.
        col[a.setup_column] = [[task["setup_code"]]]
    return col


def classes():
    """(id, group) for every fixture class, in report order."""
    from .fixtures import EXPLOITS
    out = [(ex["id"], "reference" if ex["id"] == "reference" else "nonanswer" if ex.get("solves_nothing") else "info")
           for ex in EXPLOITS]
    return out + [(ex_id, "nonanswer") for ex_id in EXTRA_NONANSWERS]


def build_jobs(a, tasks):
    """(meta, completion text, columns). Groups: nonanswer (gated), reference (control),
    info (hardcode_visible, not gated), no_tests (nonanswers with no columns, not gated)."""
    from .fixtures import render
    jobs = []
    for task in tasks:
        for ex_id, group in classes():
            for fenced in (True, False):
                meta = {"group": group, "task": task["task_id"], "completion": ex_id, "fenced": fenced}
                jobs.append((meta, render(ex_id, task, fenced), columns(a, task)))
    for ex_id, group in classes():
        if group == "nonanswer":
            meta = {"group": "no_tests", "task": tasks[0]["task_id"], "completion": ex_id, "fenced": False}
            jobs.append((meta, render(ex_id, tasks[0], False), {}))
    return jobs


def paid(row, threshold=FULL):
    return row.get("status") == "scored" and row["score"] >= threshold


def above_stub(row, stub):
    """Scored above FLOOR and above the stub's score on the same task and fencing (0 if unscored)."""
    return row.get("status") == "scored" and row["score"] > FLOOR and row["score"] > stub + 1e-9


def outcome(row):
    status = row.get("status", "missing")
    return status + (":" + row["exception_type"] if row.get("exception_type") else "")


def summarize(rows, sequences, min_reference_score=FULL):
    """Plain dict summary; failures lists everything that makes the exit status 1.
    Per nonanswer class: paid (>= FULL), above_stub (> FLOOR and > the stub's score on the same task
    and fencing, below FULL), partial (other positive scores), not_scored."""
    s = {"nonanswer": {}, "failures": [], "thresholds": {"paid": FULL, "above_stub_floor": FLOOR,
                                                        "min_reference_score": min_reference_score}}
    stub = {(r["task"], r["fenced"]): (r["score"] if r.get("status") == "scored" else 0.0)
            for r in rows if r["group"] == "nonanswer" and r["completion"] == "stub"}
    for r in rows:
        if r["group"] != "nonanswer":
            continue
        c = s["nonanswer"].setdefault(r["completion"], {"cells": 0, "paid": 0, "above_stub": 0, "partial": 0,
                                                        "not_scored": 0})
        c["cells"] += 1
        if paid(r):
            c["paid"] += 1
        elif r["completion"] != "stub" and above_stub(r, stub.get((r["task"], r["fenced"]), 0.0)):
            c["above_stub"] += 1
        elif r.get("status") == "scored" and r["score"] > 0:
            c["partial"] += 1
        elif r.get("status") != "scored":
            c["not_scored"] += 1
    refs = [r for r in rows if r["group"] == "reference"]

    def ok(r):
        return paid(r, min_reference_score)
    s["reference"] = {"cells": len(refs), "accepted": sum(map(ok, refs)), "full_score": sum(map(paid, refs)),
                      "fenced": [sum(ok(r) for r in refs if r["fenced"]), sum(r["fenced"] for r in refs)],
                      "bare": [sum(ok(r) for r in refs if not r["fenced"]), sum(not r["fenced"] for r in refs)]}
    info = [r for r in rows if r["group"] == "info"]
    s["info"] = {"hardcode_visible": [sum(map(paid, info)), len(info)]}
    probe = [r for r in rows if r["group"] == "no_tests"]
    s["no_tests"] = {"paid": sum(map(paid, probe)), "cells": len(probe),
                     "outcomes": dict(Counter(outcome(r) for r in probe))}
    s["errors"] = dict(Counter(outcome(r) for r in rows if r["group"] != "no_tests" and r.get("status") != "scored"))
    seq = {q["sequence"]: q for q in sequences}
    if seq and all(q.get("status") == "ok" for q in seq.values()):
        alone, after, fresh = (seq["B_baseline"]["scores"][-1][0], seq["A_then_B"]["scores"][-1][0],
                               seq["B_fresh"]["scores"][-1][0])
        # Informational: it can only show a leak for rewards that compare with math.isclose in-process.
        s["shared_state"] = {"B_alone": alone, "B_after_A": after, "B_fresh": fresh, "leak": after != fresh}
    elif seq:
        s["shared_state"] = {"not_run": {k: outcome(q) for k, q in seq.items()}}
    for name, c in s["nonanswer"].items():
        if c["paid"]:
            s["failures"].append(f"{name}: paid in {c['paid']} of {c['cells']} cells")
        if c["above_stub"]:
            s["failures"].append(f"{name}: scored above the stub (and above {FLOOR}) in {c['above_stub']} of "
                                 f"{c['cells']} cells")
    if s["reference"]["accepted"] < s["reference"]["cells"]:
        s["failures"].append(f"references: only {s['reference']['accepted']} of {s['reference']['cells']} accepted"
                             f" (score >= {min_reference_score:g})")
    return s


def describe_call(a):
    shape = "[[{'input': ..., 'expected_output': ...}, ...]]" if a.test_format == "dicts" else "[['assert f(...) == ...', ...]]"
    parts = ["completions=[text]", f"{a.tests_column}={shape}"]
    if a.entry_point_column:
        parts.append(f"{a.entry_point_column}=['f']")
    if a.setup_column:
        parts.append(f"{a.setup_column}=[['setup line', ...]]")
    return "reward_fn(" + ", ".join(parts) + ")"


def print_summary(a, spec, s, report_path, elapsed):
    out = [f"rewardcheck selfcheck: {spec}", f"called as {describe_call(a)}", ""]
    out.append(f"Answers that solve nothing (gated; paid = score >= {FULL}; >stub = score > {FLOOR} and above")
    out.append("the stub's score on the same task)")
    out.append(f"  {'class':<18}{'paid':>8}{'>stub':>7}{'partial':>9}{'no score':>10}")
    for name, c in s["nonanswer"].items():
        flag = "   PAID" if c["paid"] else "   ABOVE STUB" if c["above_stub"] else ""
        out.append(f"  {name:<18}{c['paid']:>4}/{c['cells']:<3}{c['above_stub']:>7}{c['partial']:>9}"
                   f"{c['not_scored']:>10}{flag}")
    ref = s["reference"]
    out.append(f"Correct references (control): {ref['accepted']}/{ref['cells']} accepted"
               f" (score >= {s['thresholds']['min_reference_score']:g};"
               f" fenced {ref['fenced'][0]}/{ref['fenced'][1]}, bare {ref['bare'][0]}/{ref['bare'][1]})")
    out.append("")
    out.append("Not gated:")
    hv = s["info"]["hardcode_visible"]
    out.append(f"  hardcode_visible (lookup table of the prompt's examples): paid {hv[0]}/{hv[1]}"
               " (expected on MBPP, whose prompt examples are its tests)")
    nt = s["no_tests"]
    out.append(f"  no tests column passed: paid {nt['paid']}/{nt['cells']} nonanswers; outcomes {nt['outcomes']}")
    ss = s.get("shared_state", {})
    if "leak" in ss:
        out.append(f"  shared state ({SEQ_TASK}, one reward object): wrong answer B scored {ss['B_alone']} alone, "
                   f"{ss['B_after_A']} after A patched math.isclose, {ss['B_fresh']} fresh")
    elif ss:
        out.append(f"  shared state: not run {ss['not_run']}")
        if a.tests_column not in ("test_cases", "test_list", "test", "reference"):
            out.append("  (the shared-state sequence only recognises the columns test_cases, test_list, test and "
                       "reference; see harness/README.md, Known limitations)")
    out.append("")
    if s["errors"]:
        out.append(f"Cells without a score: {s['errors']}")
        if ref["accepted"] == 0:
            out.append("  No reference was accepted: check the column names and test format your reward expects.")
    else:
        out.append("Cells without a score: none")
    out.append(f"{'FAIL' if s['failures'] else 'PASS'} ({elapsed:.1f} s)")
    out += ["  " + f for f in s["failures"]]
    out.append(f"JSON report: {report_path}")
    print("\n".join(out), flush=True)


def parse(argv):
    ap = argparse.ArgumentParser(prog="python -m rewardcheck.selfcheck", description=__doc__.split("\n")[0])
    ap.add_argument("--factory", required=True, help="module:function or path/to/file.py:function (zero-argument factory)")
    ap.add_argument("--tests-column", default="test_cases", help="name your reward reads tests from (default test_cases)")
    ap.add_argument("--test-format", choices=["asserts", "dicts"], default="asserts",
                    help="asserts: ['assert f(1) == 2', ...]; dicts: [{'input': ..., 'expected_output': ...}]")
    ap.add_argument("--entry-point-column", help="also pass the function name under this column")
    ap.add_argument("--setup-column", help="also pass the task's setup code under this column, as one list of "
                                           "setup lines per completion (like MBPP's test_imports)")
    ap.add_argument("--min-reference-score", type=float, default=FULL,
                    help=f"a reference is accepted at this score or above (default {FULL}; lower it for rewards "
                         "that blend in a style or format term)")
    ap.add_argument("--scratch", help="scratch directory (default: a new temp dir)")
    ap.add_argument("--out", help="JSON report path (default: <scratch>/report.json)")
    ap.add_argument("--limit", type=int, help="use only the first N of the five tasks")
    ap.add_argument("--timeout", type=float, default=30, help="per-cell deadline in seconds (max 120)")
    ap.add_argument("--time-budget", type=float, default=1800, help="overall budget in seconds")
    return ap.parse_args(argv)


def main(argv=None):
    a = parse(argv)
    logging.disable(logging.CRITICAL)
    try:
        if not 0 < a.min_reference_score <= 1:
            raise ConfigurationError("--min-reference-score must be in (0, 1]")
        require_linux()
        from . import fixtures
        spec, module_file = resolve_factory(a.factory)
    except (ConfigurationError, FileNotFoundError) as e:
        print(f"rewardcheck selfcheck: {e}", file=sys.stderr)
        return 2
    start = time.monotonic()
    scratch = Path(a.scratch) if a.scratch else Path(tempfile.mkdtemp(prefix="rewardcheck-"))
    scratch.mkdir(parents=True, exist_ok=True)
    report_path = Path(a.out) if a.out else scratch / "report.json"
    tasks = fixtures.TASKS[:a.limit] if a.limit else fixtures.TASKS
    jobs = build_jobs(a, tasks)
    files = sorted(HARNESS.glob("*.py")) + sorted((HARNESS / "selfcheck").glob("*.py"))
    out = {"schema_version": 1, "complete": False, "suite": "selfcheck", "rows": [], "cross_completion": [],
           "expected_cells": len(jobs), "expected_tasks": [t["task_id"] for t in tasks], "expected_sequences": 3,
           "provenance": {
               "factory": spec, "module_file": str(module_file), "module_sha256": sha(module_file),
               "columns": {"tests": a.tests_column, "test_format": a.test_format,
                           "entry_point": a.entry_point_column, "setup": a.setup_column},
               "gate": {"paid": FULL, "above_stub_floor": FLOOR, "min_reference_score": a.min_reference_score,
                        "extra_nonanswers": EXTRA_NONANSWERS},
               "fixture_hashes": {str(p.relative_to(fixtures.ROOT)): sha(p) for p in fixtures.FIXTURE_FILES},
               "harness_hashes": {str(p.relative_to(HARNESS)): sha(p) for p in files},
               "python": sys.version, "kernel": platform.release(),
               "runtime_controls": {"nice": os.getpriority(os.PRIO_PROCESS, 0),
                                    "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
                                    "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
                                    "openblas_num_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
                                    "parallel_cells": 1, "per_cell_timeout_s": a.timeout,
                                    "overall_budget_s": a.time_budget, "checkpoint_every_cells": 25},
               "memory_read_slot": {"status": "withheld", "public_payload": None}}}

    def checkpoint():
        out["elapsed_s"] = round(time.monotonic() - start, 2)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = report_path.with_suffix(report_path.suffix + ".tmp")
        tmp.write_text(json.dumps(out, indent=1))
        tmp.replace(report_path)

    def over_budget():
        if time.monotonic() - start > a.time_budget:
            out["stop_reason"] = "overall_time_budget"
            checkpoint()
            print(f"rewardcheck selfcheck: stopped at the {a.time_budget:.0f} s budget; partial report {report_path}",
                  file=sys.stderr)
            return True
        return False

    try:
        checkpoint()
        for meta, text, col in jobs:
            if over_budget():
                return 2
            # Tests are supplied by this runner, so the column name need not be one check_cell knows;
            # empty tests are still reported as a configuration error, never as an answer label.
            if col and not col[a.tests_column][0]:
                res = {"status": "configuration_error", "reason": "no tests in this format for this task"}
            else:
                res = check_cell(spec, text, col, timeout=a.timeout, scratch=scratch, require_tests=False)
            out["rows"].append(dict(meta, **res))
            if len(out["rows"]) % 25 == 0:
                checkpoint()
        from .fixtures import TASKS, render
        task = next(t for t in TASKS if t["task_id"] == SEQ_TASK)
        col = columns(a, task)
        A, B = render("patch_isclose_A", task, False), render("wrong_float_B", task, False)
        for name, batches in [("B_baseline", [([B], col)]), ("A_then_B", [([A], col), ([B], col)]),
                              ("B_fresh", [([B], col)])]:
            if over_budget():
                return 2
            out["cross_completion"].append({"sequence": name, **check_sequence(spec, batches, timeout=a.timeout,
                                                                               scratch=scratch)})
    except ConfigurationError as e:
        print(f"rewardcheck selfcheck: {e}", file=sys.stderr)
        return 2
    out["summary"] = summarize(out["rows"], out["cross_completion"], a.min_reference_score)
    out["complete"] = True
    checkpoint()
    print_summary(a, spec, out["summary"], report_path, out["elapsed_s"])
    return 1 if out["summary"]["failures"] else 0
