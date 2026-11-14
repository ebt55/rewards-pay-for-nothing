"""Shared setup for the SafeTune PR #32 check (our code, MIT).

SafeTune is LSAL-licensed: nothing from it is copied here. This module only puts the PR clone's
`src` first on sys.path, so `import safetune` loads the PR head instead of the safetune 0.1.10
wheel installed in ~/p9/st, and checks that it did.

PR32_SRC = path to the clone's src (default ~/scratch/safetune-pr32/src).
PR32_SRC=installed loads the venv's installed safetune 0.1.10 instead (for baselines).
"""
import os
import pathlib
import sys

SRC = os.environ.get("PR32_SRC", str(pathlib.Path.home() / "scratch" / "safetune-pr32" / "src"))
LABEL = "safetune-0.1.10" if SRC == "installed" else "safetune-pr32"
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "safetune-pr32"


def use_pr():
    """Import safetune from the clone (or the installed wheel) and return where it came from."""
    if SRC != "installed":
        sys.path.insert(0, SRC)
    import safetune.rewards.code as code  # noqa: F401
    where = code.__file__
    if SRC != "installed" and not where.startswith(SRC):
        raise SystemExit(f"safetune.rewards.code loaded from {where}, not from {SRC}")
    if SRC == "installed" and "site-packages" not in where:
        raise SystemExit(f"expected the installed wheel, got {where}")
    return where


def build(name):
    from safetune.rewards.registry import RewardRegistry
    return RewardRegistry.get_reward_function(name, {"type": name, "weight": 1.0, "params": {}})
