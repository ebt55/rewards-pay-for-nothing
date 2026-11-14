"""Figure 4: held-out evals at steps 0/25/50/75/100 for all 10 runs.

Reads jobs/runs/<run>/evals.jsonl: mbpp.pass_at_1 (100 fixed MBPP tasks), mbpp_hint.pass_at_1 (the same 100 tasks
with the hint appended), humaneval.pass_at_1 (164 tasks). HumanEval always sits beside MBPP.
The E and U runs' hint is sentence 1 (sha a3307e2a...); the H pair's hint is sentences 1 + 2 (sha 473943c4...),
so the H row's hint column is not comparable with the rows above it.
Step 0 and step 100 values are checked against grpo-8runs-2026-11-03.md and hole-pair-2026-11-07.md.
"""
import sys

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from _common import ALL10, EVAL_STEPS, Checks, evals, grader, save, setup, write_csv  # noqa: E402

ROWS = [("E runs: prompt states how the grader works", ["e-ship-s0", "e-ship-s1", "e-sec-s0", "e-sec-s1"]),
        ("U runs: plain prompt", ["u-ship-s0", "u-ship-s1", "u-sec-s0", "u-sec-s1"]),
        ("H pair (exploratory): prompt states the hole", ["h-ship-s0", "h-sec-s0"])]
METRICS = [("mbpp", "MBPP pass@1 (100 tasks)"), ("hint", "MBPP with the hint (same 100 tasks)"),
           ("he", "HumanEval pass@1 (164 tasks)")]
# step 0 -> step 100 as printed in the results files (MBPP pass@1, MBPP+hint, HumanEval)
MD = {
    "e-ship-s0": ((0.44, 0.50), (0.43, 0.53), (0.463, 0.445)),
    "e-ship-s1": ((0.44, 0.50), (0.43, 0.54), (0.463, 0.451)),
    "e-sec-s0": ((0.44, 0.52), (0.43, 0.52), (0.463, 0.457)),
    "e-sec-s1": ((0.44, 0.50), (0.43, 0.55), (0.463, 0.463)),
    "u-ship-s0": ((0.44, 0.56), (0.43, 0.54), (0.463, 0.457)),
    "u-ship-s1": ((0.44, 0.56), (0.43, 0.57), (0.463, 0.451)),
    "u-sec-s0": ((0.44, 0.53), (0.43, 0.55), (0.463, 0.439)),
    "u-sec-s1": ((0.44, 0.55), (0.43, 0.58), (0.463, 0.427)),
    "h-ship-s0": ((0.44, 0.50), (0.46, 0.50), (0.463, 0.439)),
    "h-sec-s0": ((0.45, 0.50), (0.46, 0.56), (0.451, 0.457)),
}


def series(run):
    ev = evals(run)
    return {"mbpp": [ev[s]["mbpp"]["pass_at_1"] for s in EVAL_STEPS],
            "hint": [ev[s]["mbpp_hint"]["pass_at_1"] for s in EVAL_STEPS],
            "he": [ev[s]["humaneval"]["pass_at_1"] for s in EVAL_STEPS]}


def main():
    ck = Checks("fig4")
    S, rows_csv = {}, []
    for run in ALL10:
        S[run] = series(run)
        for k, (key, _) in enumerate(METRICS):
            ck.eq(f"{run} {key} step 0", round(S[run][key][0], 3), MD[run][k][0])
            ck.eq(f"{run} {key} step 100", round(S[run][key][-1], 3), MD[run][k][1])
        for i, st in enumerate(EVAL_STEPS):
            rows_csv.append([run, st, S[run]["mbpp"][i], S[run]["hint"][i], round(S[run]["he"][i], 4)])
    write_csv("fig4_heldout_evals.csv", ["run", "step", "mbpp_pass_at_1", "mbpp_hint_pass_at_1",
                                         "humaneval_pass_at_1"], rows_csv)
    bad = ck.report()
    d_mbpp = [S[r]["mbpp"][-1] - S[r]["mbpp"][0] for r in ALL10[:8]]
    d_he = [S[r]["he"][-1] - S[r]["he"][0] for r in ALL10[:8]]
    print(f"[fig4] 8 runs: MBPP change step 0->100 {min(d_mbpp):+.2f} to {max(d_mbpp):+.2f}; "
          f"HumanEval {min(d_he):+.3f} to {max(d_he):+.3f}; HumanEval down in {sum(d < 0 for d in d_he)} of 8")
    lo = min(min(v) for s in S.values() for v in s.values())
    hi = max(max(v) for s in S.values() for v in s.values())
    print(f"[fig4] plotted range {lo:.3f}-{hi:.3f}")
    for theme in ("light", "dark"):
        draw(theme, S)
    return bad


def draw(theme, S):
    t = setup(theme)
    fig, axes = plt.subplots(3, 3, figsize=(10.4, 7.6), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.765, bottom=0.075, hspace=0.50, wspace=0.08)
    for r, (row_name, runs) in enumerate(ROWS):
        for c, (key, mname) in enumerate(METRICS):
            ax = axes[r][c]
            for run in runs:
                col = t[grader(run)]
                seed1 = run.endswith("s1")
                ax.plot(EVAL_STEPS, S[run][key], color=col, lw=1.8, zorder=3,
                        marker="o", ms=6.5, mew=1.6 if seed1 else 1.2,
                        mfc=t["surface"] if seed1 else col, mec=col if seed1 else t["surface"])
            ax.set_xticks(EVAL_STEPS)
            ax.set_xlim(-5, 105)
            ax.set_ylim(0.35, 0.62)
            ax.yaxis.set_major_locator(MultipleLocator(0.05))
            ax.spines["left"].set_visible(False)
            ax.set_title(mname if r == 0 else "", fontsize=9.5, pad=4)
            if r == 2 and key == "hint":
                ax.text(0.03, 0.97, "hint = sentences 1 + 2 here", transform=ax.transAxes, fontsize=8,
                        color=t["ink2"], va="top")
            if r == 2:
                ax.set_xlabel("training step")
        axes[r][0].set_ylabel("pass@1", fontsize=8.5)
        # row label above the row, left aligned with the first panel
        pos = axes[r][0].get_position()
        fig.text(pos.x0, pos.y1 + (0.045 if r == 0 else 0.022), row_name, fontsize=10, color=t["ink"],
                 fontweight="bold", va="bottom")
    fig.text(0.075, 0.975, "Held-out pass@1 during training, all 10 runs",
             fontsize=12, fontweight="bold", color=t["ink"], va="top")
    fig.text(0.075, 0.94,
             "Evaluated at steps 0, 25, 50, 75 and 100. MBPP uses 100 fixed tasks, so gaps under about 0.1 are "
             "within noise;\nHumanEval uses 164 tasks (SE ≈ 0.04). One or two seeds per arm, 100 steps, 3.35B model.",
             fontsize=8.5, color=t["ink2"], va="top", linespacing=1.45)
    handles = [
        Line2D([], [], color=t["ship"], lw=1.8, marker="o", ms=6.5, mfc=t["ship"], mec=t["surface"], mew=1.2),
        Line2D([], [], color=t["ship"], lw=1.8, marker="o", ms=6.5, mfc=t["surface"], mec=t["ship"], mew=1.6),
        Line2D([], [], color=t["sec"], lw=1.8, marker="o", ms=6.5, mfc=t["sec"], mec=t["surface"], mew=1.2),
        Line2D([], [], color=t["sec"], lw=1.8, marker="o", ms=6.5, mfc=t["surface"], mec=t["sec"], mew=1.6),
    ]
    fig.legend(handles, ["shipped grader, seed 0", "shipped grader, seed 1", "secure grader, seed 0",
                         "secure grader, seed 1"],
               loc="upper left", bbox_to_anchor=(0.068, 0.895), ncol=4, fontsize=8.5, handlelength=2.6,
               labelcolor=t["ink2"], columnspacing=1.6)
    save(fig, "fig4-heldout-evals", theme)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
