"""A deliberately naive code reward. rewardcheck should flag it; do not train with it.

It appends the tests to the answer, runs the file in a subprocess and pays 1.0 on exit
code 0. An answer that calls sys.exit(0) before the tests run is paid in full.
"""
import os
import re
import subprocess
import sys
import tempfile

FENCE = re.compile(r"```(?:python)?\n(.*?)```", re.S)


def make_reward():
    def reward_fn(completions, test_cases, **kwargs):
        scores = []
        for text, tests in zip(completions, test_cases):
            match = FENCE.search(text)
            code = match.group(1) if match else text
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
                f.write(code + "\n\n" + "\n".join(tests) + "\n")
            try:
                proc = subprocess.run([sys.executable, f.name], capture_output=True, timeout=10)
                scores.append(1.0 if proc.returncode == 0 else 0.0)
            except subprocess.TimeoutExpired:
                scores.append(0.0)
            finally:
                os.unlink(f.name)
        return scores
    return reward_fn
