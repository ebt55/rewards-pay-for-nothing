"""Re-score the securegrade replay controls and class a/b items with securegrade 0.1.3 (14 Nov 2026).

Reuses scripts/replay_release.py read-only (JOBS, columns(), CELL_TIMEOUT) and rewardcheck.check_cell,
exactly as `replay_release.py grade --target securegrade-0.1.2` did: test_list + test_imports, no
entry_point, a fresh reward object in a fresh forked child per cell, serial cells. The private job file
~/p9/replay-2026-11-14/jobs.json (completion texts) is only read; the 0.1.2 baseline
~/p9/replay-2026-11-14/out/securegrade-0.1.2.jsonl is only read. Public outputs carry ids, classes,
scores and statuses, never completion text.

    cd <repo>; env -u PYTHONPATH CUDA_VISIBLE_DEVICES="" OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 \
      PYTHONDONTWRITEBYTECODE=1 nice -n 19 ~/p9/tools/bin/python -B scripts/sg_013_replay_recheck.py
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "harness"), str(ROOT / "scripts")]
import replay_release as rr  # noqa: E402  (read-only: constants and columns())
import securegrade  # noqa: E402
from rewardcheck.core import check_cell  # noqa: E402

BASELINE = rr.WORK / "out" / "securegrade-0.1.2.jsonl"
PUBLIC = ROOT / "results" / "replay-release-2026-11-14.json"
OUT = ROOT / "results" / "securegrade-013-recheck-2026-11-14"
CLASSES = ("a", "b", "control")


def main():
    if sys.platform != "linux" or securegrade.__version__ != "0.1.3" or not securegrade.__file__.startswith(str(ROOT)):
        sys.exit("requires Linux and the in-repo securegrade 0.1.3")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "" or os.getpriority(os.PRIO_PROCESS, 0) < 19:
        sys.exit('run with CUDA_VISIBLE_DEVICES="" under nice -n 19')
    items = [i for i in json.loads(rr.JOBS.read_text())["items"] if i["class"] in CLASSES]
    public = json.loads(PUBLIC.read_text())
    if public["still_paid_count"] != 0:
        sys.exit("withheld items present: public ids would leak; stop")
    old = {}
    for line in BASELINE.read_text().splitlines():
        r = json.loads(line)
        old[r["id"]] = r  # latest record (a retry) wins, as in replay_release.report()
    scratch = rr.WORK / "scratch" / "securegrade-0.1.3"
    rows, start = [], time.monotonic()
    for n, it in enumerate(items, 1):
        res = check_cell("rewardcheck.targets:securegrade_factory", it["text"], rr.columns("securegrade", None, it),
                         timeout=rr.CELL_TIMEOUT, scratch=str(scratch))
        if res.get("status") != "scored":  # one serial retry, as replay_release.grade() does
            res = check_cell("rewardcheck.targets:securegrade_factory", it["text"], rr.columns("securegrade", None, it),
                             timeout=rr.CELL_TIMEOUT, scratch=str(scratch))
        b = old.get(it["id"], {})
        rows.append({"id": it["id"], "class": it["class"], "status_012": b.get("status"), "score_012": b.get("score"),
                     "status_013": res.get("status"), "score_013": res.get("score"),
                     "exception_type_013": res.get("exception_type")})
        if n % 50 == 0:
            print(json.dumps({"cells": n, "of": len(items), "elapsed_s": round(time.monotonic() - start, 1)}), flush=True)
    table = {}
    for c in CLASSES:
        cr = [r for r in rows if r["class"] == c]
        table[c] = {"n": len(cr)}
        for v in ("012", "013"):
            s = [r[f"score_{v}"] for r in cr if r[f"status_{v}"] == "scored"]
            table[c][v] = {"scored": len(s), "full": sum(x >= 0.999 for x in s), "positive": sum(x > 0 for x in s),
                           "mean": round(sum(s) / len(s), 6) if s else None}
    changed = [r for r in rows if (r["status_012"], r["score_012"]) != (r["status_013"], r["score_013"])]
    out = {"schema_version": 1, "date": "2026-11-14", "securegrade": "0.1.3", "baseline": "securegrade 0.1.2 replay cells",
           "baseline_sha256": hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
           "public_replay_sha256": hashlib.sha256(PUBLIC.read_bytes()).hexdigest(),
           "scope": "replay items of classes a, b and control from results/replay-release-2026-11-14.json; "
                    "MBPP sanitized test_list + test_imports, no entry_point (as training computed secure_all)",
           "cell_containment": "rewardcheck.check_cell, fresh forked child per cell, serial, 60 s deadline, one retry",
           "runtime": {"python": sys.version.split()[0], "interpreter": sys.executable, "kernel": platform.release(),
                       "nice": os.getpriority(os.PRIO_PROCESS, 0), "cuda_visible_devices": "",
                       "seconds": round(time.monotonic() - start, 1)},
           "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted((ROOT / "securegrade").glob("*.py"))},
           "table": table, "changed_cells": changed, "rows": rows}
    OUT.with_suffix(".json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    md = ["# securegrade 0.1.3 replay recheck, 14 Nov 2026", "",
          "Re-scored with securegrade 0.1.3 (review fixes CODE-01/02/03/06): the 300 controls and the class a/b",
          "items of `results/replay-release-2026-11-14.json`, through `rewardcheck.check_cell` exactly as the",
          "0.1.2 replay did (test_list + test_imports, no entry_point). Raw: "
          "`securegrade-013-recheck-2026-11-14.json`.", "",
          "| class | n | 0.1.2 full | 0.1.3 full | 0.1.2 positive | 0.1.3 positive | 0.1.2 mean | 0.1.3 mean |",
          "|---|---|---|---|---|---|---|---|"]
    for c in CLASSES:
        t = table[c]
        md.append(f"| {rr.CLASS_NAMES[c]} | {t['n']} | {t['012']['full']} | {t['013']['full']} | {t['012']['positive']} | "
                  f"{t['013']['positive']} | {t['012']['mean']} | {t['013']['mean']} |")
    md += ["", f"Cells whose status or score changed: **{len(changed)}** of {len(rows)}."]
    md += [f"- `{r['id']}` ({r['class']}): {r['status_012']} {r['score_012']} -> {r['status_013']} {r['score_013']}"
           for r in changed]
    md += ["", f"Runtime: Python {out['runtime']['python']}, kernel {out['runtime']['kernel']}, nice 19, "
           f"CUDA_VISIBLE_DEVICES empty, {out['runtime']['seconds']} s.", ""]
    OUT.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"table": table, "changed": len(changed),
                      "classes": dict(collections.Counter(r["class"] for r in rows))}, indent=1))


if __name__ == "__main__":
    main()
