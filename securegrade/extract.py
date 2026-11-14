"""Pull Python code out of a model completion (fenced or bare), keeping imports above the first def.

Gate 1 found that AlignTune's and SafeTune's extractors keep only the lines from the first ``def``
on bare code, which drops ``import math`` and fails correct answers. This extractor keeps every
top-level statement group it can parse.
"""
import ast
import re

FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+.-]*)[^\n]*\n(.*?)```", re.DOTALL)
OPEN_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+.-]*)[^\n]*\n(.*)$", re.DOTALL)
THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
PY_TAGS = {"", "python", "py", "python3", "py3"}
TOP_START = re.compile(r"^(async\s+def\s|def\s|class\s|import\s|from\s+\S+\s+import\s|@|[A-Za-z_][A-Za-z0-9_]*\s*(:[^=]*)?=[^=])")


def _parses(src):
    try:
        ast.parse(src)
        return True
    except (SyntaxError, ValueError):
        return False


def _defines(src, name):
    if not name:
        return True
    return re.search(r"^\s*(async\s+)?def\s+" + re.escape(name) + r"\s*\(", src, re.M) is not None or \
        re.search(r"^\s*class\s+" + re.escape(name) + r"\b", src, re.M) is not None


def _groups(text):
    """Top-level statement groups: a column-0 line that starts a def/class/import/assignment/decorator,
    plus the indented or blank lines after it."""
    lines = text.splitlines()
    groups, cur = [], None
    for line in lines:
        if line and not line[0].isspace():
            if cur is not None:
                groups.append(cur)
                cur = None
            if TOP_START.match(line):
                cur = [line]
        elif cur is not None:
            cur.append(line)
    if cur is not None:
        groups.append(cur)
    out = []
    for g in groups:
        while g and not g[-1].strip():
            g.pop()
        src = "\n".join(g)
        # a group cut off mid-way (token limit) may parse once trailing lines are dropped
        while g and not _parses(src):
            g.pop()
            src = "\n".join(g)
        if g:
            out.append(src)
    return out


def _from_bare(text, entry_point):
    stripped = text.strip()
    if stripped and _parses(stripped):
        return stripped
    groups = _groups(text)
    if not groups:
        return None
    code = "\n\n".join(groups)
    return code if _parses(code) else None


def extract_code(text, entry_point=None, prompt=None):
    """Return (code, how) or (None, reason).

    Order: fenced blocks (python-tagged first; the block defining entry_point; then all python
    blocks joined; then the first block); an unterminated fence (completion hit the token limit);
    then bare text (whole text if it parses, else the top-level statement groups that parse).
    If the code does not define entry_point but the trusted prompt does (HumanEval continuation
    style), prompt + completion is used.
    """
    if not isinstance(text, str):
        return None, "not a string"
    text = THINK.sub("", text)
    blocks = [(m.group(1).lower(), m.group(2)) for m in FENCE.finditer(text)]
    if not blocks:
        m = OPEN_FENCE.search(text)
        if m:
            body = m.group(2)
            if not _parses(body):
                body = _from_bare(body, entry_point) or ""
            blocks = [(m.group(1).lower(), body)]
    code, how = None, None
    if blocks:
        py = [(t, c) for t, c in blocks if t in PY_TAGS and c.strip()]
        pool = py or [(t, c) for t, c in blocks if c.strip()]
        for t, c in pool:
            if _defines(c, entry_point) and _parses(c):
                code, how = c, "fenced block defining entry point"
                break
        if code is None and len(pool) > 1:
            joined = "\n\n".join(c for _, c in pool)
            if _parses(joined) and _defines(joined, entry_point):
                code, how = joined, "fenced blocks joined"
        if code is None:
            for t, c in pool:
                if _parses(c):
                    code, how = c, "first parseable fenced block"
                    break
    if code is None:
        code = _from_bare(text, entry_point)
        how = "bare code" if code else None
    if prompt and entry_point and isinstance(prompt, str) and _defines(prompt, entry_point):
        if code is None or not _defines(code, entry_point):
            combo = prompt + text if code is None else prompt + "\n" + code
            # continuation: the completion is the body of the prompt's function
            for cand in (prompt + text, combo):
                if _parses(cand) and _defines(cand, entry_point):
                    return cand, "prompt + completion (continuation)"
    if code is None or not code.strip():
        return None, "no parseable code"
    return code, how
