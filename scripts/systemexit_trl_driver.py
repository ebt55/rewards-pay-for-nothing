"""Does a completion that calls sys.exit() end a GRPO run? Drives TRL 1.7.1's own
GRPOTrainer._calculate_rewards (unbound, on a minimal stand-in trainer, CPU, no model) with the
recipe's code_execution reward wrapped by AlignTune's RewardBridge, on a 3-completion batch whose
middle completion is benign `sys.exit(<code>)`.

Usage: python scripts/systemexit_trl_driver.py <exit_code|none>
Prints BEFORE, then AFTER only if control returns to the trainer. The parent shell records the
process exit status (see run_all.sh / results).
"""
import sys
from types import SimpleNamespace

import torch  # noqa: F401  (TRL needs it)
from trl import GRPOTrainer

from aligntune.core.rl.reward_handler import prepare_trl_rewards

arg = sys.argv[1] if len(sys.argv) > 1 else "0"
fn = "has_close_elements"
stub = f"```python\ndef {fn}(*args, **kwargs):\n    pass\n```"
middle = stub if arg == "none" else f"```python\nimport sys\ndef {fn}(*args, **kwargs):\n    pass\nsys.exit({arg})\n```"
completions = [stub, middle, stub]

prepared = prepare_trl_rewards([{"type": "code_execution", "weight": 0.2, "params": {}}])  # recipe's entry
fake = SimpleNamespace(
    accelerator=SimpleNamespace(device="cpu", is_main_process=True),
    reward_funcs=prepared.functions,
    reward_processing_classes=[None],
    reward_func_names=prepared.names,
    environments=None,
    state=SimpleNamespace(global_step=0),
    args=SimpleNamespace(report_to=[]),
    _log_completion_extra=lambda *a, **k: None,
    _log_metric=lambda *a, **k: None,
    async_loop=None,
)
row = {"prompt": "from typing import List\n\ndef has_close_elements(numbers, threshold):\n", "test": "def check(candidate): ...",
       "entry_point": fn, "task_id": "HumanEval/0"}
print("BEFORE _calculate_rewards", flush=True)
out = GRPOTrainer._calculate_rewards(fake, [row] * 3, [row["prompt"]] * 3, completions, [[0]] * 3)
print("AFTER _calculate_rewards:", out.tolist(), flush=True)
print("TRAINING LOOP WOULD CONTINUE", flush=True)
