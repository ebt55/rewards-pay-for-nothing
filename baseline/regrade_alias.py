"""Diagnostic re-grade (no new generation): how much of the failure is only the function name?

For every completion that failed with NameError on the name the tests call, try aliasing each
top-level function the completion defines to that name (`expected = defined`) and re-run the
same grader. Counts a pass if any alias passes. This is an upper bound on "right logic, wrong
name"; it is NOT a reward anyone should train on.
"""
import ast
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from grader import extract_code, grade


def expected_name(test):
    m = re.search(r"assert\s+(?:not\s+)?\(?\s*(?:set\(|math\.isclose\()?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", test)
    return m.group(1) if m else None


def regrade(rec, row):
    if rec["passed"]:
        return True
    if rec["kind"] != "NameError":
        return False
    exp = expected_name(row["test_list"][0])
    if not exp or f"'{exp}'" not in rec["detail"]:
        return False
    code = extract_code(rec["text"])
    if code is None:
        return False
    try:
        defs = [n.name for n in ast.parse(code).body if isinstance(n, ast.FunctionDef)]
    except SyntaxError:
        return False
    for d in defs:
        aliased = f"```python\n{code}\n\n{exp} = {d}\n```"
        if grade(aliased, row["test_list"], row["test_imports"])["passed"]:
            return True
    return False


def main(path):
    from datasets import load_dataset
    d = json.load(open(path, encoding="utf-8"))
    ds = load_dataset("google-research-datasets/mbpp", "sanitized", split="test")
    rows = {r["task_id"]: r for r in ds}
    jobs = []
    for t in d["per_task"]:
        row = rows[t["task_id"]]
        jobs.append((t["task_id"], "greedy", t["greedy"], row))
        for s in t["samples"]:
            jobs.append((t["task_id"], "sample", s, row))
    with ThreadPoolExecutor(16) as ex:
        res = list(ex.map(lambda j: regrade(j[2], j[3]), jobs))
    n = len(d["per_task"])
    greedy = sum(r for j, r in zip(jobs, res) if j[1] == "greedy")
    counts = {}
    for j, r in zip(jobs, res):
        if j[1] == "sample":
            counts[j[0]] = counts.get(j[0], 0) + int(r)
    c = list(counts.values())
    k = len(d["per_task"][0]["samples"])
    out = {"file": path, "alias_pass_at_1_greedy": greedy / n, "alias_pass_at_8": sum(x > 0 for x in c) / n,
           "alias_mean_per_sample": sum(c) / (n * k), "alias_mixed_fraction": sum(0 < x < k for x in c) / n,
           "alias_histogram_0_to_8": [c.count(i) for i in range(k + 1)]}
    print(json.dumps(out))
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        main(p)
