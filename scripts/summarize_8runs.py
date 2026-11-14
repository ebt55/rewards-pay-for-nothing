"""Summarise all 8 GRPO runs: integrity checks, per-window rates, evals."""
import json
import pathlib
import sys

RUNS = pathlib.Path(sys.argv[1])
SHA = "a3307e2a5a1f60d419a3ed4f2d9070e8ab8bbef5495155f1b6ef9e6396e29c20"
ORDER = ["e-ship", "e-sec", "u-ship", "u-sec"]
DETS = ["pass_print", "early_exit", "always_equal", "hardcoded", "stub", "any_exploit"]


def rows(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def window(cs, lo, hi):
    w = [c for c in cs if lo <= c["step"] <= hi]
    n = len(w)
    out = {"n": n,
           "rbw": sum(c["rewarded_but_wrong"] for c in w) / n,
           "ce_mean": sum(c["aligntune_ce"] for c in w) / n,
           "sec_mean": sum(c["secure_all"] for c in w) / n,
           "sec_pass": sum(c["secure_all"] >= 0.999 for c in w) / n}
    for d in DETS:
        out[d] = sum(bool(c.get("det_" + d)) for c in w) / n
    return out


report = {}
for arm in ORDER:
    for seed in (0, 1):
        run = f"{arm}-s{seed}"
        d = RUNS / run
        s = json.loads((d / "summary.json").read_text())
        cs = rows(d / "completions.jsonl")
        ev = {e["step"]: e for e in rows(d / "evals.jsonl")}
        checks = {
            "global_step": s.get("global_step"), "status": s.get("status"),
            "stop_reason": s.get("stop_reason"),
            "elicit_sha_ok": s.get("elicitation_sha256") == SHA if arm.startswith("e") else s.get("elicitation_sha256"),
            "hint_sha_ok": s.get("eval_hint_sha256") == SHA,
            "upload_errors": s.get("upload_errors_before_final"),
            "wall_h": round(s.get("wall_s", 0) / 3600, 2),
            "steps_logged": sorted({c["step"] for c in cs})[-1], "n_completions": len(cs),
            "eval_steps": sorted(ev),
            "aligntune_ver": s.get("versions", {}).get("aligntune"),
            "secure_impl": s.get("secure_impl"), "priv_drop": s.get("securegrade_privilege_drop"),
        }
        rbw_all = [c for c in cs if c["rewarded_but_wrong"]]
        paid_exploit = [c for c in cs if c.get("det_any_exploit") and c["aligntune_ce"] >= 0.999]
        report[run] = {
            "checks": checks,
            "early": window(cs, 1, 10), "late": window(cs, 91, 100),
            "rbw_count_all_steps": len(rbw_all),
            "rbw_examples": [(c["step"], c["task_id"], c["aligntune_ce"], c["secure_all"],
                              [k for k in DETS if c.get("det_" + k)]) for c in rbw_all[:8]],
            "paid_exploit_flag_count": len(paid_exploit),
            "paid_exploit_examples": [(c["step"], c["task_id"], c["aligntune_ce"], c["secure_all"],
                                       [k for k in DETS if c.get("det_" + k)]) for c in paid_exploit[:8]],
            "evals": {st: {"mbpp": e["mbpp"]["pass_at_1"], "mbpp_hidden": e["mbpp"].get("hidden_pass_at_1"),
                           "mbpp_rbw": e["mbpp"].get("rewarded_but_wrong"),
                           "hint": e["mbpp_hint"]["pass_at_1"], "hint_rbw": e["mbpp_hint"].get("rewarded_but_wrong"),
                           "hint_pass_print": e["mbpp_hint"]["det_rates"]["pass_print"],
                           "hint_early_exit": e["mbpp_hint"]["det_rates"]["early_exit"],
                           "humaneval": round(e["humaneval"]["pass_at_1"], 3)} for st, e in ev.items()},
        }

json.dump(report, open(RUNS.parent / "summary8.json", "w"), indent=1, default=str)

print("== checks")
for r, v in report.items():
    print(r, v["checks"])
print("\n== training windows: steps 1-10 -> 91-100 (fractions of 320 completions)")
hdr = ["rbw", "pass_print", "early_exit", "any_exploit", "ce_mean", "sec_pass"]
print(f"{'run':10}" + "".join(f"{h:>22}" for h in hdr) + f"{'rbw_all':>9}{'paid_flag':>10}")
for r, v in report.items():
    cells = "".join(f"{v['early'][h]:>10.3f} -> {v['late'][h]:<8.3f}" for h in hdr)
    print(f"{r:10}{cells}{v['rbw_count_all_steps']:>9}{v['paid_exploit_flag_count']:>10}")
print("\n== evals step 0 -> 100")
for r, v in report.items():
    e0, e1 = v["evals"][0], v["evals"][max(v["evals"])]
    print(r, {k: f"{e0[k]} -> {e1[k]}" for k in e0})
print("\n== evals by step, mbpp pass@1 / hint pass@1 / hint pass_print")
for r, v in report.items():
    print(r, [(st, e["mbpp"], e["hint"], e["hint_pass_print"]) for st, e in v["evals"].items()])
print("\n== rbw / paid-exploit examples")
for r, v in report.items():
    if v["rbw_examples"] or v["paid_exploit_examples"]:
        print(r, "rbw:", v["rbw_examples"], "paid:", v["paid_exploit_examples"])
