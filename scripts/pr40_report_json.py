"""Bundle the AlignTune PR #40 check into results/aligntune-pr40-check-2026-11-03.json (our code, MIT).

Reads the raw files in results/aligntune-pr40/ (written by pr40_gate1.py, pr40_fn_rate.py,
pr40_scans.py, pr40_recipe.py, pr40_probes.sh, pr40_systemexit_check.sh, pr40_tables.py). stdlib only.
Usage: python3 scripts/pr40_report_json.py
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / "results" / "aligntune-pr40"


def load(name):
    p = D / name
    return json.loads(p.read_text()) if p.exists() else None


def trl_txt(name="systemexit_trl.txt"):
    runs, cur = [], None
    for line in (D / name).read_text().splitlines():
        m = re.match(r"=== (.*)", line)
        if m:
            cur = {"case": m.group(1), "exit_status": None, "after": None, "continued": False}
            runs.append(cur)
        elif line.startswith("process exit status:") and cur:
            cur["exit_status"] = int(line.split(":")[1])
        elif line.startswith("AFTER") and cur:
            cur["after"] = line.split(":", 1)[1].strip() if "):" not in line else json.loads(line.split("):", 1)[1])
        elif line.startswith("TRAINING LOOP WOULD CONTINUE") and cur:
            cur["continued"] = True
        elif line.startswith("last exception line:") and cur:
            cur["last_exception"] = line.split(":", 1)[1].strip()
    return runs


def main():
    probes = [json.loads(l) for l in (D / "probes.jsonl").read_text().splitlines()] if (D / "probes.jsonl").exists() else []
    fn = load("aligntune-pr40-fn.json")
    scans = load("aligntune-pr40-scans.json")
    tables = load("tables.json")
    summary = json.loads((D / "summary_input.json").read_text()) if (D / "summary_input.json").exists() else {}
    out = {
        **summary,
        "exploit_table": tables["exploit_table"] if tables else None,
        "pr_cells_above_zero_for_solves_nothing_exploits": tables["pr_above_zero"] if tables else None,
        "side_experiments": {"pr": (load("aligntune-pr40-side.json") or {}).get("side"),
                             "0.1.28_extra": (load("aligntune-0.1.28-side.json") or {}).get("side"), "0.1.28_gate1": json.loads((ROOT / "results" / "raw_aligntune.json").read_text())["side"]},
        "systemexit_trl": trl_txt(),
        "deep_nesting_crash": trl_txt("crash_deep_nesting.txt"),
        "aplus_baseline": (D / "aplus_baseline.txt").read_text().splitlines(),
        "recipe": load("aligntune-pr40-recipe.json"),
        "our_patched_aligntune_tests_on_pr40": (D / "patched_tests_on_pr40.txt").read_text().splitlines(),
        "false_negatives": {"summary": fn["summary"], "rows": fn["fn_rows"], "by_task": tables.get("fn_by_task"),
                            "timeout_s": fn["timeout_s"]} if fn else None,
        "scans": {k: scans[k] for k in ("summary", "free_names", "undecomposable", "builtin_name_tasks")} if scans else None,
        "probes": probes,
        "raw_files": sorted(p.name for p in D.iterdir()),
    }
    path = ROOT / "results" / "aligntune-pr40-check-2026-11-03.json"
    path.write_text(json.dumps(out, indent=1, default=str))
    print("wrote", path, path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
