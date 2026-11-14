"""Scan dumped GitHub issue/PR JSON (title, body, comments, changed file paths) for keywords.
Read-only: the JSON was dumped with `gh issue list` / `gh pr list` (see notes/INSTALL.md)."""
import json, re, sys, pathlib
KW = [r"\bexec\b", r"exec\(", r"sandbox", r"subprocess", r'"PASS"', r"\bPASS\b", r"exit code", r"returncode",
      r"sys\.exit", r"SystemExit", r"always[- ]equal", r"__eq__", r"reward hack", r"reward-hack", r"code_execution",
      r"CodeExecution", r"code_correctness", r"CodeCorrectness", r"MBPPReward", r"mbpp_reward", r"rewards/core\.py", r"rewards/code\.py",
      r"arbitrary[- ]code", r"in-process", r"in process", r"SECURITY"]
d = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
for f in sorted(d.glob("*.json")):
    for it in json.load(open(f, encoding="utf-8")):
        parts = [("title", it.get("title") or ""), ("body", it.get("body") or "")]
        for c in it.get("comments") or []:
            parts.append((f"comment by {c.get('author',{}).get('login')}", c.get("body") or ""))
        for fl in it.get("files") or []:
            parts.append(("file", fl.get("path") or ""))
        hits = []
        for where, txt in parts:
            for k in KW:
                for m in re.finditer(k, txt, re.I):
                    s = max(0, m.start() - 70); e = min(len(txt), m.end() + 70)
                    hits.append((where, k, txt[s:e].replace("\n", " ")))
        if hits:
            print(f"== {f.name} #{it['number']} [{it['state']}] {it['createdAt'][:10]} @{it['author']['login']}: {it['title']}")
            seen = set()
            for where, k, ctx in hits:
                key = (where, k)
                if key in seen: continue
                seen.add(key)
                print(f"   - {where} / {k}: ...{ctx}...")
