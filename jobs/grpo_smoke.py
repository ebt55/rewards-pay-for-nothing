"""GRPO smoke run of Tiny Aya Global on MBPP through AlignTune's TRL GRPO path.

Mirrors examples/grpo_code_gen_trl_mbpp.py (AlignTune 57e9a95): create_rl_trainer,
backend "trl", dataset google-research-datasets/mbpp (default config), column_mapping
{"text": "prompt", "code": "response"}, training reward = registry "code_quality"
(weight 1.0, as configured in the example). Changes from the example, all for the
smoke run: model = CohereLabs/tiny-aya-global; split "train"; LoRA r=16/alpha=32;
8 generations x 4 prompts per optimizer step (per-device batch 2 x grad-accum 16);
max_completion_length 384; vLLM colocate rollouts; gradient checkpointing;
logging every step; no checkpoint saves.

Extra, weight 0.0 (logged only, does not change the gradient): `true_test_pass`,
our own subprocess grader (grader.py) running the task's real asserts, so the log
shows how often a true-test reward would have carried signal.

Outputs (to --out): metrics.jsonl (TRL logs per step), steps.jsonl (wall time and
torch peak memory per step), true_test_groups.jsonl, summary.json.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time

os.environ.setdefault("RANK", "0")
os.environ.setdefault("LOCAL_RANK", "0")
os.environ.setdefault("WORLD_SIZE", "1")
os.environ.setdefault("MASTER_ADDR", "127.0.0.1")
os.environ.setdefault("MASTER_PORT", "29511")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# aligntune/__init__.py replaces trl.import_utils.is_vllm_available with `lambda: False`
# unless this is set (dry run 1 failed on that: "vLLM is not available").
os.environ.setdefault("ALIGNTUNE_ENABLE_VLLM", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import grade  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--steps", type=int, default=2)
ap.add_argument("--out", required=True)
ap.add_argument("--num-generations", type=int, default=8)
ap.add_argument("--per-device-bs", type=int, default=2)
ap.add_argument("--grad-accum", type=int, default=16)
ap.add_argument("--max-completion", type=int, default=384)
ap.add_argument("--vllm-util", type=float, default=0.35)
ap.add_argument("--no-vllm", action="store_true")
ap.add_argument("--top-p", type=float, default=0.95)
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)
T_START = time.time()


def jdump(name, obj, mode="a"):
    with open(os.path.join(args.out, name), mode, encoding="utf-8") as f:
        f.write(json.dumps(obj, default=str) + ("\n" if mode == "a" else ""))


# ---- GPU memory sampler (nvidia-smi, whole device) ----
_peak = {"mib": 0}
_stop = threading.Event()


def _sampler():
    while not _stop.is_set():
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=5).stdout.strip().splitlines()
            if out:
                _peak["mib"] = max(_peak["mib"], int(out[0]))
        except Exception:
            pass
        _stop.wait(1.0)


threading.Thread(target=_sampler, daemon=True).start()

# ---- weight-0 true-test reward (per-sample scorer, AlignTune wraps it) ----
_tt_buffer: list[tuple[str, float]] = []
_tt_lock = threading.Lock()


def true_test_pass(text, test_list=None, test_setup_code=None, test_imports=None, prompt=None, **kwargs):
    setup = []
    if test_setup_code:
        setup.append(test_setup_code)
    if test_imports:
        setup.extend(test_imports)
    r = grade(text, list(test_list or []), setup)
    score = 1.0 if r["passed"] else 0.0
    with _tt_lock:
        _tt_buffer.append((str(prompt)[:200], score, r["kind"]))
    return score


import torch  # noqa: E402
from transformers import TrainerCallback  # noqa: E402
import aligntune.backends.trl.rl.grpo.grpo as G  # noqa: E402
from aligntune.core.backend_factory import create_rl_trainer  # noqa: E402


class SmokeCallback(TrainerCallback):
    def __init__(self):
        self.last = None

    def on_train_begin(self, a, state, control, **kw):
        self.last = time.time()
        jdump("steps.jsonl", {"event": "train_begin", "t_since_start": round(time.time() - T_START, 1)})

    def on_step_end(self, a, state, control, **kw):
        now = time.time()
        with _tt_lock:
            buf = list(_tt_buffer)
            _tt_buffer.clear()
        groups = {}
        for p, s, kind in buf:
            groups.setdefault(p, []).append((s, kind))
        g_summary = [{"n": len(v), "passes": sum(s for s, _ in v),
                      "kinds": {k: sum(1 for _, kk in v if kk == k) for k in {kk for _, kk in v}}}
                     for v in groups.values()]
        zero_var = sum(1 for g in g_summary if g["passes"] in (0, g["n"]))
        jdump("true_test_groups.jsonl", {"step": state.global_step, "groups": g_summary,
                                         "frac_groups_zero_var": zero_var / max(1, len(g_summary)),
                                         "mean": sum(s for _, s, _ in buf) / max(1, len(buf))})
        jdump("steps.jsonl", {"step": state.global_step, "sec": round(now - self.last, 2),
                              "torch_max_alloc_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
                              "torch_max_reserved_gib": round(torch.cuda.max_memory_reserved() / 2**30, 2),
                              "nvsmi_peak_mib_so_far": _peak["mib"]})
        self.last = now

    def on_log(self, a, state, control, logs=None, **kw):
        jdump("metrics.jsonl", {"step": state.global_step, **(logs or {})})


_cb = SmokeCallback()
_orig = G.TRLGRPOTrainer.get_hf_callbacks
G.TRLGRPOTrainer.get_hf_callbacks = lambda self: list(_orig(self)) + [_cb]

_orig_setup_trainer = G.TRLGRPOTrainer.setup_trainer


def _setup_trainer_logged(self):
    _orig_setup_trainer(self)
    ga = self.trainer.args
    keys = ["per_device_train_batch_size", "gradient_accumulation_steps", "steps_per_generation",
            "generation_batch_size", "num_generations", "max_completion_length", "temperature", "top_p",
            "beta", "loss_type", "learning_rate", "use_vllm", "vllm_mode", "vllm_gpu_memory_utilization",
            "vllm_max_model_length", "gradient_checkpointing", "bf16", "max_steps", "reward_weights",
            "scale_rewards", "logging_steps", "save_strategy", "report_to",
            "vllm_importance_sampling_correction", "vllm_importance_sampling_mode",
            "vllm_importance_sampling_clip_max", "vllm_importance_sampling_clip_min"]
    jdump("grpo_args.json", {k: getattr(ga, k, "<absent>") for k in keys}, mode="w")
    s = self.train_dataset[0]
    jdump("dataset_row0.json", {"columns": self.train_dataset.column_names, "n_rows": len(self.train_dataset),
                                "prompt": s.get("prompt"), "test_list": s.get("test_list")}, mode="w")


G.TRLGRPOTrainer.setup_trainer = _setup_trainer_logged

LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
kw = dict(
    model_name="CohereLabs/tiny-aya-global",
    dataset_name="google-research-datasets/mbpp",
    algorithm="grpo",
    backend="trl",
    column_mapping={"text": "prompt", "code": "response"},
    split="train",
    output_dir="/tmp/grpo_smoke_ckpt",
    batch_size=args.per_device_bs,
    num_generations=args.num_generations,
    gradient_accumulation_steps=args.grad_accum,
    loss_type="grpo",
    max_steps=args.steps,
    num_epochs=1,
    learning_rate=1e-5,
    max_prompt_length=256,
    max_completion_length=args.max_completion,
    temperature=0.6,
    top_p=args.top_p,
    beta=0.01,
    use_peft=True,
    lora_r=16,
    lora_alpha=32,
    lora_dropout=0.01,
    lora_target_modules=LORA_TARGETS,
    rewards=[
        {"type": "code_quality", "weight": 1.0, "params": {}},
        {"type": "custom", "weight": 0.0, "params": {"function": true_test_pass}},
    ],
    bf16=True,
    max_seq_length=1024,
    save_strategy="no",
    save_steps=100000,
    logging_steps=1,
    seed=42,
    use_gradient_checkpointing=True,
    gradient_checkpointing=True,
    loggers=["none"],
    report_to="none",
)
if not args.no_vllm:
    kw.update(rollout_backend="vllm", use_vllm=True, vllm_mode="colocate",
              vllm_gpu_memory_utilization=args.vllm_util, vllm_max_model_length=1024)

summary = {"argv": sys.argv, "torch": torch.__version__, "cuda": torch.version.cuda,
           "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}
try:
    import importlib.metadata as md
    summary["versions"] = {p: md.version(p) for p in ["trl", "transformers", "vllm", "peft", "aligntune",
                                                     "curatorkit", "accelerate"]}
except Exception as e:  # pragma: no cover
    summary["versions_error"] = repr(e)

status = "ok"
try:
    t0 = time.time()
    trainer = create_rl_trainer(**kw)
    summary["create_s"] = round(time.time() - t0, 1)
    t1 = time.time()
    res = trainer.train()
    summary["train_call_s"] = round(time.time() - t1, 1)
    summary["result"] = {k: v for k, v in res.items() if k != "metrics"}
    summary["train_metrics"] = res.get("metrics")
    try:
        summary["log_history"] = trainer.trainer.state.log_history
    except Exception:
        pass
except Exception as e:
    import traceback
    status = "error"
    summary["error"] = repr(e)
    summary["traceback"] = traceback.format_exc()[-6000:]
    print(summary["traceback"], file=sys.stderr)
finally:
    _stop.set()
    summary["status"] = status
    summary["nvsmi_peak_mib"] = _peak["mib"]
    if torch.cuda.is_available():
        summary["torch_max_alloc_gib"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
        summary["torch_max_reserved_gib"] = round(torch.cuda.max_memory_reserved() / 2**30, 2)
    summary["script_wall_s"] = round(time.time() - T_START, 1)
    jdump("summary.json", summary, mode="w")
    print("SMOKE_SUMMARY", json.dumps({k: summary.get(k) for k in
                                       ["status", "error", "create_s", "train_call_s", "nvsmi_peak_mib",
                                        "torch_max_alloc_gib", "script_wall_s"]}))
sys.exit(0 if status == "ok" else 1)
