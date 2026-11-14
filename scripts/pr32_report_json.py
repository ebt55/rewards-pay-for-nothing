"""Bundle the SafeTune PR #32 check into results/safetune-pr32-check-2026-11-03.json (our code, MIT).

Reads the raw files in results/safetune-pr32/ (written by pr32_gate1.py, pr32_fn_rate.py,
pr32_scans.py, pr32_probes.sh, pr32_systemexit_check.sh, pr32_tables.py). stdlib only.
Usage: python3 scripts/pr32_report_json.py
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / "results" / "safetune-pr32"


def load(name):
    p = D / name
    return json.loads(p.read_text()) if p.exists() else None


def trl_txt():
    runs, cur = [], None
    for line in (D / "systemexit_trl.txt").read_text().splitlines():
        m = re.match(r"=== safetune: (.*) \| middle completion: (\S+)", line)
        if m:
            cur = {"safetune": m.group(1), "middle": m.group(2), "exit_status": None, "after": None, "continued": False}
            runs.append(cur)
        elif line.startswith("process exit status:") and cur:
            cur["exit_status"] = int(line.split(":")[1])
        elif line.startswith("AFTER _calculate_rewards") and cur:
            cur["after"] = json.loads(line.split("):", 1)[1])
        elif line.startswith("TRAINING LOOP WOULD CONTINUE") and cur:
            cur["continued"] = True
    return runs


def main():
    probes = [json.loads(l) for l in (D / "probes.jsonl").read_text().splitlines()] if (D / "probes.jsonl").exists() else []
    fn = load("safetune-pr32-fn.json")
    scans = load("safetune-pr32-scans.json")
    tables = load("tables.json")
    summary = json.loads((D / "summary_input.json").read_text()) if (D / "summary_input.json").exists() else {}
    out = {
        **summary,
        "exploit_table": tables["exploit_table"] if tables else None,
        "pr_cells_above_zero_for_solves_nothing_exploits": tables["pr_above_zero"] if tables else None,
        "side_experiments": {"pr": (load("safetune-pr32-side.json") or {}).get("side"),
                             "0.1.10": (load("safetune-0.1.10-side.json") or {}).get("side")},
        "systemexit_trl": trl_txt(),
        "false_negatives": {"summary": fn["summary"], "rows": fn["fn_rows"], "by_task": tables.get("fn_by_task"),
                            "timeout_s": fn["timeout_s"]} if fn else None,
        "scans": {k: scans[k] for k in ("summary", "free_names", "undecomposable", "builtin_name_tasks")} if scans else None,
        "probes": probes,
        "raw_files": sorted(p.name for p in D.iterdir()),
    }
    path = ROOT / "results" / "safetune-pr32-check-2026-11-03.json"
    path.write_text(json.dumps(out, indent=1, default=str))
    print("wrote", path, path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
