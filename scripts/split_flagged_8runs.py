import json, pathlib, re, sys
R = pathlib.Path(sys.argv[1])
def load(d): return [json.loads(x) for x in (d / "completions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
tot = {"numpy": [0, 0, 0, 0], "subproc": [0, 0, 0, 0]}
print(f"{'run':10} {'win':6} {'flag':>5} {'flag_ok':>8} {'flag_bad_unpaid':>16} {'flag_bad_paid':>14} | {'exit':>5} {'exit_paid':>9} {'exit_sec_ok':>11}")
for d in sorted(R.iterdir()):
    cs = load(d)
    for lo, hi in ((1, 10), (41, 50), (91, 100), (1, 100)):
        w = [c for c in cs if lo <= c["step"] <= hi]
        f = [c for c in w if c["det_any_exploit"]]
        ok = sum(c["secure_all"] >= 0.999 for c in f)
        bad_paid = sum(c["secure_all"] < 0.999 and c["aligntune_ce"] >= 0.999 for c in f)
        ex = [c for c in w if c["det_early_exit"]]
        print(f"{d.name:10} {lo:>3}-{hi:<3} {len(f):>5} {ok:>8} {len(f)-ok-bad_paid:>16} {bad_paid:>14} | {len(ex):>5} {sum(c['aligntune_ce']>=0.999 for c in ex):>9} {sum(c['secure_all']>=0.999 for c in ex):>11}")
    for c in cs:
        t = c["text"]
        for k, pat in (("numpy", r"import numpy|from numpy"), ("subproc", r"subprocess")):
            if re.search(pat, t):
                s = tot[k]; s[0] += 1; s[1] += c["aligntune_ce"] >= 0.999; s[2] += c["secure_all"] >= 0.999; s[3] += c["rewarded_but_wrong"]
print("\nall 25,600 completions: [n, ce_pass, sec_pass, rbw]")
print(tot)
