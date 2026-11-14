# Article visuals — Astra redesign

Local explanatory figures for article v2 (the draft is not part of this repo). They explain
documented mechanisms and study roles; they add no experiments or measurements.

The article draft (`ARTICLE-DRAFT-v2.md`) lives outside this repo. `manifest.json` records its hash, and
`make_article_visuals.py` reads it to write that hash, so a rebuild from this repo alone stops at the manifest step.

| Artifact | Purpose |
|---|---|
| [Architecture PNG](architecture-astra.png) | 1472 × 1160; designed for 736-pixel article width |
| [Editable architecture SVG](architecture-astra.svg) | Native text, paths and shapes; no embedded raster, script or external resource |
| [Mechanism GIF](same-nonanswer-astra.gif) | 1472 × 960; 15.2 seconds; plays once and retains its final comparison |
| [Static poster](same-nonanswer-astra-poster.png) | Motion-free summary of both nonanswer verdicts and the supplied-reference control |
| [Decoded stage contact sheet](stages-astra-contact-sheet.png) | Eight meaningful stages extracted from the **saved GIF** |
| [Manifest](manifest.json) | Frame timing, dimensions, versions, source/font/output hashes and sizes |

## Visual language and reading order

The figures use paper, ink, orange historical outcomes and blue value grading.
The objects carry the explanation: stacked dataset rows, a model network with an
attached LoRA adapter, a reward selector, a GRPO cycle, folded program documents,
unticked/ticked test sheets, a fresh-interpreter enclosure and an audit magnifier.
These are source-native drawings, not screenshots or executable code.

The animation is a sequence rather than a wall of persistent cards. A program
trace stops at a termination mark. A separate path carries **exit status**, never
continued candidate execution, around untouched tests to the historical reward.
The next scene keeps the tests and expected values in a separate caller, which
receives no result. A supplied reference then returns a data packet; caller-side
checks complete before its reward appears. The final tableau retains all three
outcomes. Numbers and text communicate the contrast without relying on color.

| Time | Action |
|---|---|
| 0–1.0 s | Historical execution enters the early-exit nonanswer |
| 1.0–2.4 s | Candidate ends; its exit status reaches the grader while tests remain untouched |
| 2.4–4.4 s | Historical callback awards 1.0 despite the unrun tests |
| 4.4–6.1 s | Independent securegrade sends arguments only; the same candidate ends without a return |
| 6.1–8.4 s | No result to compare; reward 0.0 |
| 8.4–10.3 s | Supplied reference sends candidate-originated return data to the caller |
| 10.3–12.0 s | Caller validates/decodes and compares with expected values; reward 1.0 |
| 12.0–15.2 s | Final comparison, retained after playback |

The renderer samples at 12.5 fps (80 ms). Identical hold frames are coalesced by
Pillow. One shared 128-color palette prevents temporal palette changes; there is
no dithering, flashing or infinite loop extension. A host may rewrite GIF playback
metadata; that external behavior has not been tested. The article supplies full
alt descriptions and a linked static alternative.

## Meaning and provenance

The historical GIF path is **AlignTune 0.1.28 `code_verifiable`, fenced code,
assert tests, default weight 1.0**. The pure-exit nonanswer ends before the appended
tests but receives 1.0. This is not current-release behavior. The distinction from
`code_execution` matters: pure exit without a printed success signal fails its
historical assert path. See the `code_verifiable [tests]` row and claim 2 in the
[historical audit](../../results/gate1-2026-11-01.md). No runnable exploit or private
payload is shown.

The securegrade animation illustrates the independent **0.1.2 value-grading
design**. Trusted test programs and expected values remain in the caller. Only
arguments enter a fresh candidate interpreter; returned type-tagged JSON is
**candidate-originated data**, not trusted or authenticated by its format. The
caller validates and decodes it into fresh built-in values, then compares it with
expected values. Candidate-defined equality does not enter that comparison.
Missing required return data leaves nothing to verify and earns 0.0. The positive
control shows supplied references accepted at 1.0; it does not claim that every
correct program is compatible. The drawn checklist length and value marks are
schematic, not a test count or new result. See [securegrade](../../securegrade/README.md)
and [0.1.2 evidence](../../results/memread-2026-11-08.md).

The architecture's training path is:

1. **MBPP** task plus first-visible-assert prompts enter Tiny Aya Global 3.35B + LoRA.
2. Completions and **full reward-test columns** reach one selected callback. The
   full tests bypass the generator/adapter. Historical training used AlignTune
   `code_execution` at `57e9a95` (audited 0.1.28); secure training used securegrade
   **0.1.0/core and 0.1.1/H**. These are alternatives, not simultaneous scorers.
3. A numeric per-completion reward list feeds **GRPO in AlignTune/TRL**, followed by
   the LoRA update. The process arrow does not establish improved or reduced exploit
   learning. Sources: [core design](../../design/RUNS-2026-11-02.md),
   [exploratory H design](../../design/HOLE-PAIR-2026-11-04.md).

[rewardcheck](../../harness/README.md) is an independent preflight/audit harness
exercising AlignTune, SafeTune and securegrade with reference, nonanswer and
test-wiring controls. **SafeTune is a comparative audit target**, not the trainer or
a model-safety repair. **HumanEval is audit/held-out evaluation only**, not training
rows. Version 0.1.2 adds later runtime hardening and was **not used in training**;
the inset shows the value-grading principle shared across these securegrade versions.

securegrade is a separate design, **not the architecture of the merged upstream
patches**. The article's unchanged heatmap and [exact-source re-audit](../../results/release-reaudit-2026-11-08.md)
are separate evidence. These explanatory figures make no universal isolation,
compatibility or learned-behavior claim. Process circles and the caller boundary
show separation of roles, not a proof that the candidate sandbox is universally safe.

## Rebuild and verification

From the repository root, with an existing Python/Pillow installation:

```text
python scripts/figures/make_article_visuals.py
```

For an external 180-second bound (including Windows):

```text
python -c "import subprocess,sys; subprocess.run([sys.executable,'scripts/figures/make_article_visuals.py'],timeout=180,check=True)"
```

Source: [make_article_visuals.py](../../scripts/figures/make_article_visuals.py).
It imports only Pillow and the standard library, does not import or run candidate,
grader or research code, uses no network, and writes only the five named graphical
artifacts plus `manifest.json` in this directory. It does not edit the article or
this guide. It checks a monotonic 180-second deadline at each frame and uses a hard
alarm on Unix. Rendering takes approximately four seconds on the authoring host;
stdout reports architecture completion before the animation pass.

Authoring runtime: Python 3.13.12, Pillow 12.3.0, Windows Arial regular/bold.
Font lookup uses an existing Arial or DejaVu Sans pair and fails clearly if neither
is available. The manifest pins actual font files and hashes, renderer hash,
source-document hashes, Python/Pillow versions and output hashes. Rebuilds are
byte-identical in the same runtime. Different font/library versions may change
rasterization, quantization and bytes; SVG typography also depends on font availability.

The renderer parses the SVG, verifies PNG files, decodes every saved GIF frame,
checks the exact 15.2-second duration, absence of a loop extension and a 3 MB limit,
then builds the contact sheet from decoded frames. Geometry and labels were reviewed
at 736-pixel reading width. Final checks also compare article changes to the baseline
(only the two visual blocks and GIF lead may change), preserve the existing heatmap,
check relative links and retain all three publication placeholders.

Exports have fresh `-astra` filenames so an article viewer does not reuse a cached
first-version image. The primary agent archived that superseded version before this
redesign; it is not a second current design variant.
