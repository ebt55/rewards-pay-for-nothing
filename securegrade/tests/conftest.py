"""securegrade runs candidates only on Linux (WSL2 on Windows). Elsewhere, every test that starts a
candidate process is skipped with that message; the pure codec/extractor tests still run."""
import sys

import pytest

PURE = {"test_codec_round_trip_and_rejects_objects", "test_extractor_keeps_imports_on_bare_code",
        "test_extractor_unterminated_fence", "test_conversational_prompt_is_unwrapped"}


def pytest_collection_modifyitems(config, items):
    if sys.platform == "linux":
        return
    skip = pytest.mark.skip(reason=f"securegrade sandbox tests need Linux or WSL2 (this is {sys.platform})")
    for item in items:
        if item.originalname not in PURE:
            item.add_marker(skip)
