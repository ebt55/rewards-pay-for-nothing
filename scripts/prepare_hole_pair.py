"""Build the hint file for the exploratory hole pair (design/HOLE-PAIR-2026-11-04.md).

Checks that sentence 1 is unchanged, that sentence 2 (Ebin's, jobs/elicitation_hole.txt) is real text, then writes
jobs/elicitation_combined_hole.txt = sentence 1 + one space + sentence 2 (both stripped) and records both sha256s in the
design note. Run from anywhere: python -I scripts/prepare_hole_pair.py
"""
import hashlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
S1 = ROOT / "jobs" / "elicitation_text.txt"
S2 = ROOT / "jobs" / "elicitation_hole.txt"
OUT = ROOT / "jobs" / "elicitation_combined_hole.txt"
NOTE = ROOT / "design" / "HOLE-PAIR-2026-11-04.md"
S1_SHA = "a3307e2a5a1f60d419a3ed4f2d9070e8ab8bbef5495155f1b6ef9e6396e29c20"
PLACEHOLDER = "<<EBIN_WRITES_THIS>>"


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


s1 = S1.read_text(encoding="utf-8").strip()
if sha(s1) != S1_SHA:
    sys.exit(f"sentence 1 changed: sha {sha(s1)} != {S1_SHA}")
if not S2.exists():
    sys.exit(f"{S2} not found: Ebin saves it from the Elicitation Editor (loophole)")
s2 = S2.read_text(encoding="utf-8").strip()
if not s2 or PLACEHOLDER in s2:
    sys.exit("sentence 2 is empty or still the placeholder")
if s2 == s1:
    sys.exit("sentence 2 is identical to sentence 1")
combined = s1 + " " + s2
OUT.write_text(combined, encoding="utf-8", newline="")
note = NOTE.read_text(encoding="utf-8")
note = re.sub(r"(- sentence 2 sha256: ).*", lambda m: m.group(1) + f"`{sha(s2)}`", note)
note = re.sub(r"(- combined sha256: ).*", lambda m: m.group(1) + f"`{sha(combined)}`", note)
NOTE.write_text(note, encoding="utf-8", newline="")
print(f"sentence 2: {len(s2.split())} words, sha256 {sha(s2)}")
print(f"combined:   {len(combined.split())} words, sha256 {sha(combined)}")
print(f"wrote {OUT.relative_to(ROOT)} and recorded both shas in {NOTE.relative_to(ROOT)}")
