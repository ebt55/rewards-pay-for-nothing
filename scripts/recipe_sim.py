"""Recipe simulation (no model): score completions for one HumanEval row exactly as AlignTune's TRL
GRPO backend would, using the shipped recipe deepseek_humaneval.yaml.

Path being simulated (aligntune 0.1.28, trl 1.7.1):
  recipe YAML -> config.rewards -> TrainerBase.setup_rewards -> prepare_trl_rewards
  -> RewardBridge.wrap_registry_reward (one TRL batch function per reward)
  -> trl GRPOTrainer._calculate_rewards: reward_func(prompts=, completions=, completion_ids=,
     **{every dataset column except prompt/completion/completion_ids}, trainer_state=, log_extra=, log_metric=)
  -> total = sum_i reward_weights[i] * r_i   (reward_weights = the YAML weights)

Also simulates examples/grpo_code_gen_trl_mbpp.py's reward wiring on MBPP rows.
Writes results/recipe_sim.json.
"""
import importlib.resources as ir
import json
import pathlib
import sys
import traceback

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASKS = json.loads((ROOT / "exploits" / "tasks.json").read_text())
EX = json.loads((ROOT / "exploits" / "exploits.json").read_text())
OUT = {}


def tmpl(ex_id, fn):
    for e in EX["exploits"]:
        if e["id"] == ex_id:
            return e["template"].replace("{fn}", fn)
    return EX["special"][ex_id].replace("{fn}", fn)


def fence(s):
    return "```python\n" + s + "\n```"


# ---------------------------------------------------------------- 1. the recipe as shipped
recipe_path = ir.files("aligntune") / "recipes" / "configs" / "grpo" / "deepseek_humaneval.yaml"
recipe = yaml.safe_load(recipe_path.read_text())
cfg = recipe["config"]
OUT["recipe_file"] = str(recipe_path)
OUT["recipe_rewards"] = cfg["rewards"]
OUT["recipe_dataset"] = cfg["datasets"][0]

# ---------------------------------------------------------------- 2. can the recipe's dataset load?
from aligntune.data.manager import DataManager  # noqa: E402

def try_manager(name):
    try:
        dm = DataManager(task_type="grpo", column_mapping=cfg["datasets"][0].get("column_mapping"), tokenizer=None)
        dd = dm.load_dataset(name, split=cfg["datasets"][0]["split"])
        ds = dd[cfg["datasets"][0]["split"]]
        return {"ok": True, "rows": len(ds), "columns": ds.column_names, "row0": {k: (str(v)[:300]) for k, v in ds[0].items()}}, ds
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:500]}", "tb_tail": traceback.format_exc()[-800:]}, None

OUT["datamanager_recipe_name"], _ = try_manager(cfg["datasets"][0]["name"])
OUT["datamanager_real_humaneval"], ds = try_manager("openai/openai_humaneval")

if ds is not None:
    row = dict(ds[0])  # HumanEval/0 as the trainer would see it
    OUT["row_source"] = "DataManager(task_type=grpo, column_mapping={'text': 'prompt'}) on openai/openai_humaneval, row 0"
else:
    from datasets import load_dataset
    row = dict(load_dataset("openai/openai_humaneval", split="test")[0])
    OUT["row_source"] = "raw openai/openai_humaneval row 0 (DataManager failed; see above)"

# ---------------------------------------------------------------- 3. score completions as TRL would
from aligntune.core.rl.reward_handler import prepare_trl_rewards  # noqa: E402

prepared = prepare_trl_rewards(cfg["rewards"])
OUT["prepared_names"] = prepared.names
OUT["prepared_weights"] = prepared.weights

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

# Instrument: record which kwargs each underlying compute() receives.
seen_kwargs = {}
for name, f in zip(prepared.names, prepared.functions):
    scorer = f.__wrapped__
    owner = scorer.__self__

    def make_spy(orig, nm):
        def spy(text, reference=None, **kw):
            seen_kwargs.setdefault(nm, {"reference": None if reference is None else str(reference)[:120],
                                        "kwarg_keys": sorted(kw.keys()),
                                        "test_cases_in_kwargs": "test_cases" in kw})
            return orig(text, reference, **kw)
        return spy
    owner.compute = make_spy(owner.compute, name)
# Rebuild wrappers so they call the spied compute (wrap_registry_reward binds compute at wrap time).
from aligntune.core.rl.reward_handler import RewardBridge  # noqa: E402
funcs = [RewardBridge.wrap_registry_reward(f.__wrapped__.__self__, n) for f, n in zip(prepared.functions, prepared.names)]

texts = list(completions.values())
n = len(texts)
columns = {k: [v] * n for k, v in row.items() if k not in ("prompt", "completion", "completion_ids")}
trl_extras = {"trainer_state": None, "log_extra": lambda *a, **k: None, "log_metric": lambda *a, **k: None}
per_func = {}
for name, f in zip(prepared.names, funcs):
    per_func[name] = f(prompts=[row.get("prompt", "")] * n, completions=texts, completion_ids=None, **columns, **trl_extras)
OUT["columns_passed_as_kwargs"] = sorted(columns.keys()) + sorted(trl_extras.keys())
OUT["seen_by_compute"] = seen_kwargs
table = {}
for i, label in enumerate(completions):
    parts = {nm: per_func[nm][i] for nm in prepared.names}
    total = sum(w * parts[nm] for w, nm in zip(prepared.weights, prepared.names))
    table[label] = {"per_reward": parts, "trl_total": round(total, 4)}
OUT["humaneval0_scores"] = table

# Same row, but with the tests handed over the way the rewards read them (what the recipe would need).
asserts = he0["assert_tests"]
fixed = {}
for name, f in zip(prepared.names, funcs):
    tc = he0["dict_tests"] if name == "code_correctness" else asserts
    fixed[name] = f(prompts=[row.get("prompt", "")] * n, completions=texts, completion_ids=None,
                    **{**columns, "test_cases": [tc] * n}, **trl_extras)
OUT["humaneval0_scores_if_test_cases_column_existed"] = {
    label: {"per_reward": {nm: fixed[nm][i] for nm in prepared.names},
            "trl_total": round(sum(w * fixed[nm][i] for w, nm in zip(prepared.weights, prepared.names)), 4)}
    for i, label in enumerate(completions)}

# ---------------------------------------------------------------- 4. examples/grpo_code_gen_trl_mbpp.py wiring
example_rewards = [{"type": "code_quality", "weight": 1.0, "params": {}}]  # copied from the example (GitHub main)
ex_prep = prepare_trl_rewards(example_rewards)
mb = [t for t in TASKS if t["task_id"].startswith("MBPP/")]
ex_out = {}
for t in mb:
    rc = t["raw_columns"]
    cands = {"reference, bare": t["reference_solution"], "reference, fenced": fence(t["reference_solution"]),
             "stub, bare": tmpl("stub", t["entry_point"]), "prose": tmpl("prose", t["entry_point"]), "empty": ""}
    cols = {k: [v] * len(cands) for k, v in rc.items() if k not in ("prompt",)}
    with_tests = ex_prep.functions[0](prompts=[rc["prompt"]] * len(cands), completions=list(cands.values()), completion_ids=None, **cols, **trl_extras)
    no_tests = ex_prep.functions[0](prompts=[rc["prompt"]] * len(cands), completions=list(cands.values()), completion_ids=None, **trl_extras)
    ex_out[t["task_id"]] = {lab: {"with_test_list_column": a, "without_any_columns": b} for lab, a, b in zip(cands, with_tests, no_tests)}
OUT["mbpp_example_rewards"] = example_rewards
OUT["mbpp_example_scores"] = ex_out

OUT_PATH = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "recipe_sim.json"
OUT_PATH.write_text(json.dumps(OUT, indent=1, default=str))
print(json.dumps({k: OUT[k] for k in ["recipe_rewards", "recipe_dataset", "prepared_weights", "columns_passed_as_kwargs", "seen_by_compute"]}, indent=1, default=str))
print("datamanager_recipe_name:", json.dumps(OUT["datamanager_recipe_name"], default=str)[:700])
print("datamanager_real_humaneval:", json.dumps({k: v for k, v in OUT["datamanager_real_humaneval"].items() if k != "row0"}, default=str)[:700])
for k, v in table.items():
    print(f"{k:55s} {v}")
print("--- if test_cases existed")
for k, v in OUT["humaneval0_scores_if_test_cases_column_existed"].items():
    print(f"{k:55s} {v}")
print("--- mbpp example (code_quality only)")
for tid, v in ex_out.items():
    print(tid, json.dumps(v))
