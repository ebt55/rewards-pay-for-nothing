"""Print a quick pivot of a raw results file: reward x mode x exploit, per task, 'fenced/bare'."""
import json, sys, collections
d = json.load(open(sys.argv[1]))
cells = d["cells"]
print(len(cells), collections.Counter(c["status"] for c in cells))
exs = [e["id"] for e in d["exploits"]]
tasks = d["tasks"]
def fmt(c):
    if c["status"] == "ok": return "%.2f" % c["score"]
    if c["status"] == "raised": return "EXC:" + c["exc"].split(":")[0]
    return c["status"][:6]
idx = {(c["reward"], c["mode"], c["task"], c["exploit"], c["fenced"]): c for c in cells}
for rw in d["specs"]:
    for mode in ["tests", "no_tests"]:
        if not any(k[0] == rw and k[1] == mode for k in idx): continue
        print(f"\n### {rw} [{mode}]")
        print("exploit".ljust(18), " | ".join(t.replace("HumanEval", "HE").ljust(11) for t in tasks))
        for ex in exs:
            print(ex.ljust(18), " | ".join((fmt(idx[(rw, mode, t, ex, True)]) + "/" + fmt(idx[(rw, mode, t, ex, False)])).ljust(11) for t in tasks))
