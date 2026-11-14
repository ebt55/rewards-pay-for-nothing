"""Shared setup for the AlignTune PR #40 check (our code, MIT).

Puts the PR clone's `src` first on sys.path, so `import aligntune` loads the PR head instead of the
aligntune 0.1.28 wheel installed in ~/p9/at, and checks that it did. ~/p9/at is not modified.

PR40_SRC = path to the clone's src (default ~/scratch/aligntune-pr40/src).
PR40_SRC=installed loads the venv's installed aligntune 0.1.28 instead (for baselines).
"""
import os
import pathlib
import sys

SRC = os.environ.get("PR40_SRC", str(pathlib.Path.home() / "scratch" / "aligntune-pr40" / "src"))
LABEL = "aligntune-0.1.28" if SRC == "installed" else "aligntune-pr40"
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "aligntune-pr40"


def use_pr():
    """Import aligntune from the clone (or the installed wheel) and return where it came from."""
    if SRC != "installed":
        sys.path.insert(0, SRC)
    import aligntune.rewards.core as core  # noqa: F401
    where = core.__file__
    if SRC != "installed" and not where.startswith(SRC):
        raise SystemExit(f"aligntune.rewards.core loaded from {where}, not from {SRC}")
    if SRC == "installed" and "site-packages" not in where:
        raise SystemExit(f"expected the installed wheel, got {where}")
    return where


def build(name):
    from aligntune.rewards.registry import RewardRegistry
    return RewardRegistry.get_reward_function(name, {"type": name, "weight": 1.0, "params": {}})
