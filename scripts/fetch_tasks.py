"""Fetch the 5 benchmark tasks used by Gate 1 and write exploits/tasks.json.

Sources (both public, ungated, Hugging Face datasets):
  - google-research-datasets/mbpp, config "sanitized"
  - openai/openai_humaneval
Run once (needs network); everything after this reads exploits/tasks.json only.
"""
import ast, json, pathlib, re
from datasets import load_dataset

ROOT = pathlib.Path(__file__).resolve().parents[1]
MBPP_IDS = [3, 4, 11]
HE_IDS = ["HumanEval/0", "HumanEval/2"]


def parse_call_assert(line):
    """'assert f(a, b) == c' -> (fn, [a, b], c) when every piece is a literal, else None."""
    try:
        node = ast.parse(line.strip()).body[0]
    except SyntaxError:
        return None
    if not isinstance(node, ast.Assert):
        return None
    t = node.test
    # 'assert abs(f(x) - y) < eps' -> treated as f(x) == y (dict tests compare floats with math.isclose)
    if (isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.Lt)
            and isinstance(t.left, ast.Call) and getattr(t.left.func, "id", None) == "abs"
            and isinstance(t.left.args[0], ast.BinOp) and isinstance(t.left.args[0].op, ast.Sub)):
        call, exp = t.left.args[0].left, t.left.args[0].right
        try:
            return call.func.id, [ast.literal_eval(a) for a in call.args], ast.literal_eval(exp)
        except Exception:
            return None
    if not (isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.Eq)):
        return None
    call, exp = t.left, t.comparators[0]
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        return None
    try:
        args = [ast.literal_eval(a) for a in call.args]
        expected = ast.literal_eval(exp)
    except Exception:
        return None
    return call.func.id, args, expected


def dict_test(args, expected):
    # AlignTune CodeCorrectnessReward / SafeTune dict tests call f(*input) when input is a
    # list/tuple with len > 1, else f(input). One-argument tasks therefore pass the bare value.
    inp = args if len(args) > 1 else args[0]
    return {"input": inp, "expected_output": expected}


def docstring_examples(prompt, fn):
    """HumanEval docstring '>>> fn(args)\n    result' pairs (the only tests a model sees)."""
    out = []
    lines = prompt.splitlines()
    for i, l in enumerate(lines):
        s = l.strip()
        if s.startswith(">>> " + fn + "(") and i + 1 < len(lines):
            try:
                call = ast.parse(s[4:]).body[0].value
                args = [ast.literal_eval(a) for a in call.args]
                res = ast.literal_eval(lines[i + 1].strip())
                out.append({"args": args, "expected": res})
            except Exception:
                pass
    return out


tasks = []
mb = {}
for split in ["train", "test", "validation", "prompt"]:
    for r in load_dataset("google-research-datasets/mbpp", "sanitized", split=split):
        mb[r["task_id"]] = (split, r)
for tid in MBPP_IDS:
    split, r = mb[tid]
    asserts = list(r["test_list"])
    parsed = [parse_call_assert(a) for a in asserts]
    fn = parsed[0][0]
    tasks.append({
        "task_id": f"MBPP/{tid}", "source": "google-research-datasets/mbpp (sanitized, split=%s)" % split,
        "entry_point": fn, "prompt": r["prompt"],
        "reference_solution": r["code"],
        "setup_code": "\n".join(r.get("test_imports") or []),
        "assert_tests": asserts,
        "dict_tests": [dict_test(p[1], p[2]) for p in parsed if p],
        # MBPP's standard prompt shows the test asserts to the model, so all of them are "visible".
        "visible_examples": [{"args": p[1], "expected": p[2]} for p in parsed if p],
        "raw_columns": {k: r[k] for k in r.keys()},
    })

he = {r["task_id"]: r for r in load_dataset("openai/openai_humaneval", split="test")}
for tid in HE_IDS:
    r = he[tid]
    fn = r["entry_point"]
    # Single-line asserts inside check(candidate), rewritten to call the entry point directly.
    asserts = [l.strip().replace("candidate(", fn + "(") for l in r["test"].splitlines() if l.strip().startswith("assert ")]
    parsed = [parse_call_assert(a) for a in asserts]
    tasks.append({
        "task_id": tid, "source": "openai/openai_humaneval (split=test)",
        "entry_point": fn, "prompt": r["prompt"],
        "reference_solution": r["prompt"] + r["canonical_solution"],
        "setup_code": "",
        "assert_tests": asserts,
        "dict_tests": [dict_test(p[1], p[2]) for p in parsed if p],
        "visible_examples": docstring_examples(r["prompt"], fn),
        "raw_columns": {k: r[k] for k in r.keys()},
    })

out = ROOT / "exploits" / "tasks.json"
out.write_text(json.dumps(tasks, indent=2))
for t in tasks:
    print(t["task_id"], t["entry_point"], "asserts=%d dict=%d visible=%d" % (len(t["assert_tests"]), len(t["dict_tests"]), len(t["visible_examples"])))
