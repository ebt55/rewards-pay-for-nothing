"""Gate-1 fixtures, read from <repo root>/exploits/. No import from scripts/.

render() is a copy of scripts/gate1_run.render; harness/tests/test_selfcheck.py
checks that the two produce identical text for every exploit, task and fencing.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "exploits"
FIXTURE_FILES = [FIXTURE_DIR / "exploits.json", FIXTURE_DIR / "tasks.json"]

_missing = [p.name for p in FIXTURE_FILES if not p.is_file()]
if _missing:
    raise FileNotFoundError(
        f"rewardcheck fixtures missing: {FIXTURE_DIR} has no {', '.join(_missing)}. "
        "Run from a full checkout of this repository (harness/ and exploits/ side by side).")

TASKS = json.loads((FIXTURE_DIR / "tasks.json").read_text())
EXDATA = json.loads((FIXTURE_DIR / "exploits.json").read_text())
EXPLOITS = EXDATA["exploits"]
SPECIAL = EXDATA["special"]
EX_BY_ID = {e["id"]: e for e in EXPLOITS}


def render(ex_id, task, fenced=True):
    """Completion text for one exploit on one task (fenced = wrapped in a ```python block)."""
    fn = task["entry_point"]
    if ex_id == "reference":
        body = task["reference_solution"].strip()
    else:
        tmpl = EX_BY_ID[ex_id]["template"] if ex_id in EX_BY_ID else SPECIAL[ex_id]
        body = tmpl.replace("{fn}", fn)
        if "{table}" in body:
            table = {repr(tuple(v["args"])): v["expected"] for v in task["visible_examples"]}
            body = body.replace("{table}", repr(table))
    if fenced and EX_BY_ID.get(ex_id, {}).get("fenceable", True):
        return "```python\n" + body + "\n```"
    return body
