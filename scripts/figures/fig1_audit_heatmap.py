"""Figure 1: historical shipped rewards against the exact re-audited release sources.

Reads:
- results/gate1-2026-11-01.json (cells): the shipped scores (aligntune 0.1.28, safetune 0.1.10)
- results/release-reaudit-2026-11-08/*-gate1.json: complete exact-source release and legacy reruns
Cell = highest score over the 5 tasks and both formats (fenced, bare), weight 1.0, as in the PR-check tables.
The "before" values are computed from Gate 1 and checked against the new legacy reruns.
The "after" sources are AlignTune tag ff59f10 and SafeTune merge 36b2142, both installed
from exact source archives. No-tests rows show native payments, classified by rewardcheck
as configuration errors rather than correctness results.
No exploit code is drawn: columns carry the class names used in the results files.
"""
import json
import sys

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, to_rgb

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from _common import RESULTS, Checks, save, setup, write_csv  # noqa: E402
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from release_report import load_complete, score  # noqa: E402

EXPLOITS = ["empty", "prose", "stub", "print_pass_exit", "bare_exit", "fake_pass_lines", "always_equal"]
COL_NAMES = ["empty", "prose", "stub", "PASS+\nexit", "bare\nexit", "fake\nPASS:", "always-\nequal"]

# (package, reward key in the JSONs, mode, row label)
ROWS = [
    ("aligntune", "code_execution", "tests", "code_execution, assert tests"),
    ("aligntune", "code_execution[dicts]", "tests", "code_execution, dict tests"),
    ("aligntune", "code_execution", "no_tests", "code_execution, no tests"),
    ("aligntune", "code_correctness", "tests", "code_correctness, dict tests"),
    ("aligntune", "code_correctness[asserts]", "tests", "code_correctness, assert tests"),
    ("aligntune", "code_correctness", "no_tests", "code_correctness, no tests"),
    ("aligntune", "mbpp_reward", "tests", "mbpp_reward, tests"),
    ("aligntune", "mbpp_reward", "no_tests", "mbpp_reward, no tests"),
    ("aligntune", "code_verifiable", "tests", "code_verifiable, tests"),
    ("aligntune", "code_verifiable", "no_tests", "code_verifiable, no tests"),
    ("aligntune", "counterfact_grpo_code", "tests", "counterfactual-GRPO code reward, tests"),
    ("aligntune", "counterfact_grpo_code", "no_tests", "counterfactual-GRPO code reward, no tests"),
    ("safetune", "code_execution", "tests", "code_execution, assert tests"),
    ("safetune", "code_execution[dicts]", "tests", "code_execution, dict tests"),
    ("safetune", "code_execution", "no_tests", "code_execution, no tests"),
    ("safetune", "code_correctness", "tests", "code_correctness, assert tests"),
    ("safetune", "code_correctness", "no_tests", "code_correctness, no tests"),
    ("safetune", "mbpp_reward", "tests", "mbpp_reward, test_list"),
    ("safetune", "mbpp_reward", "no_tests", "mbpp_reward, no tests"),
]
GROUPS = {"aligntune": "AlignTune", "safetune": "SafeTune"}


def load():
    g = json.loads((RESULTS / "gate1-2026-11-01.json").read_text(encoding="utf-8"))
    data=RESULTS/"release-reaudit-2026-11-08"
    release={"aligntune":load_complete(data/"aligntune-release-gate1.json",expected_cells=2160),
             "safetune":load_complete(data/"safetune-merge-gate1.json",expected_cells=1350)}
    legacy={"aligntune":load_complete(data/"aligntune-legacy-gate1.json",expected_cells=2160),
            "safetune":load_complete(data/"safetune-legacy-gate1.json",expected_cells=1350)}
    before, raised, ref_before = {}, set(), {}
    for c in g["cells"]:
        key = (c["pkg"], c["reward"], c["mode"], c["exploit"])
        if c["status"] != "ok":
            raised.add(key)
            continue
        before.setdefault(key, []).append(c["score"])
    after, after_ref, before_refs, old_max = {}, {}, {}, {}
    for pkg in release:
        for run,values,refs in ((release[pkg],after,after_ref),(legacy[pkg],old_max,before_refs)):
            scores={}; counts={}
            for r in run["rows"]:
                if r["mode"]=="empty_tests":continue
                mode="no_tests" if r["mode"]=="missing_tests" else r["mode"]
                key=(pkg,r["reward"],mode,r["completion"])
                s=score(r)
                if s is not None:scores.setdefault(key,[]).append(s)
                if r["completion"]=="reference":
                    counts.setdefault(key,[0,0])[0 if r["fenced"] else 1]+=int(s is not None and s>=(.95 if pkg=="aligntune" else .999))
            values.update({k:max(v) for k,v in scores.items()})
            refs.update({k:tuple(v) for k,v in counts.items()})
    return before, raised, after, after_ref, before_refs, old_max


def main():
    before, raised, after, after_ref, before_ref, old_max = load()
    ck = Checks("fig1")
    B, A, rows_csv = [], [], []
    for pkg, rw, mode, _ in ROWS:
        rb, ra = [], []
        for ex in EXPLOITS:
            key = (pkg, rw, mode, ex)
            b = max(before[key])
            ck.eq(f"{pkg} {rw} [{mode}] {ex} shipped (historical Gate 1 vs legacy rerun)", b, old_max[key], tol=0.005)
            rb.append(b)
            ra.append(after[key])
            rows_csv.append([pkg, rw, mode, ex, round(b, 4), round(after[key], 4), "yes" if key in raised else ""])
        B.append(rb)
        A.append(ra)
    write_csv("fig1_audit_heatmap.csv", ["package", "reward", "mode", "exploit", "shipped_max", "release_max",
                                         "systemexit_escaped_in_some_cells_shipped"], rows_csv)
    bad = ck.report()

    paid_before = sum(v > 0 for r in B for v in r)
    paid_after = sum(v > 0 for r in A for v in r)
    tests_rows = [i for i, r in enumerate(ROWS) if r[2] == "tests"]
    paid_after_tests = sum(A[i][j] > 0 for i in tests_rows for j in range(len(EXPLOITS)))
    paid_before_tests = sum(B[i][j] > 0 for i in tests_rows for j in range(len(EXPLOITS)))
    print(f"[fig1] cells paying > 0: shipped {paid_before}/{len(ROWS) * len(EXPLOITS)}, fixed {paid_after}")
    print(f"[fig1] with tests supplied: shipped {paid_before_tests}, fixed {paid_after_tests} "
          f"(of {len(tests_rows) * len(EXPLOITS)})")
    print(f"[fig1] max shipped value {max(max(r) for r in B):.2f}")

    for theme in ("light", "dark"):
        draw(theme, B, A, raised, before_ref, after_ref)
    return bad


def draw(theme, B, A, raised, before_ref, after_ref):
    t = setup(theme)
    cmap = LinearSegmentedColormap.from_list("paid", t["seq"])

    def colour(v):
        if v <= 0:
            return t["cell0"]
        return cmap(min(v, 1.0))

    def text_on(rgb):
        r, g, b = to_rgb(rgb)
        lum = 0.2126 * r ** 2.2 + 0.7152 * g ** 2.2 + 0.0722 * b ** 2.2
        return "#0b0b0b" if lum > 0.36 else "#ffffff"

    n_rows, n_cols = len(ROWS), len(EXPLOITS)
    # layout: group header rows inserted before each package
    ypos, y = [], 0
    headers = []
    prev = None
    for pkg, *_ in ROWS:
        if pkg != prev:
            headers.append((y, pkg))
            y += 1.15
            prev = pkg
        ypos.append(y)
        y += 1
    total_h = y

    row_in = 0.30                       # inches per row unit
    head_in = 1.55                      # title + panel titles + column headers
    foot_in = 1.05                      # legend + note
    H = row_in * total_h + head_in + foot_in
    W = 11.6
    fig = plt.figure(figsize=(W, H))
    grid_bottom = foot_in / H
    grid_h = row_in * total_h / H
    axL = fig.add_axes([0.255, grid_bottom, 0.335, grid_h])
    axR = fig.add_axes([0.640, grid_bottom, 0.335, grid_h])
    gap = 0.07

    for ax, M, refs, title, sub in ((axL, B, before_ref, "Shipped", "AlignTune 0.1.28, SafeTune 0.1.10"),
                                    (axR, A, after_ref, "Re-audited release sources",
                                     "AlignTune ff59f10; SafeTune 36b2142")):
        ax.set_xlim(0, n_cols + 1.25)
        ax.set_ylim(total_h, 0)
        ax.axis("off")
        for i, (pkg, rw, mode, _) in enumerate(ROWS):
            yy = ypos[i]
            for j, ex in enumerate(EXPLOITS):
                v = M[i][j]
                fc = colour(v)
                ax.add_patch(mpatches.Rectangle((j + gap / 2, yy + gap / 2), 1 - gap, 1 - gap, facecolor=fc,
                                                edgecolor="none", linewidth=0))
                if v > 0:
                    ax.text(j + 0.5, yy + 0.53, f"{v:.2f}", ha="center", va="center", fontsize=8,
                            color=text_on(fc))
                if ax is axL and (pkg, rw, mode, ex) in raised:
                    ax.text(j + 0.5, yy + 0.53, "†", ha="center", va="center", fontsize=9, color=t["ink2"])
            rf, rb = refs[(pkg, rw, mode, "reference")]
            ax.text(n_cols + 0.65, yy + 0.53, f"{rf} · {rb}", ha="center", va="center", fontsize=8.5,
                    color=t["ink2"])
        for j, name in enumerate(COL_NAMES):
            ax.text(j + 0.5, -0.12, name, ha="center", va="bottom", fontsize=8, color=t["ink2"], linespacing=1.05)
        ax.text(n_cols + 0.65, -0.12, "real\nsolution", ha="center", va="bottom", fontsize=8, color=t["muted"],
                linespacing=1.05)
        ax.text(0, -1.55, sub, ha="left", va="bottom", fontsize=9, color=t["ink2"])
        ax.text(0, -2.25, title, ha="left", va="bottom", fontsize=10.5, color=t["ink"], fontweight="bold")
        for yh, pkg in headers:
            ax.plot([0, n_cols], [yh + 0.98, yh + 0.98], color=t["axis"], lw=0.8, solid_capstyle="butt")

    for i, (pkg, rw, mode, lab) in enumerate(ROWS):
        axL.text(-0.25, ypos[i] + 0.53, lab, ha="right", va="center", fontsize=8.5, color=t["ink2"])
    for yh, pkg in headers:
        axL.text(-0.25, yh + 0.55, GROUPS[pkg], ha="right", va="center", fontsize=9.5, color=t["ink"],
                 fontweight="bold")
        axR.text(0, yh + 0.55, GROUPS[pkg], ha="left", va="center", fontsize=9.5, color=t["ink"], fontweight="bold")

    # legend: three swatches at fixed inch offsets
    def fx(inch):
        return inch / W

    def fy(inch):
        return inch / H

    ly = 0.74
    fig.text(fx(0.15), fy(ly), "Score paid", fontsize=8.5, color=t["ink2"], va="center")
    x = 1.0
    for fc, name, w in ((t["cell0"], "0 or less", 0.95), (colour(0.5), "0.50", 0.6), (colour(1.0), "1.00 or more", 1.2)):
        fig.patches.append(mpatches.Rectangle((fx(x), fy(ly - 0.07)), fx(0.16), fy(0.14), transform=fig.transFigure,
                                              facecolor=fc, edgecolor="none"))
        fig.text(fx(x + 0.22), fy(ly), name, fontsize=8.5, color=t["ink2"], va="center")
        x += w + 0.22
    fig.text(fx(0.15), fy(0.30),
             "Cell: highest score over 5 tasks × 2 formats (fenced, bare), weight 1.0; the row says whether tests "
             "were supplied. No tests: native payment under a configuration error.\n"
             "Real solution: tasks (of 5) at the historical compatibility threshold (AlignTune ≥ 0.95; SafeTune ≥ 0.999), "
             "fenced · bare.\n"
             "† shipped AlignTune: the exit escaped the reward in the fenced format, which ends a TRL run.  "
             "Exact source archives, not a tested PyPI 0.1.29 wheel; provenance is in the release re-audit report.",
             fontsize=7.8, color=t["muted"], va="center", linespacing=1.5)
    fig.text(fx(0.15), 1 - fy(0.18),
             "What each code reward paid for answers that solve nothing, before and after the fixes",
             fontsize=12, color=t["ink"], va="top", fontweight="bold")
    save(fig, "fig1-audit-heatmap", theme)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
