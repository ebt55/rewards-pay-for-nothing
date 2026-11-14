"""Gate 1 runner: score benign exploit completions with the code rewards shipped in the
installed aligntune / safetune wheels.

Usage (inside the package's venv, from the project root):
    python scripts/gate1_run.py --pkg aligntune --out results/raw_aligntune.json
    python scripts/gate1_run.py --pkg safetune  --out results/raw_safetune.json

Every (reward, mode, task, completion) cell runs in its own forked child process with a hard
timeout, and builds a fresh reward object there. In-process exec() in one cell therefore cannot
change another cell's grade. The cross-completion experiment (claim 5) deliberately shares one
reward object inside one child instead.
"""
import argparse
import contextlib
import importlib
import importlib.metadata as md
import io
import json
import multiprocessing as mp
import os
import pathlib
import sys
import tempfile
import threading
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASKS = json.loads((ROOT / "exploits" / "tasks.json").read_text())
EXDATA = json.loads((ROOT / "exploits" / "exploits.json").read_text())
EXPLOITS = EXDATA["exploits"]
SPECIAL = EXDATA["special"]
SCRATCH = pathlib.Path.home() / "p9" / "tmp"  # rewards' temp files land here, never in the repo
CELL_TIMEOUT = 120
CTX = mp.get_context("fork")


EX_BY_ID = {e["id"]: e for e in EXPLOITS}


def render(ex_id, task, fenced=True):
    """Completion text for one exploit on one task. fenced=True wraps code in a ```python block
    (how chat models usually answer); fenced=False gives the bare code (how a base model continues)."""
    fn = task["entry_point"]
    if ex_id == "reference":
        body = task["reference_solution"].strip()
    else:
        tmpl = EX_BY_ID[ex_id]["template"] if ex_id in EX_BY_ID else SPECIAL[ex_id]
        body = tmpl.replace("{fn}", fn)
        if "{table}" in body:
            table = {repr(tuple(v["args"])): v["expected"] for v in task["visible_examples"]}
            body = body.replace("{table}", repr(table))
    if fenced and EX_BY_ID.get(ex_id, {}).get("fenceable", True):
        return "```python\n" + body + "\n```"
    return body


# --------------------------------------------------------------------------------------
# Reward call specs. Each spec builds the reward through the package's own registry (the same
# path AlignTune's TRL RewardBridge uses) and calls compute() with the test format that
# reward reads. mode "tests": tests supplied in that format. mode "no_tests": nothing supplied.
# --------------------------------------------------------------------------------------

def at_build(name, weight=1.0, params=None):
    from aligntune.rewards.registry import RewardRegistry
    return RewardRegistry.get_reward_function(name, {"type": name, "weight": weight, "params": params or {}})


def st_build(name, weight=1.0, params=None):
    from safetune.rewards.registry import RewardRegistry
    return RewardRegistry.get_reward_function(name, {"type": name, "weight": weight, "params": params or {}})


def at_counterfact(text, task, with_tests):
    """AlignTune's counterfactual-GRPO backend code reward (TRLCounterFactGRPOTrainer._compute_code_rewards),
    called unbound on a stand-in object holding the prompt->tests map the trainer builds."""
    from types import SimpleNamespace
    from aligntune.backends.trl.rl.counterfact_grpo.counterfact_grpo import TRLCounterFactGRPOTrainer
    p = "PROMPT::" + task["task_id"]
    data = {p: {"tests": task["assert_tests"], "setup": task["setup_code"], "expected_func": task["entry_point"]}} if with_tests else {}
    fake = SimpleNamespace(prompt_to_data=data)
    return TRLCounterFactGRPOTrainer._compute_code_rewards(fake, [text], prompts=[p])[0]


AT_SPECS = {
    # name: (description, tests_call, no_tests_call)
    "code_execution": ("CodeExecutionReward; tests=test_cases (assert strings)",
                       lambda r, t, x: r.compute(x, None, test_cases=t["assert_tests"]),
                       lambda r, t, x: r.compute(x)),
    "code_execution[dicts]": ("CodeExecutionReward; tests=test_cases (input/expected_output dicts)",
                              lambda r, t, x: r.compute(x, None, test_cases=t["dict_tests"]),
                              None),
    "code_correctness": ("CodeCorrectnessReward; tests=test_cases (input/expected_output dicts)",
                         lambda r, t, x: r.compute(x, None, test_cases=t["dict_tests"]),
                         lambda r, t, x: r.compute(x)),
    "code_correctness[asserts]": ("CodeCorrectnessReward fed MBPP-style assert strings (the format the other code rewards take)",
                                  lambda r, t, x: r.compute(x, None, test_cases=t["assert_tests"]),
                                  None),
    "mbpp_reward": ("MBPPReward.compute; tests=test_cases (assert strings)",
                    lambda r, t, x: r.compute(x, None, test_cases=t["assert_tests"]),
                    lambda r, t, x: r.compute(x)),
    "code_verifiable": ("CodeExecutionVerifiableReward (RLVR); tests=reference (list of asserts)",
                        lambda r, t, x: r.compute(x, t["assert_tests"]),
                        lambda r, t, x: r.compute(x)),
    "code_syntax": ("CodeSyntaxReward (compile only, no tests)", lambda r, t, x: r.compute(x), None),
    "code_completeness": ("CodeCompletenessReward (regex heuristics, no tests)", lambda r, t, x: r.compute(x), None),
    "code_quality": ("CodeQualityReward (style heuristics, no tests)", lambda r, t, x: r.compute(x), None),
    "counterfact_grpo_code": ("TRL counterfactual-GRPO backend code reward (not in registry)",
                              "special", "special"),
}

ST_SPECS = {
    "code_execution": ("CodeExecutionReward; tests=test_cases (assert strings)",
                       lambda r, t, x: r.compute(x, None, test_cases=t["assert_tests"]),
                       lambda r, t, x: r.compute(x)),
    "code_execution[dicts]": ("CodeExecutionReward; tests=test_cases (input/expected_output dicts)",
                              lambda r, t, x: r.compute(x, None, test_cases=t["dict_tests"]),
                              None),
    "code_correctness": ("CodeCorrectnessReward (alias of CodeExecutionReward); tests=test_cases (asserts)",
                         lambda r, t, x: r.compute(x, None, test_cases=t["assert_tests"]),
                         lambda r, t, x: r.compute(x)),
    "mbpp_reward": ("MBPPReward; tests=test_list (assert strings, MBPP's own column name)",
                    lambda r, t, x: r.compute(x, None, test_list=t["assert_tests"]),
                    lambda r, t, x: r.compute(x)),
    "code_syntax": ("CodeSyntaxReward (compile only)", lambda r, t, x: r.compute(x), None),
    "code_completeness": ("CodeCompletenessReward (regex heuristics)", lambda r, t, x: r.compute(x), None),
    "code_quality": ("CodeQualityReward (style heuristics)", lambda r, t, x: r.compute(x), None),
}


def registry_name(spec_name):
    return spec_name.split("[")[0]


# --------------------------------------------------------------------------------------
# Forked-cell machinery
# --------------------------------------------------------------------------------------

def _child(conn, pkg, spec_name, mode, task, text, tmpdir):
    os.makedirs(tmpdir, exist_ok=True)
    tempfile.tempdir = tmpdir
    os.environ["TMPDIR"] = tmpdir
    buf = io.StringIO()
    t0 = time.time()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            if spec_name == "counterfact_grpo_code":
                score = at_counterfact(text, task, mode == "tests")
            else:
                specs = AT_SPECS if pkg == "aligntune" else ST_SPECS
                build = at_build if pkg == "aligntune" else st_build
                _, tests_call, no_tests_call = specs[spec_name]
                call = tests_call if mode == "tests" else no_tests_call
                r = build(registry_name(spec_name))
                score = call(r, task, text)
        res = {"status": "ok", "score": float(score) if score is not None else None}
    except BaseException as e:  # noqa: BLE001 -- SystemExit escaping compute() is itself a finding
        res = {"status": "raised", "exc": f"{type(e).__name__}: {e}"[:300], "tb": traceback.format_exc()[-600:]}
    res["seconds"] = round(time.time() - t0, 2)
    res["captured_output_tail"] = buf.getvalue()[-300:]
    try:
        conn.send(res)
    finally:
        os._exit(0)


def run_matrix(pkg, specs, parallel, timeout=CELL_TIMEOUT):
    """All cells, forked from the main thread only (no helper threads: filelock refuses os.fork
    while another thread holds its descriptors). Up to `parallel` children run at once."""
    jobs = []
    for spec_name, (desc, tests_call, no_tests_call) in specs.items():
        modes = ["tests"] + (["no_tests"] if no_tests_call is not None else [])
        for mode in modes:
            for task in TASKS:
                for ex in EXPLOITS:
                    for fenced in (True, False):
                        jobs.append((spec_name, mode, task, ex["id"], fenced))
    results, running = [], []
    jobs = list(reversed(jobs))
    while jobs or running:
        while jobs and len(running) < parallel:
            spec_name, mode, task, ex_id, fenced = jobs.pop()
            parent, child = CTX.Pipe(duplex=False)
            tmpdir = str(SCRATCH / pkg / spec_name.replace("[", "_").replace("]", "") / mode)
            p = CTX.Process(target=_child, args=(child, pkg, spec_name, mode, task, render(ex_id, task, fenced), tmpdir))
            p.start(); child.close()
            meta = {"pkg": pkg, "reward": spec_name, "mode": mode, "task": task["task_id"], "exploit": ex_id,
                    "fenced": fenced}
            running.append([p, parent, meta, time.time(), None])
        time.sleep(0.01)
        still = []
        for item in running:
            p, conn, meta, t0, res = item
            if res is None and conn.poll():
                try:
                    item[4] = res = conn.recv()
                except EOFError:
                    item[4] = res = {"status": "child_died"}
            if not p.is_alive() or res is not None:
                if res is None and conn.poll(0.2):  # child may exit right after sending
                    try:
                        res = conn.recv()
                    except EOFError:
                        res = None
                p.join(5)
                if p.is_alive():
                    p.kill(); p.join()
                if res is None or res.get("status") == "child_died":
                    res = {"status": "child_died", "exitcode": p.exitcode, "seconds": round(time.time() - t0, 2)}
                res.update(meta); results.append(res); conn.close()
            elif time.time() - t0 > timeout:
                p.kill(); p.join()
                res = {"status": "timeout", "seconds": round(time.time() - t0, 1)}
                res.update(meta); results.append(res); conn.close()
            else:
                still.append(item)
        running = still
    return results


# --------------------------------------------------------------------------------------
# Side experiments
# --------------------------------------------------------------------------------------

def _side_child(conn, fn_name, tmpdir):
    os.makedirs(tmpdir, exist_ok=True)
    tempfile.tempdir = tmpdir
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            out = SIDE[fn_name]()
        res = {"status": "ok", "result": out}
    except BaseException as e:  # noqa: BLE001
        res = {"status": "raised", "exc": f"{type(e).__name__}: {e}"[:300], "tb": traceback.format_exc()[-800:]}
    res["captured_output_tail"] = buf.getvalue()[-400:]
    conn.send(res)
    os._exit(0)


def run_side(pkg, fn_name, timeout):
    parent, child = CTX.Pipe(duplex=False)
    p = CTX.Process(target=_side_child, args=(child, fn_name, str(SCRATCH / pkg / "side" / fn_name)))
    t0 = time.time()
    p.start(); child.close()
    res = None
    if parent.poll(timeout):
        try:
            res = parent.recv()
        except EOFError:
            res = None
    p.join(5)
    if p.is_alive():
        p.kill(); p.join()
        res = res or {"status": "timeout", "killed_after_s": timeout}
    if res is None:
        res = {"status": "child_died", "exitcode": p.exitcode}
    res["wall_s"] = round(time.time() - t0, 2)
    return res


def task(tid):
    return next(t for t in TASKS if t["task_id"] == tid)


def side_at_cross_isclose():
    """Claim 5: completion A patches math.isclose; wrong completion B is graded after it by the same
    CodeCorrectnessReward instance in the same process."""
    t = task("HumanEval/2")
    r = at_build("code_correctness")
    # CodeCorrectnessReward exec()s the raw text (no fence stripping), so bare code is used here.
    A, B = render("patch_isclose_A", t, fenced=False), render("wrong_float_B", t, fenced=False)
    out = {"reference_score": r.compute(render("reference", t, fenced=False), None, test_cases=t["dict_tests"]),
           "B_alone_first": r.compute(B, None, test_cases=t["dict_tests"])}
    out["A_score"] = r.compute(A, None, test_cases=t["dict_tests"])
    out["B_after_A"] = r.compute(B, None, test_cases=t["dict_tests"])
    r2 = at_build("code_correctness")
    out["B_on_fresh_instance_same_process"] = r2.compute(B, None, test_cases=t["dict_tests"])
    import math
    out["math_isclose_still_patched_in_caller"] = math.isclose(1.0, 2.0)
    return out


def side_at_cross_isclose_bridge():
    """Same as above, but A and B are two completions of one GRPO batch, scored through AlignTune's
    TRL RewardBridge exactly as GRPOTrainer would call it (dict tests passed as a dataset column)."""
    from aligntune.core.rl.reward_handler import prepare_trl_rewards
    t = task("HumanEval/2")
    prepared = prepare_trl_rewards([{"type": "code_correctness", "weight": 1.0, "params": {}}])
    fn = prepared.functions[0]
    A, B = render("patch_isclose_A", t, fenced=False), render("wrong_float_B", t, fenced=False)
    batch_BB = fn(prompts=["p", "p"], completions=[B, B], completion_ids=None, test_cases=[t["dict_tests"]] * 2)
    batch_AB = fn(prompts=["p", "p"], completions=[A, B], completion_ids=None, test_cases=[t["dict_tests"]] * 2)
    return {"batch[B,B]": batch_BB, "batch[A,B]": batch_AB}


def side_at_cross_alarm():
    """A disables SIGALRM; infinite-loop completion B is then graded by CodeExecutionReward (no tests).
    Expect: without A, B returns 0.0 after ~5 s; with A first, B never returns (outer timeout kills it)."""
    t = task("MBPP/3")
    r = at_build("code_execution")
    A, B = render("patch_alarm_A", t), render("infinite_loop", t)
    a = r.compute(A)
    return {"A_score": a, "B_after_A": r.compute(B)}


def side_at_loop_alone():
    t = task("MBPP/3")
    r = at_build("code_execution")
    t0 = time.time()
    s = r.compute(render("infinite_loop", t))
    return {"score": s, "seconds": round(time.time() - t0, 2)}


def side_at_stale_alarm():
    """A replaces signal.alarm, so the reward's finally-block cannot cancel the 5 s alarm it armed.
    The caller then gets TimeoutError ~5 s later, wherever it happens to be (here: an unrelated sleep)."""
    t = task("MBPP/3")
    r = at_build("code_execution")
    a = r.compute(render("stale_alarm_A", t))
    t0 = time.time()
    try:
        time.sleep(15)
        return {"A_score": a, "caller_sleep": "completed 15 s, no exception"}
    except BaseException as e:  # noqa: BLE001
        return {"A_score": a, "caller_sleep": f"{type(e).__name__} raised in caller after {time.time() - t0:.1f} s: {e}"}


def side_at_loop_correctness_tests():
    t = task("MBPP/3")
    r = at_build("code_correctness")
    return {"score": r.compute(render("infinite_loop", t, fenced=False), None, test_cases=t["dict_tests"])}


def side_at_systemexit_compute():
    """SystemExit raised by the completion inside CodeExecutionReward (no tests): does it escape compute()?"""
    t = task("MBPP/3")
    r = at_build("code_execution")
    r.compute(render("raise_systemexit", t))
    return "compute returned normally"


def side_at_systemexit_correctness():
    t = task("MBPP/3")
    r = at_build("code_correctness")
    return {"score_with_tests": r.compute(render("raise_systemexit", t, fenced=False), None, test_cases=t["dict_tests"]),
            "os_exit_note": "see at_os_exit_correctness"}


def side_at_os_exit_correctness():
    t = task("MBPP/3")
    r = at_build("code_correctness")
    r.compute(render("os_exit", t, fenced=False), None, test_cases=t["dict_tests"])
    return "compute returned normally"


def side_at_os_exit_compute():
    t = task("MBPP/3")
    r = at_build("code_execution")
    r.compute(render("os_exit", t))
    return "compute returned normally"


def side_at_thread_reference():
    """CodeExecutionReward (no tests) called from a worker thread, as AlignTune's async reward path
    (asyncio.to_thread) would: signal.signal() only works in the main thread."""
    t = task("MBPP/3")
    r = at_build("code_execution")
    out = {}

    def go():
        out["reference_in_thread"] = r.compute(render("reference", t))
        out["stub_in_thread"] = r.compute(render("stub", t))
    th = threading.Thread(target=go); th.start(); th.join(30)
    out["reference_main_thread"] = r.compute(render("reference", t))
    return out


def side_at_mbpp_tempfile_leak():
    """MBPPReward._run_code_in_sandbox unlinks its temp file with os.unlink, but core.py never imports os."""
    t = task("MBPP/3")
    d = tempfile.mkdtemp(prefix="leak_")
    tempfile.tempdir = d
    r = at_build("mbpp_reward")
    for _ in range(3):
        r.compute(render("reference", t), None, test_cases=t["assert_tests"])
    left = os.listdir(d)
    r2 = at_build("code_execution")
    d2 = tempfile.mkdtemp(prefix="leak_ce_")
    tempfile.tempdir = d2
    r2.compute(render("reference", t), None, test_cases=t["assert_tests"])
    return {"mbpp_reward_files_left_after_3_calls": len(left), "code_execution_files_left_after_1_call": len(os.listdir(d2))}


def side_at_registry_defaults():
    """Rewards built with the registry's own default config (RewardRegistry.get_reward_function(name)),
    i.e. the default weight, to see what 'after weight' means per reward."""
    from aligntune.rewards.registry import RewardRegistry
    t = task("MBPP/3")
    out = {}
    cases = [
        ("code_execution", "stub", True, None),
        ("code_execution", "print_pass_exit", True, t["assert_tests"]),
        ("code_correctness", "empty", False, None),
        ("code_correctness", "always_equal", False, t["dict_tests"]),
        ("mbpp_reward", "fake_pass_lines", True, t["assert_tests"]),
        ("code_verifiable", "bare_exit", True, t["assert_tests"]),
        ("code_quality", "stub", False, None),
        ("code_quality", "reference", False, None),
    ]
    for name, ex, fenced, tests in cases:
        r = RewardRegistry.get_reward_function(name)
        text = render(ex, t, fenced)
        if name == "code_verifiable":
            s = r.compute(text, tests) if tests else r.compute(text)
        else:
            s = r.compute(text, None, test_cases=tests) if tests else r.compute(text)
        out[f"{name} / {ex} / {'fenced' if fenced else 'bare'} / {'tests' if tests else 'no tests'}"] = {
            "default_weight": r.config.weight, "score_returned": s}
    return out


def side_st_systemexit():
    t = task("MBPP/3")
    from safetune.rewards.registry import RewardRegistry
    out = {}
    for name in ["code_execution", "code_correctness"]:
        r = RewardRegistry.get_reward_function(name, {"type": name, "weight": 1.0, "params": {}})
        out[name + "_no_tests_raise_systemexit"] = r.compute(render("raise_systemexit", t))
        out[name + "_no_tests_os_exit"] = r.compute(render("os_exit", t))
    r = RewardRegistry.get_reward_function("code_execution", {"type": "code_execution", "weight": 1.0, "params": {}})
    t0 = time.time()
    out["code_execution_no_tests_infinite_loop"] = r.compute(render("infinite_loop", t))
    out["infinite_loop_seconds"] = round(time.time() - t0, 2)
    return out


SIDE = {
    "at_cross_isclose": side_at_cross_isclose,
    "at_cross_isclose_bridge": side_at_cross_isclose_bridge,
    "at_cross_alarm": side_at_cross_alarm,
    "at_loop_alone": side_at_loop_alone,
    "at_loop_correctness_tests": side_at_loop_correctness_tests,
    "at_systemexit_compute": side_at_systemexit_compute,
    "at_systemexit_correctness": side_at_systemexit_correctness,
    "at_os_exit_compute": side_at_os_exit_compute,
    "at_os_exit_correctness": side_at_os_exit_correctness,
    "at_stale_alarm": side_at_stale_alarm,
    "at_thread_reference": side_at_thread_reference,
    "at_mbpp_tempfile_leak": side_at_mbpp_tempfile_leak,
    "at_registry_defaults": side_at_registry_defaults,
    "st_systemexit": side_st_systemexit,
}


def versions():
    out = {"python": sys.version.split()[0], "executable": sys.executable,
           "python_on_PATH": __import__("shutil").which("python")}
    for p in ["aligntune", "safetune", "trl", "transformers", "torch", "vllm", "curatorkit", "datasets"]:
        try:
            out[p] = md.version(p)
        except md.PackageNotFoundError:
            out[p] = None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", choices=["aligntune", "safetune"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--parallel", type=int, default=4)  # gentle mode
    ap.add_argument("--only-side", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    # Import once in the parent so forked children inherit loaded modules (fast cells).
    reg = importlib.import_module(f"{a.pkg}.rewards.registry")
    if a.pkg == "aligntune":
        importlib.import_module("aligntune.backends.trl.rl.counterfact_grpo.counterfact_grpo")
        importlib.import_module("aligntune.core.rl.reward_handler")
    registry = reg.RewardRegistry.list_rewards()
    specs = AT_SPECS if a.pkg == "aligntune" else ST_SPECS
    out = {"pkg": a.pkg, "versions": versions(), "registry_entries": registry,
           "specs": {k: v[0] for k, v in specs.items()},
           "tasks": [t["task_id"] for t in TASKS], "exploits": EXPLOITS}
    if not a.only_side:
        out["cells"] = run_matrix(a.pkg, specs, a.parallel)
    side_names = [k for k in SIDE if k.startswith("at_" if a.pkg == "aligntune" else "st_")]
    out["side"] = {}
    for k in side_names:
        out["side"][k] = run_side(a.pkg, k, timeout=40)
        print("side", k, json.dumps(out["side"][k])[:300], flush=True)
    out["elapsed_s"] = round(time.time() - t0, 1)
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1, default=str))
    print("wrote", a.out, "cells:", len(out.get("cells", [])), "elapsed", out["elapsed_s"])


if __name__ == "__main__":
    main()
