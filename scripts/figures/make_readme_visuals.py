"""README visuals: a rewardcheck terminal GIF, the replay before/after chart and a small explainer.

Run from the repository root in WSL (CPU only):

    nice -n 19 ~/p9/figs/bin/python -B scripts/figures/make_readme_visuals.py

Reads only:
  figures/readme/selfcheck-naive.txt, figures/readme/selfcheck-securegrade.txt
      (captured stdout of the two harness/README.md quick-start commands; this script never runs them)
  results/replay-release-2026-11-14.json
Writes only figures/readme/ (images + README.md). Needs matplotlib and Pillow, DejaVu Sans / Sans Mono.

Colours: the dataviz reference palette as in scripts/figures/_common.py. Orange = the old (historical)
grader, blue = released graders / value grading, as in figures/article-visuals/. The terminal uses a
red/green pair checked for deutan separation; the words PAID / FAIL / PASS carry the meaning without colour.
"""
import hashlib
import io
import json
import pathlib
import platform
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _common import THEMES  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "figures" / "readme"
REPLAY = ROOT / "results" / "replay-release-2026-11-14.json"
NAIVE_TXT = OUT / "selfcheck-naive.txt"
SG_TXT = OUT / "selfcheck-securegrade.txt"

# old grader = orange, released / value grading = blue (same hexes as _common: "sec" / "ship" slots)
OLD = {"light": "#eb6834", "dark": "#d95926"}
NEW = {"light": "#2a78d6", "dark": "#3987e5"}
TRACK = {"light": "#efeee9", "dark": "#262624"}
OLD_WASH = {"light": "#fbe3d8", "dark": "#3a2419"}
NEW_WASH = {"light": "#e3eefb", "dark": "#18273b"}

FONT_DIR = pathlib.Path("/usr/share/fonts/truetype/dejavu")
MONO = FONT_DIR / "DejaVuSansMono.ttf"
MONO_BOLD = FONT_DIR / "DejaVuSansMono-Bold.ttf"
SANS = FONT_DIR / "DejaVuSans.ttf"


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def fail(msg):
    raise SystemExit(f"CHECK FAILED: {msg}")


# =============================================================================== data checks
OLD_KEY = "AlignTune old 57e9a95 code_execution"
RELEASED = ["AlignTune release code_execution", "AlignTune release code_verifiable", "AlignTune release mbpp_reward",
            "SafeTune merge code_execution", "SafeTune merge mbpp_reward"]
PASS_FAIL = [g for g in RELEASED if g != "AlignTune release mbpp_reward"]


def replay_numbers():
    d = json.loads(REPLAY.read_text(encoding="utf-8"))
    if not d.get("complete") or d.get("missing_cells") != 0:
        fail("replay JSON is not complete")
    t = d["table"]
    want = {"a": 47, "b": 64, "control": 300}
    for c, n in want.items():
        if t[c]["n"] != n:
            fail(f"class {c}: n {t[c]['n']} != {n}")
        if t[c][OLD_KEY]["full"] != n or t[c][OLD_KEY]["graded"] != n:
            fail(f"class {c}: old grader full {t[c][OLD_KEY]['full']} != {n}")
    for c in ("a", "b"):
        for g in RELEASED:
            r = t[c][g]
            if (r["full"], r["positive"], r["graded"], r["not_scored"]) != (0, 0, want[c], 0):
                fail(f"class {c} / {g}: {r}")
    for g in PASS_FAIL:
        if t["control"][g]["full"] != 297 or t["control"][g]["graded"] != 300:
            fail(f"control / {g}: {t['control'][g]}")
    if t["control"]["AlignTune release mbpp_reward"]["full"] != 1:
        fail("AlignTune release mbpp_reward control full != 1")
    if d.get("still_paid_count") != 0:
        fail("still_paid_count != 0")
    rows = [
        ("a", "Wrong code that exits\nbefore the tests run", 47, 47, 0, "every released grader"),
        ("b", "Correct code that exits\nbefore the tests run", 64, 64, 0, "every released grader"),
        ("control", "Ordinary correct code\n(random sample)", 300, 300, 297, "each pass/fail grader"),
    ]
    print("[chart] checks passed: old 47/47, 64/64, 300/300; released 0/47, 0/64 on all 5; control 297/300 on 4")
    return rows


# =============================================================================== matplotlib setup
def mpl_setup(theme):
    t = THEMES[theme]
    plt.rcdefaults()
    plt.rcParams.update({
        "font.family": ["DejaVu Sans"],
        "font.size": 10,
        "text.color": t["ink"],
        "figure.facecolor": t["surface"],
        "savefig.facecolor": t["surface"],
        "axes.facecolor": t["surface"],
        "svg.fonttype": "path",
        "svg.hashsalt": "readme-visuals",
    })
    return t


def save_mpl(fig, name, theme, svg=True):
    base = OUT / f"{name}-{theme}"
    fig.savefig(base.with_suffix(".png"), dpi=200, metadata={"Software": None})
    if svg:
        fig.savefig(base.with_suffix(".svg"), metadata={"Date": None, "Creator": None})
    plt.close(fig)


def hbar(ax, x0, x1, y, h, color, px_per_x, px_per_y, r_px=8):
    """Bar from x0 to x1 (data), square at the baseline, rounded data end (r_px at 2x = 4 px at 1x)."""
    if x1 - x0 <= 0:
        return
    rx = r_px / px_per_x
    ry = r_px / px_per_y
    if x1 - x0 <= 2 * rx:
        ax.add_patch(Rectangle((x0, y - h / 2), x1 - x0, h, color=color, lw=0, zorder=3))
        return
    ax.add_patch(Rectangle((x0, y - h / 2), x1 - x0 - rx, h, color=color, lw=0, zorder=3))
    ax.add_patch(FancyBboxPatch((x1 - 2 * rx, y - h / 2), 2 * rx, h,
                                boxstyle=f"round,pad=0,rounding_size={rx}",
                                mutation_aspect=ry / rx, color=color, lw=0, zorder=3))


# =============================================================================== chart
def chart(theme, rows):
    t = mpl_setup(theme)
    W, H = 8.4, 5.2
    fig = plt.figure(figsize=(W, H))
    L = 0.035  # left margin (figure fraction)
    fig.text(L, 0.942, "Released graders pay none of the 111 exit tricks the old one paid",
             fontsize=13, fontweight="bold", color=t["ink"], va="baseline")
    fig.text(L, 0.886, "Answers a 3.35B model wrote in 10 GRPO training runs on MBPP, re-graded on 14 Nov 2026. "
             "Paid = score ≥ 0.999.", fontsize=8.8, color=t["ink2"], va="baseline")
    items = [(OLD[theme], "Old grader: AlignTune code_execution 57e9a95, the version used in training"),
             (NEW[theme], "Released graders: AlignTune ff59f10, SafeTune merge 36b2142")]
    for i, (c, s) in enumerate(items):
        y = 0.826 - i * 0.046
        fig.patches.append(Rectangle((L, y - 0.013), 0.02, 0.028, transform=fig.transFigure, color=c, lw=0))
        fig.text(L + 0.03, y, s, fontsize=8.8, color=t["ink"], va="center")

    axl, axw = 0.30, 0.40
    ax = fig.add_axes([axl, 0.225, axw, 0.525])
    ax.set_xlim(0, 1)
    ax.set_ylim(5.0, -0.6)
    ax.axis("off")
    renderer = fig.canvas.get_renderer()
    bbox = ax.get_window_extent(renderer)
    px_per_x = bbox.width * 200 / fig.dpi
    px_per_y = bbox.height / 5.6 * 200 / fig.dpi
    hx = (L - axl) / axw  # data x of the figure's left margin

    ys = {"a": 0.55, "b": 2.0, "control": 4.1}
    for y, s in ((-0.38, "Exit tricks found in training answers"), (3.22, "Control: ordinary correct answers")):
        ax.text(hx, y, s, fontsize=8.8, fontweight="bold", color=t["ink2"], va="center", ha="left", clip_on=False)
    ax.plot([hx, (0.965 - axl) / axw], [2.93, 2.93], color=t["grid"], lw=0.9, clip_on=False, zorder=1)

    h = 0.40
    inv = ax.transData.inverted()
    for key, label, n, old_paid, new_paid, scope in rows:
        y = ys[key]
        ax.text(-0.035, y, label + f"\n(n = {n})", fontsize=8.8, color=t["ink"], ha="right", va="center",
                linespacing=1.3, clip_on=False)
        for dy, val, colr, extra in ((-0.25, old_paid, OLD[theme], "old"), (0.25, new_paid, NEW[theme], scope)):
            yy = y + dy
            ax.add_patch(Rectangle((0, yy - h / 2), 1.0, h, color=TRACK[theme], lw=0, zorder=2))
            hbar(ax, 0, val / n, yy, h, colr, px_per_x, px_per_y)
            t1 = ax.text(1.03, yy, f"{val} of {n}", fontsize=9.2, fontweight="bold", color=t["ink"],
                         va="center", ha="left", clip_on=False)
            ext = t1.get_window_extent(renderer)
            x2 = inv.transform((ext.x1, 0))[0] + 0.025
            ax.text(x2, yy, extra, fontsize=8.6, color=t["ink2"], va="center", ha="left", clip_on=False)
    for x, s in ((0, "0%"), (1, "100%")):
        ax.text(x, 4.6, s, fontsize=8.6, color=t["muted"], ha="center", va="top", clip_on=False)
    notes = ["Released graders: AlignTune ff59f10 code_execution, code_verifiable and mbpp_reward; SafeTune merge",
             "36b2142 code_execution and mbpp_reward. Source archives, not PyPI wheels.",
             "Control row: the four pass/fail graders. AlignTune mbpp_reward scores on a sliding scale (1 of 300 at",
             "full marks). The 3 controls the released graders reject print PASS and end before the tests run."]
    for i, s in enumerate(notes):
        fig.text(L, 0.142 - i * 0.034, s, fontsize=8.4, color=t["muted"], va="baseline")
    save_mpl(fig, "replay-before-after", theme)


# =============================================================================== explainer
def explainer(theme):
    t = mpl_setup(theme)
    W, H = 1600, 850
    fig = plt.figure(figsize=(W / 200, H / 200))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    ink, ink2, muted, grid = t["ink"], t["ink2"], t["muted"], t["grid"]
    surf = t["surface"]
    mono = {"family": "DejaVu Sans Mono", "size": 10.5}

    ax.text(60, 62, "How exit(0) earns full marks", fontsize=14, fontweight="bold", color=ink, va="center")
    ax.plot([60, 1540], [108, 108], color=ink2, lw=1.0)
    ax.plot([800, 800], [145, 808], color=grid, lw=1.2)

    def box(x0, y0, x1, y1, fc, ec, lw=1.2, r=10):
        ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle=f"round,pad=0,rounding_size={r}",
                                    fc=fc, ec=ec, lw=lw, zorder=2))

    def arrow(p0, p1, color, ls="-", lw=1.8):
        ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=16, color=color, lw=lw,
                                     linestyle=ls, zorder=4, shrinkA=0, shrinkB=0))

    def verdict(x, label, value, color):
        ax.text(x, 696, label, fontsize=10, color=ink2, va="center")
        ax.add_patch(Rectangle((x, 726), 10, 82, color=color, lw=0))
        ax.text(x + 30, 770, value, fontsize=30, fontweight="bold", color=ink, va="center")

    # ---------------- left: one program, tests appended after the answer
    ax.text(60, 172, "A grader that pays on exit code 0", fontsize=11.5, fontweight="bold", color=ink, va="center")
    ax.text(60, 212, "runs the answer and the tests as one program", fontsize=9.2, color=ink2, va="center")
    bx0, by0, bx1, by1 = 60, 245, 520, 610
    box(bx0, by0, bx1, by1, surf, ink2)
    ax.add_patch(Rectangle((bx0 + 1.5, 368), bx1 - bx0 - 3, 44, color=OLD_WASH[theme], lw=0, zorder=2.5))
    ax.add_patch(Rectangle((bx0 + 1.5, 368), 8, 44, color=OLD[theme], lw=0, zorder=2.6))
    for y, s, c in ((290, "def add(a, b):", ink), (340, "    return 0", ink), (390, "exit(0)", ink),
                    (510, "assert add(2, 3) == 5", muted), (560, "assert add(1, 1) == 2", muted)):
        ax.text(bx0 + 30, y, s, color=c, va="center", zorder=3, **mono)
    ax.plot([bx0 + 14, bx1 - 14], [440, 440], color=muted, lw=1.1, ls=(0, (4, 4)), zorder=3)
    ax.text(bx0 + 30, 465, "tests appended by the grader", fontsize=9.2, color=muted, va="center", zorder=3,
            style="italic")
    ax.text(548, 380, "program stops,", fontsize=9.6, color=ink, va="center")
    ax.text(548, 410, "exit code 0", fontsize=9.6, color=ink, va="center")
    ax.plot([536, 536], [490, 580], color=muted, lw=1.2)
    ax.text(548, 535, "never run", fontsize=9.6, color=ink, va="center")
    verdict(60, "exit code 0, so the reward is", "1.0", OLD[theme])

    # ---------------- right: tests stay in the caller, only values come back
    X = 860
    ax.text(X, 172, "A value-out grader", fontsize=11.5, fontweight="bold", color=ink, va="center")
    ax.text(X, 212, "keeps the tests and compares returned values", fontsize=9.2, color=ink2, va="center")
    box(X, 245, X + 440, 380, NEW_WASH[theme], NEW[theme])
    ax.text(X + 22, 272, "caller (grader)", fontsize=9.2, color=ink2, va="center", zorder=3)
    ax.text(X + 22, 312, "add(2, 3) == 5 ?", color=ink, va="center", zorder=3, **mono)
    ax.text(X + 22, 352, "add(1, 1) == 2 ?", color=ink, va="center", zorder=3, **mono)
    box(X, 460, X + 440, 642, surf, ink2)
    ax.text(X + 22, 487, "fresh process: the answer", fontsize=9.2, color=ink2, va="center", zorder=3)
    ax.add_patch(Rectangle((X + 1.5, 579), 437, 42, color=OLD_WASH[theme], lw=0, zorder=2.5))
    for y, s in ((524, "def add(a, b):"), (562, "    return 0"), (600, "exit(0)")):
        ax.text(X + 22, y, s, color=ink, va="center", zorder=3, **mono)
    arrow((X + 60, 380), (X + 60, 460), NEW[theme])
    ax.text(X + 78, 420, "add(2, 3)", fontsize=9.2, color=ink, va="center", family="DejaVu Sans Mono")
    arrow((X + 300, 460), (X + 300, 380), muted, ls=(0, (4, 3)))
    ax.text(X + 318, 420, "no value comes back", fontsize=9.2, color=ink, va="center")
    verdict(X, "nothing to compare, so the reward is", "0.0", NEW[theme])
    save_mpl(fig, "how-the-trick-works", theme)


# =============================================================================== terminal GIF
T_BG, T_BAR, T_INK, T_INK2, T_MUTED = "#1a1a19", "#2c2c2a", "#f0efec", "#c3c2b7", "#9a9891"
T_PROMPT = "#6da7ec"
T_RED, T_GREEN = "#ef6b62", "#57d38c"  # deutan dE checked with the dataviz validator (see README)
T_RED_WASH = "#3a2220"


def rel_lum(hexc):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexc[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted((rel_lum(a), rel_lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def pick(lines, startswith):
    for ln in lines:
        if ln.startswith(startswith):
            return ln
    fail(f"line starting {startswith!r} not found in captured output")


def terminal_doc():
    """Build the displayed lines from the captured outputs. Each line: (kind, [(text, style), ...])."""
    naive = NAIVE_TXT.read_text(encoding="utf-8").splitlines()
    sg = SG_TXT.read_text(encoding="utf-8").splitlines()
    classes = ["empty", "prose", "stub", "print_pass_exit", "bare_exit", "fake_pass_lines", "always_equal"]

    def block(out, verdict, details):
        lines = [("out", [(pick(out, "rewardcheck selfcheck:"), "ink2")]),
                 ("out", [(pick(out, "Answers that solve nothing"), "ink")]),
                 ("out", [(pick(out, "  class "), "muted")])]
        for c in classes:
            ln = pick(out, f"  {c} ")
            if ln.rstrip().endswith("PAID"):
                body = ln.rstrip()[:-4]
                lines.append(("paid", [(body, "red"), ("PAID", "red_bold")]))
            else:
                lines.append(("out", [(ln.rstrip(), "ink")]))
        lines.append(("out", [(pick(out, "Correct references (control):"), "ink")]))
        lines.append(("out", [("…", "muted")]))
        v = pick(out, verdict)
        word, rest = v.split(" ", 1)
        lines.append(("verdict", [(word, "pill_red" if word == "FAIL" else "pill_green"), (" " + rest, "ink2")]))
        i = out.index(v)
        for k in range(details):
            lines.append(("out", [(out[i + 1 + k], "ink")]))
        return lines

    # sanity on the captured text
    for c in ("print_pass_exit", "bare_exit", "always_equal"):
        if "10/10" not in pick(naive, f"  {c} ") or not pick(naive, f"  {c} ").rstrip().endswith("PAID"):
            fail(f"naive capture: {c} not PAID 10/10")
        if " 0/10" not in pick(sg, f"  {c} "):
            fail(f"securegrade capture: {c} not 0/10")
    for out in (naive, sg):
        if "10/10 accepted" not in pick(out, "Correct references (control):"):
            fail("references not 10/10")
    if not pick(naive, "FAIL (") or not pick(sg, "PASS ("):
        fail("verdicts missing")

    cmd1 = ['export PYTHONPATH="$PWD/harness"',
            "nice -n 19 python3 -m rewardcheck.selfcheck \\",
            "    --factory harness/examples/naive_reward.py:make_reward \\",
            "    --tests-column test_cases"]
    cmd2 = ["nice -n 19 python3 -m rewardcheck.selfcheck \\",
            "    --factory harness/examples/securegrade_reward.py:make_reward \\",
            "    --tests-column test_list --entry-point-column entry_point \\",
            "    --setup-column test_imports"]
    # the README commands, joined, must equal the displayed ones without the line continuations
    readme = (ROOT / "harness" / "README.md").read_text(encoding="utf-8")
    for cmd in (cmd1[1:], cmd2):
        joined = " ".join(s.rstrip(" \\").strip() for s in cmd)
        if joined not in readme:
            fail(f"displayed command not in harness/README.md: {joined}")
    if cmd1[0] not in readme:
        fail("export line not in README")

    def cmd_lines(cmd):
        out = []
        for j, s in enumerate(cmd):
            prefix = "$ " if (j == 0 or not cmd[j - 1].endswith("\\")) else "  "
            out.append(("cmd", [(prefix, "prompt"), (s, "ink")]))
        return out

    doc = cmd_lines(cmd1) + block(naive, "FAIL (", 3) + [("out", [("", "ink")])] + cmd_lines(cmd2) + block(sg, "PASS (", 0)
    return doc


def render_gif():
    for name, fg in (("red", T_RED), ("green", T_GREEN), ("ink2", T_INK2), ("muted", T_MUTED), ("prompt", T_PROMPT)):
        c = contrast(fg, T_BG)
        need = 4.5
        if c < need:
            fail(f"terminal {name} {fg} contrast {c:.2f} < {need}")
    for pill in (T_RED, T_GREEN):
        if contrast(T_BG, pill) < 4.5:
            fail(f"pill text contrast on {pill} too low")
    if contrast(T_RED, T_RED_WASH) < 4.5:
        fail("red on wash too low")

    doc = terminal_doc()
    SIZE, LH = 16, 22
    f_reg = ImageFont.truetype(str(MONO), SIZE)
    f_bold = ImageFont.truetype(str(MONO_BOLD), SIZE)
    f_bar = ImageFont.truetype(str(SANS), 13)
    cw = f_reg.getlength("M")
    PADX, TOP, BAR = 26, 52, 34
    longest = max(sum(len(s) for s, _ in segs) for _, segs in doc)
    W = int(PADX * 2 + cw * max(longest, 72))
    W += W % 2
    H = TOP + LH * len(doc) + 22
    if W > 1000:
        fail(f"GIF width {W} > 1000")

    colors = {"ink": T_INK, "ink2": T_INK2, "muted": T_MUTED, "prompt": T_PROMPT, "red": T_RED,
              "red_bold": T_RED}

    def frame(n_full, partial=None, cursor=False):
        im = Image.new("RGB", (W, H), T_BG)
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, W, BAR), fill=T_BAR)
        for k in range(3):
            d.ellipse((16 + k * 20, BAR // 2 - 6, 28 + k * 20, BAR // 2 + 6), fill="#4a4a46")
        d.text((W / 2, BAR / 2), "rewardcheck selfcheck (README quick start, output trimmed)", font=f_bar,
               fill=T_MUTED, anchor="mm")
        shown = doc[:n_full] + ([doc[n_full]] if partial is not None and n_full < len(doc) else [])
        cur_xy = None
        for i, (kind, segs) in enumerate(shown):
            y = TOP + i * LH
            limit = partial if (partial is not None and i == n_full) else None
            if kind == "paid":
                d.rectangle((PADX - 8, y - 2, W - PADX + 8, y + LH - 4), fill=T_RED_WASH)
            x = PADX
            used = 0
            for s, style in segs:
                if limit is not None:
                    take = max(0, min(len(s), limit - used))
                    s_draw = s[:take]
                else:
                    s_draw = s
                used += len(s)
                if style.startswith("pill_"):
                    fill = T_RED if style == "pill_red" else T_GREEN
                    wpx = cw * len(s_draw)
                    d.rounded_rectangle((x - 5, y - 2, x + wpx + 5, y + LH - 4), radius=4, fill=fill)
                    d.text((x, y), s_draw, font=f_bold, fill=T_BG)
                else:
                    font = f_bold if style.endswith("_bold") else f_reg
                    d.text((x, y), s_draw, font=font, fill=colors[style])
                x += cw * len(s_draw)
            if limit is not None:
                cur_xy = (x, y)
        if cursor:
            if cur_xy is None:
                y = TOP + len(shown) * LH
                cur_xy = (PADX + cw * 2, y) if False else (PADX, y)
            x, y = cur_xy
            d.rectangle((x + 1, y, x + cw - 1, y + SIZE + 2), fill=T_INK2)
        return im

    # ---------------- timeline (80 ms ticks)
    TICK = 80
    frames = []  # (image, ms)

    def add(im, ms):
        frames.append((im, ms))

    def line_len(i):
        return sum(len(s) for s, _ in doc[i][1])

    def type_block(start, count, ticks):
        total = sum(line_len(start + k) for k in range(count))
        for tk in range(1, ticks + 1):
            typed = round(total * tk / ticks)
            i, rem = start, typed
            while i < start + count and rem >= line_len(i):
                rem -= line_len(i)
                i += 1
            if i == start + count:
                add(frame(start + count, None, False), TICK)
            else:
                add(frame(i, rem, True), TICK)

    cmd_idx = [i for i, (k, _) in enumerate(doc) if k == "cmd"]
    c1 = [i for i in cmd_idx if i < 4]
    c2 = [i for i in cmd_idx if i >= 4]
    # prompt with blinking-free cursor, then the first command typed over about 1.2 s
    add(frame(0, 0, True), 400)
    type_block(0, len(c1), 15)
    add(frame(len(c1), None, False), 400)
    # reveal naive output in chunks
    first_out = len(c1)
    verdict1 = next(i for i, (k, _) in enumerate(doc) if k == "verdict")
    chunks = [first_out + 1, first_out + 3]
    chunks += list(range(first_out + 4, first_out + 11))  # one class row per tick group
    chunks += [first_out + 11, verdict1, verdict1 + 4]
    durations = [320, 320] + [200] * 7 + [360, 500, 400]
    for n, ms in zip(chunks, durations):
        add(frame(n), ms)
    add(frame(c2[0], None, False), 1500)
    # second command
    add(frame(c2[0], 0, True), 300)
    type_block(c2[0], len(c2), 15)
    add(frame(c2[-1] + 1), 400)
    s2 = c2[-1] + 1
    verdict2 = len(doc) - 1
    chunks = [s2 + 1, s2 + 3] + list(range(s2 + 4, s2 + 11)) + [s2 + 11, verdict2 + 1]
    durations = [320, 320] + [200] * 7 + [360, 3400]
    for n, ms in zip(chunks, durations):
        add(frame(n), ms)

    # coalesce identical consecutive frames
    merged = []
    for im, ms in frames:
        if merged and merged[-1][0].tobytes() == im.tobytes():
            merged[-1] = (merged[-1][0], merged[-1][1] + ms)
        else:
            merged.append((im, ms))
    final = merged[-1][0]
    pal = final.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im, _ in merged]
    durs = [ms for _, ms in merged]
    gif = OUT / "demo-rewardcheck.gif"
    q[0].save(gif, save_all=True, append_images=q[1:], duration=durs, optimize=False, disposal=1)
    poster = q[-1].convert("RGB")
    poster.save(OUT / "demo-rewardcheck-poster.png", optimize=True)

    # verify the saved GIF
    g = Image.open(gif)
    if "loop" in g.info:
        fail("GIF has a loop extension")
    total, n, last = 0, 0, None
    try:
        while True:
            total += g.info["duration"]
            n += 1
            last = g.convert("RGB")
            g.seek(g.tell() + 1)
    except EOFError:
        pass
    if last.tobytes() != Image.open(OUT / "demo-rewardcheck-poster.png").convert("RGB").tobytes():
        fail("GIF last frame != poster")
    size = gif.stat().st_size
    if size > 1_500_000:
        fail(f"GIF {size} bytes > 1.5 MB")
    if not 10_000 <= total <= 15_500:
        fail(f"GIF duration {total} ms outside 10-15 s")
    print(f"[gif] {W}x{H}, {n} frames, {total / 1000:.2f} s, {size / 1024:.0f} KiB, no loop extension")
    return {"dims": [W, H], "frames": n, "duration_ms": total}


# =============================================================================== contact sheet for review
def gif_contact_sheet(path, out, cols=4, scale=0.4):
    g = Image.open(path)
    frames = []
    try:
        while True:
            frames.append(g.convert("RGB").copy())
            g.seek(g.tell() + 1)
    except EOFError:
        pass
    idx = sorted(set([round(i * (len(frames) - 1) / 11) for i in range(12)]))
    th = [f.resize((int(f.width * scale), int(f.height * scale)), Image.LANCZOS) for f in (frames[i] for i in idx)]
    rows = (len(th) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * th[0].width, rows * th[0].height), "#888888")
    for k, im in enumerate(th):
        sheet.paste(im, ((k % cols) * im.width, (k // cols) * im.height))
    sheet.save(out)


# =============================================================================== README
def write_readme(gif_meta, rows):
    files = ["demo-rewardcheck.gif", "demo-rewardcheck-poster.png",
             "replay-before-after-light.png", "replay-before-after-dark.png",
             "replay-before-after-light.svg", "replay-before-after-dark.svg",
             "how-the-trick-works-light.png", "how-the-trick-works-dark.png",
             "how-the-trick-works-light.svg", "how-the-trick-works-dark.svg"]
    lines = []
    for f in files:
        p = OUT / f
        dims = ""
        if p.suffix in (".png", ".gif"):
            with Image.open(p) as im:
                dims = f"{im.width} x {im.height}"
        lines.append(f"| `{f}` | {dims} | {p.stat().st_size / 1024:.0f} KiB | `{sha(p)}` |")
    src = [("selfcheck-naive.txt", NAIVE_TXT), ("selfcheck-securegrade.txt", SG_TXT),
           ("results/replay-release-2026-11-14.json", REPLAY),
           ("scripts/figures/make_readme_visuals.py", pathlib.Path(__file__))]
    srcl = [f"| `{n}` | `{sha(p)}` |" for n, p in src]
    md = f"""# README visuals

Generated by `scripts/figures/make_readme_visuals.py` from the repository root, in WSL, CPU only:

```sh
nice -n 19 ~/p9/figs/bin/python -B scripts/figures/make_readme_visuals.py
```

Python {platform.python_version()}, matplotlib {matplotlib.__version__}, Pillow {Image.__version__}, DejaVu Sans / Sans Mono.
The script reads only the files listed under Inputs and writes only this folder. It checks every
number it draws against the replay JSON and the captured output, and stops on any mismatch.

## Files

| File | Pixels | Size | SHA-256 |
|---|---|---:|---|
{chr(10).join(lines)}

`demo-rewardcheck.gif`: {gif_meta['duration_ms'] / 1000:.1f} s, {gif_meta['frames']} frames, plays once
(no loop extension) and holds the final frame. `demo-rewardcheck-poster.png` is that final frame.

## Inputs

| Input | SHA-256 |
|---|---|
{chr(10).join(srcl)}

`selfcheck-*.txt` is the unedited stdout of the two quick-start commands in `harness/README.md`,
run on 14 Nov 2026 from the repository root in WSL (Python 3.12.3, `nice -n 19`, `PYTHONPATH="$PWD/harness"`).
Exit status: 1 for the naive reward (FAIL), 0 for securegrade (PASS). The GIF shows these lines trimmed:
the `called as` line, blank lines, the not-gated block, `Cells without a score: none` and the JSON report path are left
out (the not-gated block is marked `…`). Elapsed times are from this run. The terminal's red and green differ in lightness for deutan
viewers (dataviz validator: #ef6b62 vs #57d38c, deutan dE 8.6, target 8) and the words PAID, FAIL and PASS carry the meaning without colour.

## Chart numbers (from `results/replay-release-2026-11-14.json`, paid = score >= 0.999)

| Answers | Old grader (AlignTune code_execution 57e9a95) | Released graders |
|---|---:|---:|
| Wrong code that exits before the tests (class a) | 47 of 47 | 0 of 47, all 5 paths |
| Correct code that exits before the tests (class b) | 64 of 64 | 0 of 64, all 5 paths |
| Ordinary correct code, random control sample | 300 of 300 | 297 of 300, each of the 4 pass/fail paths |

AlignTune `mbpp_reward` is left out of the control row: it scores on a sliding scale and gives full marks to 1 of 300.

Colour: orange = the old grader, blue = released graders and value grading, as in `figures/article-visuals/`
(the reverse of fig2-5 in `figures/`, where blue is the arm trained on the shipped grader). The explainer's left
panel is a generic exit-code grader, not one named AlignTune reward. One GIF only (dark terminal, both themes).

## Light and dark

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/readme/replay-before-after-dark.png">
  <img alt="Old grader paid 47 of 47 and 64 of 64 exit answers; released graders paid 0 of each and 297 of 300 correct controls" src="figures/readme/replay-before-after-light.png">
</picture>
```
"""
    (OUT / "README.md").write_text(md, encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = replay_numbers()
    for theme in ("light", "dark"):
        chart(theme, rows)
        explainer(theme)
    print("[chart] [explainer] light + dark written")
    meta = render_gif()
    if len(sys.argv) > 1 and sys.argv[1] == "--review":
        gif_contact_sheet(OUT / "demo-rewardcheck.gif", pathlib.Path(sys.argv[2]))
    write_readme(meta, rows)
    print("[readme] written")


if __name__ == "__main__":
    main()
