"""Does a deeply nested completion make a reward raise, and does that end a TRL run? (our code, MIT)

1. mbpp_reward through AlignTune's RewardBridge and TRL 1.7.1's GRPOTrainer._calculate_rewards
   (stand-in trainer, CPU, no model), tests in the `test_cases` column, 3-completion batch.
2. The counterfactual-GRPO code reward, called as Gate 1 calls it (unbound, stand-in prompt_to_data).
The middle completion is a fenced block holding a 20,000-deep attribute chain (`x.a.a.a...`).

Usage: python scripts/pr40_crash_driver.py <none|deep> <mbpp_bridge|counterfact>
Prints BEFORE, then AFTER only if control returns. The shell records the exit status.
"""
import json
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pr40_common import ROOT, use_pr  # noqa: E402

print("aligntune.rewards.core from:", use_pr(), flush=True)
variant, path = sys.argv[1], sys.argv[2]
t = next(x for x in json.loads((ROOT / "exploits" / "tasks.json").read_text()) if x["task_id"] == "MBPP/3")
fn = t["entry_point"]
stub = f"```python\ndef {fn}(*args, **kwargs):\n    pass\n```"
middle = stub if variant == "none" else "```python\nx" + ".a" * 20000 + "\n```"
completions = [stub, middle, stub]
print("BEFORE", flush=True)
if path == "mbpp_bridge":
    import torch  # noqa: F401
    from trl import GRPOTrainer
    from aligntune.core.rl.reward_handler import prepare_trl_rewards
    prep = prepare_trl_rewards([{"type": "mbpp_reward", "weight": 1.0, "params": {}}])
    fake = SimpleNamespace(accelerator=SimpleNamespace(device="cpu", is_main_process=True), reward_funcs=prep.functions,
                           reward_processing_classes=[None], reward_func_names=prep.names, environments=None,
                           state=SimpleNamespace(global_step=0), args=SimpleNamespace(report_to=[]),
                           _log_completion_extra=lambda *a, **k: None, _log_metric=lambda *a, **k: None, async_loop=None)
    row = {"prompt": "p", "test_cases": t["assert_tests"]}
    out = GRPOTrainer._calculate_rewards(fake, [row] * 3, ["p"] * 3, completions, [[0]] * 3).tolist()
else:
    from aligntune.backends.trl.rl.counterfact_grpo.counterfact_grpo import TRLCounterFactGRPOTrainer
    p = "PROMPT::MBPP/3"
    fake = SimpleNamespace(prompt_to_data={p: {"tests": t["assert_tests"], "setup": "", "expected_func": fn}})
    out = TRLCounterFactGRPOTrainer._compute_code_rewards(fake, completions, prompts=[p] * 3)
print("AFTER:", out, flush=True)
print("TRAINING LOOP WOULD CONTINUE", flush=True)
