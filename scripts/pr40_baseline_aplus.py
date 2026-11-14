"""0.1.28 baseline for the A_plus cross-completion case (our code, MIT). Run in a throwaway process:
    env -i ... PR40_SRC=installed ~/p9/at/bin/python -W ignore scripts/pr40_baseline_aplus.py
A_plus patches builtins in whatever process runs it; on 0.1.28 code_correctness exec()s it in-process,
so this writes with os.write (print may not survive the patch). With PR40_SRC unset it runs on the PR.
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import builtins  # noqa: E402

import gate1_run as g  # noqa: E402
import pr40_gate1 as p  # noqa: E402  (loads the PR or 0.1.28 per PR40_SRC)

real_len = builtins.len


def say(k, v):
    os.write(1, (k + "=" + repr(v) + "\n").encode())


t = g.task("HumanEval/2")
B = g.render("wrong_float_B", t, fenced=False)
r = g.at_build("code_correctness")
say("label", p.LABEL)
say("B_alone", r.compute(B, None, test_cases=t["dict_tests"]))
try:
    a = r.compute(p.A_PLUS, None, test_cases=t["dict_tests"])
except BaseException as e:  # noqa: BLE001
    a = "raised " + type(e).__name__
say("A_plus", a)
say("caller_builtins_len_is_real_len", builtins.len is real_len)
say("caller_abs(-1)", abs(-1))
builtins.len = real_len  # restore len so the next call can be scored at all
say("B_after_A_plus_same_object", r.compute(B, None, test_cases=t["dict_tests"]))
say("B_after_A_plus_fresh_object", g.at_build("code_correctness").compute(B, None, test_cases=t["dict_tests"]))
