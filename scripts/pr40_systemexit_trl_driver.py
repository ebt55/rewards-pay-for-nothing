"""Does a completion that exits (or signals the trainer) end a GRPO run under AlignTune's code
rewards? Extended version of scripts/systemexit_trl_driver.py for the PR #40 check (our code, MIT).

Same path as the original: AlignTune's TRL RewardBridge (prepare_trl_rewards) driven by TRL 1.7.1's own
GRPOTrainer._calculate_rewards on a minimal stand-in trainer (CPU, no model), 3-completion batch,
middle completion varied. Four rewards: the recipe's code_execution entry (weight 0.2, no tests in the
row's columns) plus code_correctness, mbpp_reward and code_verifiable, which get HumanEval/0's `test`
and `entry_point` columns.

Usage: python scripts/pr40_systemexit_trl_driver.py <none|exit0|exit3|os_exit0|kill_parent>
kill_parent sends SIGKILL to the grader's parent: this throwaway driver process only.
"""
import json
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pr40_common import ROOT, use_pr  # noqa: E402

print("aligntune.rewards.core from:", use_pr(), flush=True)
import torch  # noqa: E402,F401
from trl import GRPOTrainer  # noqa: E402

from aligntune.core.rl.reward_handler import prepare_trl_rewards  # noqa: E402

arg = sys.argv[1] if len(sys.argv) > 1 else "exit0"
t = next(x for x in json.loads((ROOT / "exploits" / "tasks.json").read_text()) if x["task_id"] == "HumanEval/0")
raw = t["raw_columns"]
fn = t["entry_point"]
stub = f"```python\ndef {fn}(*args, **kwargs):\n    pass\n```"
tails = {"exit0": "import sys\nsys.exit(0)", "exit3": "import sys\nsys.exit(3)", "os_exit0": "import os\nos._exit(0)",
         "kill_parent": "import os, signal\nos.kill(os.getppid(), signal.SIGKILL)"}
middle = stub if arg == "none" else f"```python\ndef {fn}(*args, **kwargs):\n    pass\n{tails[arg]}\n```"
completions = [stub, middle, stub]

code_exec = prepare_trl_rewards([{"type": "code_execution", "weight": 0.2, "params": {}}])  # recipe's entry
tested = prepare_trl_rewards([{"type": n, "weight": 1.0, "params": {}} for n in ("code_correctness", "mbpp_reward", "code_verifiable")])
funcs = code_exec.functions + tested.functions
names = ["code_execution[no tests]"] + [n + "[test+entry_point]" for n in tested.names]
fake = SimpleNamespace(
    accelerator=SimpleNamespace(device="cpu", is_main_process=True),
    reward_funcs=funcs,
    reward_processing_classes=[None] * len(funcs),
    reward_func_names=names,
    environments=None,
    state=SimpleNamespace(global_step=0),
    args=SimpleNamespace(report_to=[]),
    _log_completion_extra=lambda *a, **k: None,
    _log_metric=lambda *a, **k: None,
    async_loop=None,
)
# code_execution must see no tests (as in Gate 1's recipe path); the others read test + entry_point.
row = {"prompt": raw["prompt"], "task_id": t["task_id"]}
cols_tested = {"test": raw["test"], "entry_point": fn}


def tested_only(f):
    def g(prompts, completions, completion_ids=None, **kw):
        return f(prompts=prompts, completions=completions, completion_ids=completion_ids,
                 **{**kw, **{k: [v] * len(completions) for k, v in cols_tested.items()}})
    g.__name__ = getattr(f, "__name__", "f")
    return g


fake.reward_funcs = [funcs[0]] + [tested_only(f) for f in funcs[1:]]
print("BEFORE _calculate_rewards", flush=True)
out = GRPOTrainer._calculate_rewards(fake, [row] * 3, [row["prompt"]] * 3, completions, [[0]] * 3)
print("AFTER _calculate_rewards (rows = completions; columns = " + ", ".join(names) + "):", out.tolist(), flush=True)
print("TRAINING LOOP WOULD CONTINUE", flush=True)
