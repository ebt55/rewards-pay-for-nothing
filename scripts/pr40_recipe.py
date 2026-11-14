"""Recipe check for AlignTune PR #40 (our code, MIT): the three recipe files Gate 1 flagged.

Same simulation as scripts/recipe_sim.py, on the PR's files, no model:
  recipe YAML -> prepare_trl_rewards -> RewardBridge -> TRL-style call with every dataset column
  except prompt/completion/completion_ids as keywords -> total = sum(weight_i * r_i).
The dataset is loaded with HF_HUB_OFFLINE / HF_DATASETS_OFFLINE set by the runner, so only a cached
copy is used (nothing is downloaded).

Usage (at venv): HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 python -W ignore scripts/pr40_recipe.py
Writes results/aligntune-pr40/<label>-recipe.json
"""
import ast
import importlib.resources as ir
import json
import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pr40_common import LABEL, OUT, ROOT, SRC, use_pr  # noqa: E402

WHERE = use_pr()
import yaml  # noqa: E402

TASKS = json.loads((ROOT / "exploits" / "tasks.json").read_text())
EX = json.loads((ROOT / "exploits" / "exploits.json").read_text())
RES = {"label": LABEL, "aligntune_rewards_core_file": WHERE}


def tmpl(ex_id, fn):
    for e in EX["exploits"]:
        if e["id"] == ex_id:
            return e["template"].replace("{fn}", fn)
    return EX["special"][ex_id].replace("{fn}", fn)


def fence(s):
    return "```python\n" + s + "\n```"


cfgs = {}
for rel in ("grpo/deepseek_humaneval.yaml", "advanced/gbmpo_l2_code.yaml"):
    p = ir.files("aligntune") / "recipes" / "configs" / rel
    y = yaml.safe_load(p.read_text())
    cfgs[rel] = y
    RES[rel] = {"file": str(p), "recipe_dataset": y["recipe"].get("dataset"), "datasets": y["config"]["datasets"],
                "rewards": y["config"].get("rewards")}

# The MBPP example's reward list, read from the file (examples/ is not in the wheel).
ex_path = (pathlib.Path(SRC).parent / "examples" / "grpo_code_gen_trl_mbpp.py") if SRC != "installed" else None
if ex_path and ex_path.exists():
    # The file is notebook-style (it has `!git clone` lines), so read the rewards list with a regex.
    import re
    src = ex_path.read_text()
    block = re.search(r"rewards\s*=\s*\[(.*?)\]", src, re.DOTALL)
    found = re.findall(r'"type"\s*:\s*"(\w+)"', block.group(1)) if block else []
    RES["mbpp_example_reward_types"] = found

from aligntune.data.manager import DataManager  # noqa: E402

cfg = cfgs["grpo/deepseek_humaneval.yaml"]["config"]


def try_manager(name):
    try:
        dm = DataManager(task_type="grpo", column_mapping=cfg["datasets"][0].get("column_mapping"), tokenizer=None)
        dd = dm.load_dataset(name, split=cfg["datasets"][0]["split"])
        ds = dd[cfg["datasets"][0]["split"]]
        return {"ok": True, "rows": len(ds), "columns": ds.column_names}, ds
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}", "tb_tail": traceback.format_exc()[-400:]}, None


RES["datamanager_recipe_dataset"], ds = try_manager(cfg["datasets"][0]["name"])
if ds is not None:
    row = dict(ds[0])
    RES["row_source"] = f"DataManager(task_type=grpo, column_mapping={cfg['datasets'][0].get('column_mapping')}) on {cfg['datasets'][0]['name']}, row 0"
    RES["row_columns"] = sorted(row.keys())
else:
    he0r = next(t for t in TASKS if t["task_id"] == "HumanEval/0")["raw_columns"]
    row = dict(he0r)
    RES["row_source"] = "raw HumanEval/0 columns from exploits/tasks.json (dataset not loaded offline)"

from aligntune.core.rl.reward_handler import prepare_trl_rewards  # noqa: E402

prepared = prepare_trl_rewards(cfg["rewards"])
RES["prepared_names"], RES["prepared_weights"] = prepared.names, prepared.weights
he0 = next(t for t in TASKS if t["task_id"] == "HumanEval/0")
raw = he0["raw_columns"]
fn = he0["entry_point"]
full_ref = raw["prompt"] + raw["canonical_solution"]
completions = {
    "canonical body only (continuation of the prompt)": raw["canonical_solution"],
    "canonical full function, fenced": fence(full_ref),
    "canonical full function, bare": full_ref,
    "stub, fenced": fence(tmpl("stub", fn)),
    "stub, bare": tmpl("stub", fn),
    "empty": "",
    "prose": tmpl("prose", fn),
    "always_equal, bare": tmpl("always_equal", fn),
    "wrong answer (return True), fenced": fence(f"def {fn}(*args, **kwargs):\n    return True"),
}
texts = list(completions.values())
n = len(texts)
columns = {k: [v] * n for k, v in row.items() if k not in ("prompt", "completion", "completion_ids")}
extras = {"trainer_state": None, "log_extra": lambda *a, **k: None, "log_metric": lambda *a, **k: None}
per = {nm: f(prompts=[row.get("prompt", "")] * n, completions=texts, completion_ids=None, **columns, **extras)
       for nm, f in zip(prepared.names, prepared.functions)}
RES["columns_passed_as_kwargs"] = sorted(columns)
RES["humaneval0_scores"] = {
    lab: {"per_reward": {nm: per[nm][i] for nm in prepared.names},
          "trl_total": round(sum(w * per[nm][i] for w, nm in zip(prepared.weights, prepared.names)), 4)}
    for i, lab in enumerate(completions)}

# The MBPP example's reward on MBPP rows, with the test_list column TRL would pass.
types = RES.get("mbpp_example_reward_types") or ["code_quality"]
ex_prep = prepare_trl_rewards([{"type": tp, "weight": 1.0, "params": {}} for tp in types])
mb = {}
for t in [t for t in TASKS if t["task_id"].startswith("MBPP/")]:
    rc = t["raw_columns"]
    cands = {"reference, bare": t["reference_solution"], "reference, fenced": fence(t["reference_solution"]),
             "stub, fenced": fence(tmpl("stub", t["entry_point"])), "prose": tmpl("prose", t["entry_point"]), "empty": ""}
    cols = {k: [v] * len(cands) for k, v in rc.items() if k not in ("prompt",)}
    mb[t["task_id"]] = {lab: s for lab, s in zip(cands, ex_prep.functions[0](
        prompts=[rc["prompt"]] * len(cands), completions=list(cands.values()), completion_ids=None, **cols, **extras))}
RES["mbpp_example_scores"] = mb
OUT.mkdir(parents=True, exist_ok=True)
(OUT / f"{LABEL}-recipe.json").write_text(json.dumps(RES, indent=1, default=str))
print(json.dumps({k: RES[k] for k in RES if k not in ("humaneval0_scores", "mbpp_example_scores")}, indent=1, default=str)[:3000])
for k, v in RES["humaneval0_scores"].items():
    print(f"{k:55s} {v}")
print(json.dumps(mb, indent=1)[:1500])
