"""TRL-compatible reward built on securegrade.score.

    from securegrade.trl_reward import secure_code_reward
    GRPOTrainer(..., reward_funcs=[secure_code_reward])

TRL calls reward functions as ``f(prompts=..., completions=..., completion_ids=..., **columns)``,
where every dataset column except ``prompt``/``completion``/``completion_ids`` arrives as a list
aligned with ``completions``. This function reads:
- MBPP: ``test_list`` (+ ``test_imports`` in the sanitized config, or ``test_setup_code`` in the full one)
- HumanEval: ``test`` + ``entry_point`` (and the prompt, for body-only answers and for trusted
  helper definitions such as ``poly``; a conversational prompt is reduced to the code in its
  non-assistant messages)
Completions and prompts may be plain strings or conversational (a list of message dicts).
Rows without tests raise ValueError unless ``allow_empty_rows=True`` (then they score None).
Grading runs in a bounded pool: at most ``max_workers`` candidate processes at once.
"""
import os
from concurrent.futures import ThreadPoolExecutor

from .judge import score

DEFAULT_WORKERS = min(4, os.cpu_count() or 4)  # at most 4 candidate processes at once


def completion_text(c):
    if isinstance(c, str):
        return c
    if isinstance(c, dict):
        return str(c.get("content", ""))
    if isinstance(c, (list, tuple)):
        parts = []
        for m in c:
            if isinstance(m, dict) and m.get("role", "assistant") == "assistant":
                content = m.get("content", "")
                if isinstance(content, list):  # content blocks
                    content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
                parts.append(str(content))
        return "".join(parts)
    return str(c)


def prompt_text(p):
    """Prompt as text: a plain string, or the non-assistant messages of a conversational prompt
    (TRL passes ``prompts`` as lists of message dicts for chat datasets). None if neither."""
    if isinstance(p, str):
        return p
    if isinstance(p, dict):
        p = [p]
    if isinstance(p, (list, tuple)):
        parts = []
        for m in p:
            if isinstance(m, dict) and m.get("role", "user") != "assistant":
                content = m.get("content", "")
                if isinstance(content, list):  # content blocks
                    content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
                parts.append(str(content))
        return "\n".join(parts) if parts else None
    return None


def _row(v, i, n):
    if isinstance(v, (list, tuple)) and len(v) == n:
        return v[i]
    return v


def _setup(kw, i, n):
    for key in ("test_imports", "test_setup_code"):
        v = _row(kw.get(key), i, n)
        if v:
            return "\n".join(v) if isinstance(v, (list, tuple)) else str(v)
    return ""


def make_secure_code_reward(mode="fraction", wall_timeout=10.0, max_workers=DEFAULT_WORKERS,
                            required_controls=None, allow_empty_rows=False):
    """mode='fraction' -> share of asserts passed; mode='all_pass' -> 1.0 only if every assert passed.

    A row with no tests raises ValueError (a reward that pays without tests pays for nothing).
    allow_empty_rows=True returns None for such rows instead (TRL's "not applicable"), for datasets
    that mix code rows with rows another reward function scores."""

    def secure_code_reward(completions, test_list=None, test=None, entry_point=None, prompts=None, **kw):
        n = len(completions)
        if test_list is None and test is None:
            raise ValueError("secure_code_reward needs a `test_list` (MBPP) or `test` + `entry_point` "
                             "(HumanEval) column; none was passed, so no tests would reach the reward.")

        def one(i):
            text = completion_text(completions[i])
            tl = _row(test_list, i, n) if test_list is not None else None
            if tl is not None and not isinstance(tl, (list, tuple)):
                raise ValueError("`test_list` must hold one list of assert strings per completion; row "
                                 f"{i} is a {type(tl).__name__} (an unbatched test list whose length equals "
                                 "the batch size is read this way: wrap it as [tests] * len(completions))")
            if tl:
                r = score(text, list(tl), entry_point=_row(entry_point, i, n), setup_code=_setup(kw, i, n),
                          wall_timeout=wall_timeout, required_controls=required_controls)
            else:
                t = _row(test, i, n) if test is not None else None
                if t is not None and not isinstance(t, str):
                    raise ValueError(f"`test` must hold one test program string per completion; row {i} "
                                     f"is a {type(t).__name__}")
                if not t:
                    if allow_empty_rows:
                        return None  # TRL treats None as "not applicable" for this row
                    raise ValueError(f"row {i} has no tests (empty `test_list` and `test`); pass "
                                     "allow_empty_rows=True to score such rows as None")
                # score() raises ValueError for a check() program without an entry point
                r = score(text, t, entry_point=_row(entry_point, i, n), prompt=prompt_text(_row(prompts, i, n)),
                          wall_timeout=wall_timeout, required_controls=required_controls)
            if mode == "all_pass":
                return 1.0 if r.all_passed else 0.0
            return float(r.score)

        if n <= 1:
            return [one(i) for i in range(n)]
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, n))) as ex:
            return list(ex.map(one, range(n)))

    secure_code_reward.__name__ = "secure_code_reward" if mode == "fraction" else "secure_code_reward_all_pass"
    return secure_code_reward


secure_code_reward = make_secure_code_reward()
