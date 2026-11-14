"""securegrade's TRL reward (securegrade/ in this repository), which grades returned values.

It reads tests from `test_list`, the function name from `entry_point` and setup code from
`test_imports`, so run rewardcheck with those column names.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repository root, for `import securegrade`


def make_reward():
    from securegrade.trl_reward import make_secure_code_reward
    return make_secure_code_reward(max_workers=1)
