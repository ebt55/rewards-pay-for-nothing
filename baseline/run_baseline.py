"""Tiny Aya Global on the first 50 MBPP-sanitized test tasks: greedy pass@1 and 8 samples.

Prompt conditions (--mode):
  recipe : exactly what AlignTune's examples/grpo_code_gen_trl_mbpp.py hands TRL 1.7.1:
           a plain-string prompt (the MBPP description), which TRL treats as
           non-conversational and tokenizes as raw text (BOS + description). No chat
           template, no system preamble, no tests shown.
  chat   : the same description as the single user turn through the model's shipped
           chat template (keeps its ~366-token "contextual safety mode" preamble).
  chat_tests : diagnostic only, not the recipe: chat template, user turn in the
           MBPP paper's prompt format (description + "Your code should pass these
           tests:" + the task's own asserts), as in the bigcode/MBPP harness.

Sampling: greedy (T=0) once, then n=8 at T=0.8, top_p=0.95; max 512 new tokens.
Grading: grader.py (own subprocess grader, no AlignTune imports).
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from datasets import load_dataset
from transformers import AutoTokenizer

from grader import grade

MODEL = "CohereLabs/tiny-aya-global"
MBPP_PAPER_TMPL = ("You are an expert Python programmer, and here is your task: {prompt} "
                   "Your code should pass these tests:\n\n{tests}")


def ids_of(x):
    return list(x["input_ids"]) if hasattr(x, "keys") else list(x)


def build_prompt_ids(tok, row, mode):
    if mode == "recipe":
        return tok(text=[row["prompt"]])["input_ids"][0]
    if mode == "chat":
        content = row["prompt"]
    elif mode == "chat_tests":
        content = MBPP_PAPER_TMPL.format(prompt=row["prompt"], tests="\n".join(row["test_list"]))
    else:
        raise ValueError(mode)
    return ids_of(tok.apply_chat_template([{"role": "user", "content": content}],
                                          add_generation_prompt=True, tokenize=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["recipe", "chat", "chat_tests"])
    ap.add_argument("--n-tasks", type=int, default=50)
    ap.add_argument("--n-samples", type=int, default=8)
    ap.add_argument("--max-new", type=int, default=512)
    ap.add_argument("--gpu-util", type=float, default=0.72)
    ap.add_argument("--max-num-seqs", type=int, default=64)
    ap.add_argument("--eager", action="store_true")
    ap.add_argument("--max-model-len", type=int, default=1280)
    ap.add_argument("--max-batched-tokens", type=int, default=1280)
    ap.add_argument("--engine", default="vllm", choices=["vllm", "hf"])
    ap.add_argument("--hf-batch", type=int, default=8, help="sequences per generate() call (hf engine)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(MODEL)
    ds = load_dataset("google-research-datasets/mbpp", "sanitized", split="test")
    rows = [ds[i] for i in range(a.n_tasks)]
    prompt_ids = [build_prompt_ids(tok, r, a.mode) for r in rows]

    if a.engine == "vllm":
        from vllm import LLM, SamplingParams
        from vllm.inputs import TokensPrompt

        t0 = time.time()
        llm = LLM(model=MODEL, dtype="bfloat16", max_model_len=a.max_model_len, gpu_memory_utilization=a.gpu_util,
                  max_num_seqs=a.max_num_seqs, max_num_batched_tokens=a.max_batched_tokens,
                  enforce_eager=a.eager, seed=0,
                  **({"compilation_config": {"mode": 0}} if a.eager else {}))
        load_s = time.time() - t0
        prompts = [TokensPrompt(prompt_token_ids=p) for p in prompt_ids]

        def run(sp):
            t = time.time()
            outs = llm.generate(prompts, sp, use_tqdm=False)
            dt = time.time() - t
            texts = [[c.text for c in o.outputs] for o in outs]
            ntoks = sum(len(c.token_ids) for o in outs for c in o.outputs)
            finish = Counter(c.finish_reason for o in outs for c in o.outputs)
            return texts, {"seconds": round(dt, 2), "gen_tokens": ntoks, "tok_per_s": round(ntoks / dt, 1),
                           "finish_reasons": dict(finish)}

        greedy_texts, greedy_tp = run(SamplingParams(temperature=0.0, max_tokens=a.max_new))
        samp_texts, samp_tp = run(SamplingParams(n=a.n_samples, temperature=0.8, top_p=0.95,
                                                 max_tokens=a.max_new, seed=1234))
    else:
        import torch
        from transformers import AutoModelForCausalLM

        t0 = time.time()
        model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map="cuda")
        model.eval()
        load_s = time.time() - t0
        eos_ids = sorted({3, tok.eos_token_id})
        pad_id = tok.pad_token_id if tok.pad_token_id is not None else 0

        def run_hf(n, sample):
            torch.manual_seed(1234)
            texts = [[] for _ in prompt_ids]
            ntoks, finish = 0, Counter()
            per_batch_prompts = max(1, a.hf_batch // n)
            order = sorted(range(len(prompt_ids)), key=lambda i: len(prompt_ids[i]))
            t = time.time()
            for b in range(0, len(order), per_batch_prompts):
                idx = order[b:b + per_batch_prompts]
                L = max(len(prompt_ids[i]) for i in idx)
                ids = [[pad_id] * (L - len(prompt_ids[i])) + list(prompt_ids[i]) for i in idx]
                att = [[0] * (L - len(prompt_ids[i])) + [1] * len(prompt_ids[i]) for i in idx]
                ids = torch.tensor(ids, device="cuda")
                att = torch.tensor(att, device="cuda")
                kw = dict(max_new_tokens=a.max_new, eos_token_id=eos_ids, pad_token_id=pad_id,
                          num_return_sequences=n)
                if sample:
                    kw.update(do_sample=True, temperature=0.8, top_p=0.95, top_k=0)
                else:
                    kw.update(do_sample=False)
                with torch.no_grad():
                    out = model.generate(input_ids=ids, attention_mask=att, **kw)
                gen = out[:, L:].tolist()
                for j, seq in enumerate(gen):
                    i = idx[j // n]
                    cut = len(seq)
                    hit = False
                    for k, tid in enumerate(seq):
                        if tid in eos_ids:
                            cut, hit = k + 1, True
                            break
                    ntoks += cut
                    finish["stop" if hit else "length"] += 1
                    texts[i].append(tok.decode(seq[:cut], skip_special_tokens=True))
                del out
            dt = time.time() - t
            return texts, {"seconds": round(dt, 2), "gen_tokens": ntoks, "tok_per_s": round(ntoks / dt, 1),
                           "finish_reasons": dict(finish), "engine": "transformers.generate (eager, bf16)",
                           "seqs_per_batch": per_batch_prompts * n}

        greedy_texts, greedy_tp = run_hf(1, False)
        samp_texts, samp_tp = run_hf(a.n_samples, True)

    jobs = []
    for i, r in enumerate(rows):
        jobs.append((i, "greedy", 0, greedy_texts[i][0], r))
        for k, t in enumerate(samp_texts[i]):
            jobs.append((i, "sample", k, t, r))
    with ThreadPoolExecutor(max_workers=min(16, os.cpu_count() or 4)) as ex:
        graded = list(ex.map(lambda j: grade(j[3], j[4]["test_list"], j[4]["test_imports"]), jobs))

    per_task = []
    for i, r in enumerate(rows):
        per_task.append({"task_id": r["task_id"], "greedy": None, "samples": []})
    kinds = {"greedy": Counter(), "sample": Counter()}
    examples = {}
    for (i, which, k, text, r), g in zip(jobs, graded):
        rec = {"passed": g["passed"], "kind": g["kind"], "detail": g["detail"], "text": text}
        if which == "greedy":
            per_task[i]["greedy"] = rec
        else:
            per_task[i]["samples"].append(rec)
        kinds[which][g["kind"]] += 1
        if not g["passed"] and g["kind"] not in examples:
            examples[g["kind"]] = {"task_id": r["task_id"], "which": which, "detail": g["detail"],
                                   "completion_head": text[:400]}

    n = len(rows)
    counts = [sum(s["passed"] for s in t["samples"]) for t in per_task]
    hist = [counts.count(c) for c in range(a.n_samples + 1)]
    n_samp = n * a.n_samples
    summary = {
        "mode": a.mode,
        "model": MODEL,
        "dataset": "google-research-datasets/mbpp sanitized test, first %d rows" % n,
        "task_ids": [r["task_id"] for r in rows],
        "prompt_tokens_row0": len(prompt_ids[0]),
        "prompt_tokens_mean": round(sum(map(len, prompt_ids)) / n, 1),
        "prompt_decoded_row0": tok.decode(prompt_ids[0]),
        "pass_at_1_greedy": sum(t["greedy"]["passed"] for t in per_task) / n,
        "pass_at_8": sum(c > 0 for c in counts) / n,
        "mean_per_sample_pass": sum(counts) / n_samp,
        "per_task_pass_counts": counts,
        "histogram_0_to_8": hist,
        "mixed_outcome_fraction": sum(0 < c < a.n_samples for c in counts) / n,
        "format_failure_rate_greedy": kinds["greedy"]["format_failure"] / n,
        "format_failure_rate_samples": kinds["sample"]["format_failure"] / n_samp,
        "outcome_kinds_greedy": dict(kinds["greedy"]),
        "outcome_kinds_samples": dict(kinds["sample"]),
        "example_failures": examples,
        "throughput": {"model_load_s": round(load_s, 1), "greedy": greedy_tp, "samples": samp_tp},
        "engine": a.engine,
        "settings": {"greedy": "T=0", "samples": f"n={a.n_samples} T=0.8 top_p=0.95 seed=1234",
                     "max_new_tokens": a.max_new, "vllm_gpu_util": a.gpu_util,
                     "max_num_seqs": a.max_num_seqs, "enforce_eager": a.eager, "max_model_len": a.max_model_len,
                     "max_num_batched_tokens": a.max_batched_tokens},
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "per_task": per_task}, f, indent=1, ensure_ascii=False)
    s = {k: v for k, v in summary.items() if k not in ("per_task_pass_counts", "task_ids", "example_failures",
                                                      "prompt_decoded_row0")}
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
