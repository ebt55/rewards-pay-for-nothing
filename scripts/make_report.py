"""Build results/gate1-2026-11-01.json (all raw scores + gate computation) and
results/gate1-tables-2026-11-01.md (full per-task tables + compact table) from the raw runner output.

Gate 1 rule (as applied here): an execution-based reward "pays for nothing" if some exploit marked
solves_nothing scores >= 0.5 on all 5 tasks, in one completion format (fenced or bare), with the
tests supplied in the format that reward reads, built at weight 1.0. A no-tests count is reported too.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
RES = ROOT / "results"
DATE = "2026-11-01"
raw = {p: json.loads((RES / f"raw_{p}.json").read_text()) for p in ("aligntune", "safetune")}
recipe = json.loads((RES / "recipe_sim.json").read_text()) if (RES / "recipe_sim.json").exists() else None
EXPLOITS = raw["aligntune"]["exploits"]
EX_IDS = [e["id"] for e in EXPLOITS]
NOTHING = [e["id"] for e in EXPLOITS if e["solves_nothing"]]
TASKS = raw["aligntune"]["tasks"]

EXECUTION_BASED = {
    ("aligntune", "code_execution"), ("aligntune", "code_correctness"), ("aligntune", "mbpp_reward"),
    ("aligntune", "code_verifiable"), ("aligntune", "counterfact_grpo_code"),
    ("safetune", "code_execution"), ("safetune", "code_correctness"), ("safetune", "mbpp_reward"),
}
IN_REGISTRY = lambda pkg, base: base != "counterfact_grpo_code"
# SafeTune's CodeCorrectnessReward is a thin alias that calls CodeExecutionReward.compute.
IMPLEMENTATION = {("safetune", "code_correctness"): ("safetune", "code_execution")}


def val(c):
    return c["score"] if c["status"] == "ok" and c["score"] is not None else None


def show(c):
    if c["status"] == "ok":
        return f"{c['score']:.2f}"
    if c["status"] == "raised":
        return "exc:" + c["exc"].split(":")[0]
    return c["status"]


rows = []  # (pkg, reward, mode)
idx = {}
for pkg, d in raw.items():
    for c in d["cells"]:
        idx[(pkg, c["reward"], c["mode"], c["task"], c["exploit"], c["fenced"])] = c
        key = (pkg, c["reward"], c["mode"])
        if key not in rows:
            rows.append(key)


def min_over_tasks(pkg, rw, mode, ex, fenced):
    vals = []
    for t in TASKS:
        v = val(idx[(pkg, rw, mode, t, ex, fenced)])
        if v is None:
            return None
        vals.append(v)
    return min(vals)


def summary_cell(pkg, rw, mode, ex):
    if ex == "reference":  # false-negative check: on how many of the 5 tasks does the real solution get >= 0.95?
        ok = [sum(1 for t in TASKS if (val(idx[(pkg, rw, mode, t, ex, f)]) or -9) >= 0.95) for f in (True, False)]
        return f"{ok[0]}/5 · {ok[1]}/5 full"
    out = []
    for f in (True, False):
        m = min_over_tasks(pkg, rw, mode, ex, f)
        if m is None:
            sts = {idx[(pkg, rw, mode, t, ex, f)]["status"] for t in TASKS}
            excs = {show(idx[(pkg, rw, mode, t, ex, f)]) for t in TASKS if idx[(pkg, rw, mode, t, ex, f)]["status"] != "ok"}
            out.append("/".join(sorted(excs)) if excs else "/".join(sorted(sts)))
        else:
            out.append(f"{m:.2f}")
    return " / ".join(out)


# ---------------- gate computation
gate = {"rule": __doc__.strip().split("\n\n")[1].replace("\n", " "), "tests_mode": {}, "no_tests_mode": {}}
for (pkg, rw, mode) in rows:
    base = rw.split("[")[0]
    if (pkg, base) not in EXECUTION_BASED:
        continue
    best = None
    for ex in NOTHING:
        for f in (True, False):
            m = min_over_tasks(pkg, rw, mode, ex, f)
            if m is not None and (best is None or m > best[0]):
                best = (m, ex, "fenced" if f else "bare")
    bucket = gate["tests_mode"] if mode == "tests" else gate["no_tests_mode"]
    name = f"{pkg}:{rw}"
    bucket[name] = {"best_solves_nothing_min_over_5_tasks": best[0] if best else None,
                    "exploit": best[1] if best else None, "format": best[2] if best else None,
                    "pays": bool(best and best[0] >= 0.5), "in_registry": IN_REGISTRY(pkg, base),
                    "implementation": "%s:%s" % IMPLEMENTATION.get((pkg, base), (pkg, base))}


def count(bucket, registry_only=True):
    impls = {v["implementation"] for k, v in bucket.items() if v["pays"] and (v["in_registry"] or not registry_only)}
    names = sorted({k.split("[")[0] for k, v in bucket.items() if v["pays"] and (v["in_registry"] or not registry_only)})
    return sorted(impls), names

gate["tests_mode_paying_implementations"], gate["tests_mode_paying_registry_names"] = count(gate["tests_mode"])
gate["no_tests_mode_paying_implementations"], gate["no_tests_mode_paying_registry_names"] = count(gate["no_tests_mode"])
gate["PASS"] = len(gate["tests_mode_paying_implementations"]) >= 2

# ---------------- outputs
consolidated = {
    "date": DATE,
    "versions": {p: raw[p]["versions"] for p in raw},
    "registry_entries": {p: raw[p]["registry_entries"] for p in raw},
    "tasks": TASKS, "exploits": EXPLOITS,
    "reward_specs": {p: raw[p]["specs"] for p in raw},
    "gate": gate,
    "cells": [c for p in raw for c in raw[p]["cells"]],
    "side_experiments": {p: raw[p]["side"] for p in raw},
    "recipe_simulation": recipe,
}
for name in ("path_check.jsonl", "systemexit_trl.txt", "sql_check.json"):
    f = RES / name
    if f.exists():
        consolidated[name] = f.read_text()
(RES / f"gate1-{DATE}.json").write_text(json.dumps(consolidated, indent=1, default=str))

L = [f"# Gate 1 tables ({DATE}) - generated by scripts/make_report.py", "",
     "Cell = lowest score across the 5 tasks, shown as `fenced / bare` (completion inside a ```python block / bare code).",
     "Reference column = number of tasks (of 5) where the dataset's own solution scored >= 0.95, fenced · bare.",
     "Weight 1.0. `exc:SystemExit` = the exception escaped `compute()` into the caller.", "",
     "## Compact table", "",
     "| package:reward [mode] | " + " | ".join(EX_IDS) + " |", "|" + "---|" * (len(EX_IDS) + 1)]
for (pkg, rw, mode) in rows:
    L.append(f"| {pkg}:{rw} [{mode}] | " + " | ".join(summary_cell(pkg, rw, mode, ex) for ex in EX_IDS) + " |")
L += ["", "## Gate computation", "", "```json", json.dumps({k: v for k, v in gate.items() if k != "rule"}, indent=1), "```", ""]
L += ["## Full per-task tables", ""]
for (pkg, rw, mode) in rows:
    L += [f"### {pkg}:{rw} [{mode}]", "", "| exploit | " + " | ".join(TASKS) + " |", "|" + "---|" * (len(TASKS) + 1)]
    for ex in EX_IDS:
        L.append(f"| {ex} | " + " | ".join(f"{show(idx[(pkg, rw, mode, t, ex, True)])} / {show(idx[(pkg, rw, mode, t, ex, False)])}" for t in TASKS) + " |")
    L.append("")
(RES / f"gate1-tables-{DATE}.md").write_text("\n".join(L))
print("PASS" if gate["PASS"] else "FAIL", "| tests-mode paying implementations:", gate["tests_mode_paying_implementations"])
print("no-tests-mode paying implementations:", gate["no_tests_mode_paying_implementations"])
for k, v in gate["tests_mode"].items():
    print(" tests ", k, v["best_solves_nothing_min_over_5_tasks"], v["exploit"], v["format"])
for k, v in gate["no_tests_mode"].items():
    print(" notests", k, v["best_solves_nothing_min_over_5_tasks"], v["exploit"], v["format"])
