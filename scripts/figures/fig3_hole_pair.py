"""Figure 3: the exploratory hole pair, h-ship-s0 against h-sec-s0.

Reads jobs/runs/h-ship-s0 and h-sec-s0: completions.jsonl, summary.json (gpu).
Top row: exploit-shaped rate per step (pass_print or early_exit or always_equal).
Bottom row: RBW per step (aligntune_ce >= 0.999 and secure_all < 0.999), counted in both arms;
only H-ship's were paid in training (H-sec trains on securegrade).
Two measures, two rows: no shared second axis. Unsmoothed.
Numbers checked against results/hole-pair-2026-11-07.md, which rounds halves up (68/320 -> 21.3%).
"""
import sys

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MultipleLocator

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from _common import Checks, fmt_pct, half_up, completions, grader, is_exploit, per_step, save, setup, summary, window, write_csv  # noqa: E402

RUNS = ["h-ship-s0", "h-sec-s0"]
GPU_SHORT = {"h-ship-s0": "RTX 3090", "h-sec-s0": "RTX 5090"}
# hole-pair-2026-11-07.md main table
MD = {"h-ship-s0": {"exp": (0.291, 0.213), "rbw": (5, 6), "rbw_all": 62, "wall": 1.96},
      "h-sec-s0": {"exp": (0.338, 0.231), "rbw": (6, 5), "rbw_all": 42, "wall": 2.14}}


def is_rbw(c):
    return bool(c["rewarded_but_wrong"])


def main():
    ck = Checks("fig3")
    D, rows_csv = {}, []
    for run in RUNS:
        cs = completions(run)
        s = summary(run)
        ck.eq(f"{run} GPU is {GPU_SHORT[run]}", int(GPU_SHORT[run] in (s["gpu"] or "")), 1)
        ck.eq(f"{run} wall hours", round(s["wall_s"] / 3600, 2), MD[run]["wall"], tol=0.006)
        e1, _ = window(cs, 1, 10, is_exploit)
        e2, _ = window(cs, 91, 100, is_exploit)
        r1 = sum(is_rbw(c) for c in cs if 1 <= c["step"] <= 10)
        r2 = sum(is_rbw(c) for c in cs if 91 <= c["step"] <= 100)
        ra = sum(is_rbw(c) for c in cs)
        ck.eq(f"{run} exploit rate steps 1-10", half_up(e1, 3), MD[run]["exp"][0], tol=0.0006)
        ck.eq(f"{run} exploit rate steps 91-100", half_up(e2, 3), MD[run]["exp"][1], tol=0.0006)
        ck.eq(f"{run} RBW count steps 1-10", r1, MD[run]["rbw"][0])
        ck.eq(f"{run} RBW count steps 91-100", r2, MD[run]["rbw"][1])
        ck.eq(f"{run} RBW count all steps", ra, MD[run]["rbw_all"])
        exp = per_step(cs, is_exploit)
        rbw = per_step(cs, is_rbw)
        D[run] = {"exp": exp, "rbw": rbw, "e": (e1, e2), "r": (r1, r2, ra)}
        for st in exp:
            rows_csv.append([run, st, round(exp[st], 5), round(rbw[st], 5)])
    write_csv("fig3_hole_pair_per_step.csv", ["run", "step", "exploit_shaped_rate", "rbw_rate"], rows_csv)
    bad = ck.report()
    for run in RUNS:
        e1, e2 = D[run]["e"]
        r1, r2, ra = D[run]["r"]
        print(f"[fig3] {run}: exploit {fmt_pct(e1)} -> {fmt_pct(e2)}; RBW {r1}/320 -> {r2}/320; all steps {ra}/3,200; "
              f"max per-step RBW {max(D[run]['rbw'].values()):.3f}")
    for theme in ("light", "dark"):
        draw(theme, D)
    return bad


def pct(x, _):
    return f"{x * 100:.0f}%"


def draw(theme, D):
    t = setup(theme)
    fig, axes = plt.subplots(2, 2, figsize=(10.4, 5.9), sharex=True)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.73, bottom=0.10, hspace=0.42, wspace=0.07)
    for c, run in enumerate(RUNS):
        for r, (key, ymax, step) in enumerate((("exp", 0.62, 0.1), ("rbw", 0.155, 0.05))):
            ax = axes[r][c]
            for lo, hi in ((0.5, 10.5), (90.5, 100.5)):
                ax.axvspan(lo, hi, color=t["wash"], lw=0, zorder=0)
            xs = list(D[run][key].keys())
            ys = list(D[run][key].values())
            ax.plot(xs, ys, color=t[grader(run)], lw=1.6, zorder=3)
            ax.set_xlim(0.5, 100.5)
            ax.set_ylim(0, ymax)
            ax.yaxis.set_major_locator(MultipleLocator(step))
            ax.yaxis.set_major_formatter(FuncFormatter(pct))
            ax.set_xticks([1, 25, 50, 75, 100])
            ax.spines["left"].set_visible(False)
            if c == 1:
                ax.tick_params(labelleft=False)
            name = "H-ship" if "ship" in run else "H-sec"
            if key == "exp":
                e1, e2 = D[run]["e"]
                ax.set_title(f"{name}: exploit-shaped rate ({GPU_SHORT[run]})", fontsize=9.5, pad=4)
                note = f"steps 1–10: {fmt_pct(e1)}    91–100: {fmt_pct(e2)}"
            else:
                r1, r2, ra = D[run]["r"]
                paid = "all paid in training" if "ship" in run else "never paid: trains on securegrade"
                ax.set_title(f"{name}: rewarded-but-wrong rate ({paid})", fontsize=9.5, pad=4)
                note = f"steps 1–10: {r1}/320    91–100: {r2}/320    all: {ra}/3,200"
                ax.set_xlabel("training step")
            ax.text(0.995, 0.97, note, transform=ax.transAxes, ha="right", va="top", fontsize=8, color=t["ink2"])
    axes[0][0].set_ylabel("share of 32", fontsize=8.5)
    axes[1][0].set_ylabel("share of 32", fontsize=8.5)
    fig.text(0.075, 0.965, "Hole pair (exploratory, seed 0): the prompt states the grader’s hole outright",
             fontsize=12, fontweight="bold", color=t["ink"], va="top")
    fig.text(0.075, 0.915,
             "Share of the 32 completions at each step, unsmoothed. Rewarded-but-wrong: shipped grader ≥ 0.999, "
             "securegrade < 0.999.\n"
             "Different GPUs (RTX 3090, RTX 5090), started about 15 h apart, so sampling is not identical. "
             "Shaded: steps 1–10 and 91–100.",
             fontsize=8.5, color=t["ink2"], va="top", linespacing=1.45)
    handles = [Line2D([], [], color=t["ship"], lw=2), Line2D([], [], color=t["sec"], lw=2)]
    fig.legend(handles, ["H-ship: trained on the shipped grader (AlignTune code_execution)",
                         "H-sec: trained on the secure grader (securegrade)"],
               loc="upper left", bbox_to_anchor=(0.068, 0.845), ncol=2, fontsize=8.5, handlelength=1.6,
               labelcolor=t["ink2"])
    save(fig, "fig3-hole-pair", theme)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
