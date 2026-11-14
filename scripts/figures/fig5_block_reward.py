"""Figure 5: mean training reward per 10-step block, per arm, per seed.

Reads jobs/runs/<run>/completions.jsonl: train_reward_recomputed (the arm's own training reward: AlignTune
code_execution for ship arms, securegrade's fraction of asserts passed for sec arms), 32 completions per step.
Block b covers steps 10(b-1)+1 .. 10b (block 3 = steps 21-30, block 6 = steps 51-60).
Same-seed arms draw the same tasks in the same order (checked here step by step), so their block rewards move together.
Checks the release plan section 0 numbers: seed 0, block 3 is 0.27-0.33 and block 6 is 0.52-0.61 in all four arms;
and "only 3-5 of the 40 tasks in steps 91-100 also appear in steps 1-10".
"""
import sys

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from _common import Checks, completions, grader, mean, save, setup, write_csv  # noqa: E402

SEEDS = {"0": ["e-ship-s0", "e-sec-s0", "u-ship-s0", "u-sec-s0", "h-ship-s0", "h-sec-s0"],
         "1": ["e-ship-s1", "e-sec-s1", "u-ship-s1", "u-sec-s1"]}
MARK = {"e": "o", "u": "s", "h": "^"}
GROUP = {"e": "E", "u": "U", "h": "H"}
PREREG4 = ["e-ship-s0", "e-sec-s0", "u-ship-s0", "u-sec-s0"]
CLAIMS = {3: (0.27, 0.33), 6: (0.52, 0.61)}  # 15-RELEASE-AND-WRITEUP-PLAN.md section 0


def tasks_by_step(cs):
    by = {}
    for c in cs:
        by.setdefault(c["step"], set()).add(c["task_id"])
    return by


def main():
    ck = Checks("fig5")
    B, T, rows_csv = {}, {}, []
    for seed, runs in SEEDS.items():
        for run in runs:
            cs = completions(run)
            T[run] = tasks_by_step(cs)
            B[run] = [mean([c["train_reward_recomputed"] for c in cs if 10 * b + 1 <= c["step"] <= 10 * b + 10])
                      for b in range(10)]
            for b, v in enumerate(B[run], 1):
                rows_csv.append([run, b, f"{10 * (b - 1) + 1}-{10 * b}", round(v, 4)])
        base = T[runs[0]]
        for run in runs[1:]:
            same = sum(base[s] == T[run][s] for s in base)
            ck.eq(f"seed {seed}: {run} sees the same tasks as {runs[0]} at every step", same, 100)
    write_csv("fig5_block_reward.csv", ["run", "block", "steps", "mean_training_reward"], rows_csv)

    verdicts = []
    for blk, (lo, hi) in CLAIMS.items():
        vals = [B[r][blk - 1] for r in PREREG4]
        got_lo, got_hi = round(min(vals), 2), round(max(vals), 2)
        ok = got_lo >= lo and got_hi <= hi and got_lo == lo and got_hi == hi
        ck.eq(f"seed 0 block {blk} low end (4 arms)", got_lo, lo, tol=0.0001)
        ck.eq(f"seed 0 block {blk} high end (4 arms)", got_hi, hi, tol=0.0001)
        with_h = [B[r][blk - 1] for r in SEEDS["0"]]
        verdicts.append((blk, lo, hi, vals, ok, min(with_h), max(with_h)))
    # "only 3-5 of the 40 tasks in steps 91-100 also appear in steps 1-10"
    overlaps = {}
    for seed, runs in SEEDS.items():
        t = T[runs[0]]
        early = set().union(*[t[s] for s in range(1, 11)])
        late_steps = [t[s] for s in range(91, 101)]
        n_late = sum(len(x) for x in late_steps)
        late = set().union(*late_steps)
        overlaps[seed] = (len(late & early), n_late, len(late))
    bad = ck.report()
    for blk, lo, hi, vals, ok, hlo, hhi in verdicts:
        print(f"[fig5] seed 0 block {blk} (steps {10 * blk - 9}-{10 * blk}): " +
              ", ".join(f"{r} {v:.3f}" for r, v in zip(PREREG4, vals)) +
              f" -> {min(vals):.2f}-{max(vals):.2f}; plan says {lo:.2f}-{hi:.2f}: {'HOLDS' if ok else 'DOES NOT HOLD'}; "
              f"with the H pair {hlo:.2f}-{hhi:.2f}")
    for seed, (ov, n, uniq) in overlaps.items():
        print(f"[fig5] seed {seed}: {ov} of the {uniq} distinct tasks in steps 91-100 ({n} task slots) "
              f"also appear in steps 1-10")
    for seed, runs in SEEDS.items():
        for r in runs:
            print(f"[fig5] {r}: " + " ".join(f"{v:.3f}" for v in B[r]))
    # descriptive only (not in a results file): correlation of block curves within and across seeds
    def corr(a, b):
        ma, mb = mean(a), mean(b)
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
        return num / den
    within0 = [corr(B[a], B[b]) for i, a in enumerate(PREREG4) for b in PREREG4[i + 1:]]
    s1 = SEEDS["1"]
    within1 = [corr(B[a], B[b]) for i, a in enumerate(s1) for b in s1[i + 1:]]
    across = [corr(B[a], B[b]) for a in PREREG4 for b in s1]
    print(f"[fig5] (descriptive) Pearson r of 10 block means: within seed 0 {min(within0):.2f}-{max(within0):.2f}; "
          f"within seed 1 {min(within1):.2f}-{max(within1):.2f}; across seeds {min(across):.2f}-{max(across):.2f}")
    for theme in ("light", "dark"):
        draw(theme, B)
    return bad


def draw(theme, B):
    t = setup(theme)
    fig, axes = plt.subplots(2, 1, figsize=(10.4, 6.9), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.735, bottom=0.095, hspace=0.32)
    xs = list(range(1, 11))
    for ax, (seed, runs) in zip(axes, SEEDS.items()):
        if seed == "0":
            for blk, (lo, hi) in CLAIMS.items():
                ax.axvspan(blk - 0.4, blk + 0.4, color=t["wash"], lw=0, zorder=0)
                ax.text(blk, 0.212, f"{lo:.2f}–{hi:.2f}*", ha="center", va="bottom", fontsize=7.8,
                        color=t["ink2"])
        for run in runs:
            g = run.split("-")[0]
            col = t[grader(run)]
            ax.plot(xs, B[run], color=col, lw=1.8, marker=MARK[g], ms=6.5, mfc=col, mec=t["surface"], mew=1.2,
                    zorder=3)
        ax.set_ylim(0.2, 0.66)
        ax.yaxis.set_major_locator(MultipleLocator(0.1))
        ax.set_xlim(0.5, 10.5)
        ax.set_xticks(xs)
        ax.set_xticklabels([f"{10 * (b - 1) + 1}–{10 * b}" for b in xs])
        ax.spines["left"].set_visible(False)
        n = len(runs)
        extra = " (E, U and the exploratory H pair)" if seed == "0" else " (E and U)"
        ax.set_title(f"Seed {seed}: {n} arms{extra}", fontsize=10, pad=5)
        ax.set_ylabel("mean training reward", fontsize=8.5)
    axes[1].set_xlabel("training steps in the 10-step block")
    fig.text(0.075, 0.975, "Training reward per 10-step block: arms with the same seed move together",
             fontsize=12, fontweight="bold", color=t["ink"], va="top")
    fig.text(0.075, 0.935,
             "Each point is the mean of 320 completions. Each arm’s own training reward: the shipped grader’s "
             "score for ship arms,\nsecuregrade’s share of asserts passed for sec arms. Arms with the same seed see "
             "the same tasks in the same order.\n* range over the 4 pre-registered seed-0 arms in the shaded block.",
             fontsize=8.5, color=t["ink2"], va="top", linespacing=1.45)
    handles, labels = [], []
    for g in ("e", "u", "h"):
        for gr in ("ship", "sec"):
            handles.append(Line2D([], [], color=t[gr], lw=1.8, marker=MARK[g], ms=6.5, mfc=t[gr],
                                  mec=t["surface"], mew=1.2))
            labels.append(f"{GROUP[g]}-{gr}")
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.068, 0.835), ncol=6, fontsize=8.5,
               handlelength=2.6, labelcolor=t["ink2"], columnspacing=1.8)
    fig.text(0.985, 0.819, "ship = trained on the shipped grader, sec = on securegrade", ha="right", va="center",
             fontsize=8, color=t["muted"])
    save(fig, "fig5-block-reward", theme)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
