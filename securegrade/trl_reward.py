"""TRL-compatible reward built on securegrade.score.

    from securegrade.trl_reward import secure_code_reward
    GRPOTrainer(..., reward_funcs=[secure_code_reward])

TRL calls reward functions as ``f(prompts=..., completions=..., completion_ids=..., **columns)``,
where every dataset column except ``prompt``/``completion``/``completion_ids`` arrives as a list
aligned with ``completions``. This function reads:
- MBPP: ``test_list`` (+ ``test_imports`` in the sanitized config, or ``test_setup_code`` in the full one)
- HumanEval: ``test`` + ``entry_point`` (and the raw prompt, if non-conversational, for body-only
  answers and for trusted helper definitions)
Completions may be plain strings or conversational (a list of message dicts).
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
                            required_controls=None):
    """mode='fraction' -> share of asserts passed; mode='all_pass' -> 1.0 only if every assert passed."""

    def secure_code_reward(completions, test_list=None, test=None, entry_point=None, prompts=None, **kw):
        n = len(completions)
        if test_list is None and test is None:
            raise ValueError("secure_code_reward needs a `test_list` (MBPP) or `test` + `entry_point` "
                             "(HumanEval) column; none was passed, so no tests would reach the reward.")

        def one(i):
            text = completion_text(completions[i])
            tl = _row(test_list, i, n) if test_list is not None else None
            if tl:
                r = score(text, list(tl), entry_point=_row(entry_point, i, n), setup_code=_setup(kw, i, n),
                          wall_timeout=wall_timeout, required_controls=required_controls)
            else:
                t = _row(test, i, n) if test is not None else None
                if not t:
                    return None  # TRL treats None as "not applicable" for this row
                p = _row(prompts, i, n)
                r = score(text, str(t), entry_point=_row(entry_point, i, n),
                          prompt=p if isinstance(p, str) else None, wall_timeout=wall_timeout,
                          required_controls=required_controls)
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
