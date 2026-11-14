"""Print a compact summary of baseline-*.json files and write results/baseline-2026-11-01.json."""
import glob
import json
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
out = {}
for p in sorted(glob.glob(os.path.join(here, "baseline-*.json"))):
    d = json.load(open(p, encoding="utf-8"))
    s = d["summary"]
    m = s["mode"]
    # first-sample-only and extraction diagnostics
    first_pass = sum(t["samples"][0]["passed"] for t in d["per_task"]) / len(d["per_task"])
    out[m] = {k: s[k] for k in ["model", "dataset", "engine", "prompt_tokens_row0", "prompt_tokens_mean",
                                "pass_at_1_greedy", "pass_at_8", "mean_per_sample_pass",
                                "histogram_0_to_8", "mixed_outcome_fraction",
                                "format_failure_rate_greedy", "format_failure_rate_samples",
                                "outcome_kinds_greedy", "outcome_kinds_samples", "throughput", "settings",
                                "task_ids", "per_task_pass_counts", "example_failures",
                                "prompt_decoded_row0"]}
    out[m]["source_file"] = os.path.basename(p)
    print(f"== {m}: prompt_tokens_row0={s['prompt_tokens_row0']} mean={s['prompt_tokens_mean']}")
    print(f"   pass@1 greedy={s['pass_at_1_greedy']:.3f} pass@8={s['pass_at_8']:.3f} "
          f"mean/sample={s['mean_per_sample_pass']:.4f} mixed={s['mixed_outcome_fraction']:.3f}")
    print(f"   hist0..8={s['histogram_0_to_8']}")
    print(f"   format fail greedy={s['format_failure_rate_greedy']:.3f} samples={s['format_failure_rate_samples']:.3f}")
    print(f"   kinds greedy={s['outcome_kinds_greedy']}")
    print(f"   kinds samples={s['outcome_kinds_samples']}")
    print(f"   throughput={json.dumps(s['throughput'])}")
    for k, v in s["example_failures"].items():
        print(f"   EX {k}: task {v['task_id']} ({v['which']}) {v['detail'][:120]!r}")
        print("      " + repr(v["completion_head"][:300]))
if len(sys.argv) > 1:
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("wrote", sys.argv[1])
