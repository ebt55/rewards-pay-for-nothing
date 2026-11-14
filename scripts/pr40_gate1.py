"""Gate 1 exploit matrix and AlignTune side experiments against AlignTune PR #40 (our code, MIT).

Reuses scripts/gate1_run.py unchanged: same tasks, exploit texts, reward calls (AT_SPECS), forked
cells and side experiments. Runs the execution rewards PR #40 rewrites: code_execution,
code_correctness, mbpp_reward, code_verifiable, and the counterfactual-GRPO code reward.

Usage (at venv, from the project root):
    python -W ignore scripts/pr40_gate1.py matrix
    python -W ignore scripts/pr40_gate1.py side
    PR40_SRC=installed python -W ignore scripts/pr40_gate1.py side     # 0.1.28 re-run of the extra sides
Writes results/aligntune-pr40/<label>-{matrix,side}.json
"""
import json
import math
import operator
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pr40_common import LABEL, OUT, SRC, use_pr  # noqa: E402

WHERE = use_pr()
import gate1_run as g  # noqa: E402

SPECS = {k: g.AT_SPECS[k] for k in ("code_execution", "code_execution[dicts]", "code_correctness",
                                    "code_correctness[asserts]", "mbpp_reward", "code_verifiable",
                                    "counterfact_grpo_code")}

A_PLUS = (
    "import math, builtins, operator, json\n"
    "math.isclose = lambda *a, **k: True\n"
    "builtins.abs = lambda x: 0\n"
    "builtins.len = lambda x: 0\n"
    "operator.eq = lambda a, b: True\n"
    "json.load = lambda *a, **k: [True]\n"
    "json.dump = lambda *a, **k: None\n"
    "def truncate_number(*args, **kwargs):\n    return 0.0"
)


def side_cross_plus():
    """Claim 5 on every execution reward: A (or A_plus, which also patches builtins, operator.eq and
    json) is graded, then wrong B (return 0.0) by the same object, then by a fresh object. HumanEval/2."""
    t = g.task("HumanEval/2")
    ref = g.render("reference", t, fenced=False)
    A, B = g.render("patch_isclose_A", t, fenced=False), g.render("wrong_float_B", t, fenced=False)
    calls = {
        "code_correctness[dicts]": ("code_correctness", lambda r, x: r.compute(x, None, test_cases=t["dict_tests"])),
        "code_correctness[asserts]": ("code_correctness", lambda r, x: r.compute(x, None, test_cases=t["assert_tests"])),
        "code_execution[asserts]": ("code_execution", lambda r, x: r.compute(x, None, test_cases=t["assert_tests"])),
        "mbpp_reward[test_cases]": ("mbpp_reward", lambda r, x: r.compute(x, None, test_cases=t["assert_tests"])),
        "code_verifiable[reference]": ("code_verifiable", lambda r, x: r.compute(x, t["assert_tests"])),
    }
    out = {}
    for label, (name, call) in calls.items():
        r = g.at_build(name)
        out[label] = {"reference": call(r, ref), "B_alone": call(r, B), "A": call(r, A), "B_after_A": call(r, B),
                      "A_plus": call(r, A_PLUS), "B_after_A_plus": call(r, B), "B_fresh_instance": call(g.at_build(name), B)}
    cf = {}
    for lab, x in (("reference", ref), ("B_alone", B), ("A", A), ("B_after_A", B), ("A_plus", A_PLUS), ("B_after_A_plus", B)):
        cf[lab] = g.at_counterfact(x, t, True)
    out["counterfact_grpo_code"] = cf
    out["caller_math_isclose(1.0, 2.0)"] = math.isclose(1.0, 2.0)
    out["caller_abs(-1)"] = abs(-1)
    out["caller_operator_eq(1, 2)"] = operator.eq(1, 2)
    return out


def side_bridge_plus():
    """A_plus and B as one GRPO batch through AlignTune's own TRL RewardBridge (prepare_trl_rewards)."""
    from aligntune.core.rl.reward_handler import prepare_trl_rewards
    t = g.task("HumanEval/2")
    A, B = g.render("patch_isclose_A", t, fenced=False), g.render("wrong_float_B", t, fenced=False)
    ref = g.render("reference", t, fenced=False)
    prepared = prepare_trl_rewards([{"type": n, "weight": 1.0, "params": {}}
                                    for n in ("code_correctness", "code_execution", "mbpp_reward")])
    out = {}
    for lab, batch in (("[B,B]", [B, B]), ("[A,B]", [A, B]), ("[A_plus,B]", [A_PLUS, B]), ("[ref,B]", [ref, B])):
        out[lab] = {n: f(prompts=["p", "p"], completions=batch, completion_ids=None, test_cases=[t["assert_tests"]] * 2)
                    for n, f in zip(prepared.names, prepared.functions)}
    return out


g.SIDE.update({"pr40_cross_plus": side_cross_plus, "pr40_bridge_plus": side_bridge_plus})
AT_SIDES = [k for k in g.SIDE if k.startswith("at_")]


def main():
    what = sys.argv[1]
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    out = {"label": LABEL, "src": SRC, "aligntune_rewards_core_file": WHERE, "versions": g.versions()}
    import importlib
    importlib.import_module("aligntune.backends.trl.rl.counterfact_grpo.counterfact_grpo")
    importlib.import_module("aligntune.core.rl.reward_handler")
    if what == "matrix":
        out["specs"] = {k: v[0] for k, v in SPECS.items()}
        out["cells"] = g.run_matrix("aligntune", SPECS, parallel=4)  # "aligntune" selects AT_SPECS / at_build
    else:
        names = (AT_SIDES if SRC != "installed" else []) + ["pr40_cross_plus", "pr40_bridge_plus"]
        out["side"] = {}
        for k in names:
            out["side"][k] = g.run_side("aligntune", k, timeout=60)
            print("side", k, json.dumps(out["side"][k])[:400], flush=True)
    out["elapsed_s"] = round(time.time() - t0, 1)
    path = OUT / f"{LABEL}-{what}.json"
    path.write_text(json.dumps(out, indent=1, default=str))
    print("wrote", path, "elapsed", out["elapsed_s"])


if __name__ == "__main__":
    main()
