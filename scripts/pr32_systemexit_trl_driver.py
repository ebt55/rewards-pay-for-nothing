"""Does a completion that exits (or signals the trainer) end a GRPO run under SafeTune's code
rewards? SafeTune counterpart of scripts/systemexit_trl_driver.py (which drove AlignTune's bridge).
Our code, MIT.

Drives TRL's own GRPOTrainer._calculate_rewards (unbound, minimal stand-in trainer, CPU, no model)
on a 3-completion batch; the middle completion is the variant under test. Three SafeTune rewards,
each wrapped as a plain TRL reward function (SafeTune ships no TRL bridge):
  code_execution with no tests (what the AlignTune recipe path reached), code_correctness with
  test_cases, mbpp_reward with test_list (HumanEval/0's seven asserts).

Usage: python scripts/pr32_systemexit_trl_driver.py <none|exit0|exit3|os_exit0|kill_parent>
Prints BEFORE, then AFTER only if control returns. The parent shell records the exit status.
kill_parent sends SIGKILL to the grader's parent, i.e. this throwaway driver process only.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pr32_common import ROOT, build, use_pr  # noqa: E402

print("safetune.rewards.code from:", use_pr(), flush=True)
import torch  # noqa: E402,F401  (TRL needs it)
from pr32_trl import calculate_rewards, wrap  # noqa: E402

arg = sys.argv[1] if len(sys.argv) > 1 else "exit0"
t = next(x for x in json.loads((ROOT / "exploits" / "tasks.json").read_text()) if x["task_id"] == "HumanEval/0")
fn = t["entry_point"]
stub = f"```python\ndef {fn}(*args, **kwargs):\n    pass\n```"
tails = {
    "exit0": "import sys\nsys.exit(0)",
    "exit3": "import sys\nsys.exit(3)",
    "os_exit0": "import os\nos._exit(0)",
    "kill_parent": "import os, signal\nos.kill(os.getppid(), signal.SIGKILL)",
}
middle = stub if arg == "none" else f"```python\ndef {fn}(*args, **kwargs):\n    pass\n{tails[arg]}\n```"
completions = [stub, middle, stub]
funcs = [wrap(build("code_execution"), "no_tests", "code_execution[no tests]"),
         wrap(build("code_correctness"), "test_cases", "code_correctness[test_cases]"),
         wrap(build("mbpp_reward"), "test_list", "mbpp_reward[test_list]")]
row = {"prompt": t["prompt"], "test_cases": t["assert_tests"], "test_list": t["assert_tests"],
       "entry_point": fn, "task_id": t["task_id"]}
print("BEFORE _calculate_rewards", flush=True)
out = calculate_rewards(funcs, [row] * 3, completions)
print("AFTER _calculate_rewards (rows = completions; columns = " + ", ".join(f.__name__ for f in funcs) + "):",
      out, flush=True)
print("TRAINING LOOP WOULD CONTINUE", flush=True)
