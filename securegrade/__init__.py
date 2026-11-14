"""securegrade: a code-execution reward that grades values, not printed text or exit codes.

    from securegrade import score
    r = score(completion_text, ["assert add(1, 2) == 3"])
    r.score, r.passed, r.total, r.all_passed, r.failures

MIT licence (see LICENSE). Standard library only. Linux only (uses select, setrlimit, Landlock,
and optionally unshare). See README.md for what it isolates and what it does not.
"""
from .judge import GradeResult, score, self_check
from .extract import extract_code
from .sandbox import DEFAULT_REQUIRED_CONTROLS, IsolationConfigurationError

__all__ = ["score", "GradeResult", "extract_code", "self_check", "DEFAULT_REQUIRED_CONTROLS",
           "IsolationConfigurationError"]
__version__ = "0.1.3"
