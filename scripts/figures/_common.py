"""Shared helpers for the article figures: paths, run loaders, metric definitions, themes, save.

Definitions follow design/RUNS-2026-11-02.md section 2:
- RBW (rewarded-but-wrong): aligntune_ce >= 0.999 and secure_all < 0.999 (the `rewarded_but_wrong` field).
- Exploit-shaped rate: share of completions flagged pass_print or early_exit or always_equal.
- Divergence: mean aligntune_ce minus mean secure_all over the same completions.
Colours follow the dataviz skill's reference palette (slot 1 blue, slot 2 orange), validated light and dark.
"""
import csv
import json
import pathlib
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "jobs" / "runs"
RESULTS = ROOT / "results"
FIG_DIR = ROOT / "figures"
DATA_DIR = FIG_DIR / "data"

EIGHT = ["e-ship-s0", "e-ship-s1", "e-sec-s0", "e-sec-s1", "u-ship-s0", "u-ship-s1", "u-sec-s0", "u-sec-s1"]
HOLE = ["h-ship-s0", "h-sec-s0"]
ALL10 = EIGHT + HOLE
EVAL_STEPS = [0, 25, 50, 75, 100]


def label(run):
    """'e-ship-s0' -> 'E-ship, seed 0'."""
    group, arm, seed = run.split("-")
    return f"{group.upper()}-{arm}, seed {seed[1:]}"


def grader(run):
    return "ship" if "-ship-" in run else "sec"


def _rows(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def completions(run):
    return _rows(RUNS_DIR / run / "completions.jsonl")


def evals(run):
    return {e["step"]: e for e in _rows(RUNS_DIR / run / "evals.jsonl")}


def summary(run):
    """Only the fields the figures need (the file also holds the launch command; never print it)."""
    s = json.loads((RUNS_DIR / run / "summary.json").read_text(encoding="utf-8"))
    return {"wall_s": s["wall_s"], "gpu": s.get("gpu"), "global_step": s.get("global_step"), "status": s.get("status")}


def is_exploit(c):
    return bool(c.get("det_pass_print") or c.get("det_early_exit") or c.get("det_always_equal"))


def per_step(cs, fn):
    by = {}
    for c in cs:
        by.setdefault(c["step"], []).append(fn(c))
    return {s: sum(v) / len(v) for s, v in sorted(by.items())}


def window(cs, lo, hi, fn):
    w = [fn(c) for c in cs if lo <= c["step"] <= hi]
    return sum(w) / len(w), len(w)


def mean(xs):
    return statistics.fmean(xs)


def half_up(x, nd):
    """Round half up (as the results files do: 68/320 = 0.2125 -> 21.3%), not Python's float rounding."""
    from decimal import ROUND_HALF_UP, Decimal
    return float(Decimal(repr(round(x, 12))).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP))


def fmt_pct(x, nd=1):
    return f"{half_up(x * 100, nd):.{nd}f}%"


def write_csv(name, header, rows):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


class Checks:
    """Collects comparisons between computed numbers and the numbers printed in results/*.md."""

    def __init__(self, fig):
        self.fig = fig
        self.items = []

    def eq(self, what, got, expected, tol=0.0005):
        ok = abs(got - expected) <= tol
        self.items.append((what, got, expected, ok))
        return ok

    def report(self):
        bad = [i for i in self.items if not i[3]]
        print(f"[{self.fig}] checks: {len(self.items) - len(bad)}/{len(self.items)} match the results files")
        for what, got, exp, _ in bad:
            print(f"[{self.fig}] MISMATCH {what}: computed {got} vs results file {exp}")
        return bad


# ----------------------------------------------------------------------------- themes
THEMES = {
    "light": {
        "surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
        "grid": "#e1e0d9", "axis": "#c3c2b7",
        "ship": "#2a78d6", "sec": "#eb6834",
        "wash": (0.043, 0.043, 0.043, 0.045),
        # heatmap: <= 0 cell, then the blue ramp (light -> dark = more paid)
        "cell0": "#f0efec", "seq": ["#9ec5f4", "#5598e7", "#256abf", "#104281"],
    },
    "dark": {
        "surface": "#1a1a19", "ink": "#f0efec", "ink2": "#c3c2b7", "muted": "#898781",
        "grid": "#2c2c2a", "axis": "#383835",
        "ship": "#3987e5", "sec": "#d95926",
        "wash": (0.941, 0.937, 0.925, 0.06),
        # dark mode flips the anchor: more paid = lighter
        "cell0": "#2c2c2a", "seq": ["#1c5cab", "#3987e5", "#6da7ec", "#b7d3f6"],
    },
}
GRADER_NAME = {"ship": "Shipped grader (AlignTune code_execution)", "sec": "Secure grader (securegrade)"}


def setup(theme):
    t = THEMES[theme]
    plt.rcdefaults()
    plt.rcParams.update({
        "font.family": ["DejaVu Sans"],
        "font.size": 10,
        "axes.titlesize": 10.5,
        "axes.titleweight": "regular",
        "axes.titlelocation": "left",
        "axes.titlecolor": t["ink"],
        "axes.labelcolor": t["ink2"],
        "axes.labelsize": 9.5,
        "axes.edgecolor": t["axis"],
        "axes.linewidth": 0.8,
        "axes.facecolor": t["surface"],
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.axisbelow": True,
        "grid.color": t["grid"],
        "grid.linewidth": 0.8,
        "grid.linestyle": "-",
        "xtick.color": t["muted"],
        "ytick.color": t["muted"],
        "xtick.labelcolor": t["ink2"],
        "ytick.labelcolor": t["ink2"],
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "figure.facecolor": t["surface"],
        "savefig.facecolor": t["surface"],
        "text.color": t["ink"],
        "legend.frameon": False,
        "legend.fontsize": 9,
        "lines.linewidth": 2.0,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        "svg.fonttype": "path",
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
    return t


def clean_axes(ax, t, left=True):
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(t["axis"])
    if not left:
        ax.tick_params(labelleft=False)


def save(fig, name, theme):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    base = FIG_DIR / f"{name}-{theme}"
    fig.savefig(base.with_suffix(".png"), dpi=200)
    fig.savefig(base.with_suffix(".svg"))
    plt.close(fig)
    return base
