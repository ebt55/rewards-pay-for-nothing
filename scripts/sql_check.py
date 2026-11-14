"""AlignTune sql_verifiable (SQLVerifiableReward): what does it pay for? Registry default params
(execute=False), and execute=True on an in-memory SQLite db. Reference = an expected result."""
import json
from aligntune.rewards.registry import RewardRegistry as R
cands = {"correct-looking query": "SELECT name FROM users WHERE age > 30;", "SELECT 1": "SELECT 1",
         "prose": "I am not able to write this query right now.", "single word": "users", "empty": ""}
out = {}
for execute in (False, True):
    r = R.get_reward_function("sql_verifiable", {"type": "sql_verifiable", "weight": 1.0, "params": {"execute": execute, "db_path": ":memory:"}})
    out[f"execute={execute}"] = {k: r.compute(v, "[('alice',), ('bob',)]") for k, v in cands.items()}
print(json.dumps(out))
