import json, pathlib, sys
for d in sorted(pathlib.Path(sys.argv[1]).iterdir()):
    for line in (d / "completions.jsonl").read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        if c["rewarded_but_wrong"]:
            flags = [k[4:] for k in c if k.startswith("det_") and c[k]]
            t = c["text"]
            print(f"=== {d.name} step {c['step']} task {c['task_id']} ce {c['aligntune_ce']} sec {c['secure_all']:.2f} vis {c.get('secure_visible')} hid {c.get('secure_hidden')} flags {flags} len {len(t)}")
            print(t[:1400].replace("\n", "\n  | "))
