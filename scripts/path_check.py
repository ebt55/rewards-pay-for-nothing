"""Several rewards launch tests with subprocess ['python', file] (bare name, resolved via PATH).
Score the fenced MBPP/3 reference with tests supplied, once with the venv's bin on PATH and once
without it (stock Ubuntu 24.04 has no `python`, only `python3`). Run with the venv interpreter by
absolute path; run_all.sh does both."""
import json, os, pathlib, shutil, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
t = next(x for x in json.loads((ROOT / "exploits" / "tasks.json").read_text()) if x["task_id"] == "MBPP/3")
ref = "```python\n" + t["reference_solution"] + "\n```"
pkg = sys.argv[1]
out = {"pkg": pkg, "python_on_PATH": shutil.which("python"), "PATH_head": os.environ.get("PATH", "")[:80]}
if pkg == "aligntune":
    from aligntune.rewards.registry import RewardRegistry as R
    b = lambda n: R.get_reward_function(n, {"type": n, "weight": 1.0, "params": {}})
    out["code_execution(asserts)"] = b("code_execution").compute(ref, None, test_cases=t["assert_tests"])
    out["mbpp_reward(asserts) [uses sys.executable]"] = b("mbpp_reward").compute(ref, None, test_cases=t["assert_tests"])
    out["code_verifiable(asserts) [uses /usr/bin/python3]"] = b("code_verifiable").compute(ref, t["assert_tests"])
else:
    from safetune.rewards.registry import RewardRegistry as R
    b = lambda n: R.get_reward_function(n, {"type": n, "weight": 1.0, "params": {}})
    out["code_execution(asserts)"] = b("code_execution").compute(ref, None, test_cases=t["assert_tests"])
    out["mbpp_reward(test_list)"] = b("mbpp_reward").compute(ref, None, test_list=t["assert_tests"])
print(json.dumps(out))
