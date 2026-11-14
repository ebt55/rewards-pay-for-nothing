"""Show the exact prompt AlignTune's MBPP GRPO recipe hands to TRL for Tiny Aya.

Mirrors examples/grpo_code_gen_trl_mbpp.py: task "grpo", column_mapping
{"text": "prompt", "code": "response"}, no system_prompt, KEEP_COLUMNS=True.
Runs AlignTune's own DataManager on MBPP (sanitized test split and full test
split), then shows what TRL 1.7.1's GRPOTrainer._tokenize_prompts would do with
the resulting `prompt` value, and the chat-templated alternative.
"""
import json
import sys

from transformers import AutoTokenizer
from trl.data_utils import is_conversational
from aligntune.data.manager import DataManager

MODEL = "CohereLabs/tiny-aya-global"
tok = AutoTokenizer.from_pretrained(MODEL)
out = {"model": MODEL}

for cfg in ["sanitized", "full"]:
    dm = DataManager(task_type="grpo", column_mapping={"text": "prompt", "code": "response"},
                     system_prompt=None, tokenizer=tok, max_length=1024)
    dd = dm.load_dataset("google-research-datasets/mbpp", config_name=cfg, split="test")
    ds = dd["test"]
    row = ds[0]
    p = row["prompt"]
    conv = is_conversational({"prompt": p})
    if conv:
        ids = tok.apply_chat_template(p, add_generation_prompt=True, tokenize=True)
        ids = ids["input_ids"] if isinstance(ids, dict) else ids
    else:
        ids = tok(text=[p])["input_ids"][0]
    chat_ids = tok.apply_chat_template([{"role": "user", "content": p if isinstance(p, str) else p[-1]["content"]}],
                                       add_generation_prompt=True, tokenize=True)
    chat_ids = chat_ids["input_ids"] if isinstance(chat_ids, dict) else chat_ids
    out[cfg] = {
        "n_rows": len(ds),
        "columns": ds.column_names,
        "row0_task_id": row.get("task_id"),
        "prompt_type": type(p).__name__,
        "prompt_repr": repr(p)[:600],
        "trl_is_conversational": conv,
        "trl_prompt_tokens": len(ids),
        "trl_prompt_decoded": tok.decode(ids),
        "chat_template_prompt_tokens": len(chat_ids),
        "chat_keys_present": [k for k in ("messages", "chat_template_kwargs") if k in ds.column_names],
    }

out["chat_template_rendered_example"] = tok.apply_chat_template(
    [{"role": "user", "content": "<USER_PROMPT>"}], add_generation_prompt=True, tokenize=False)
out["bos_token"] = tok.bos_token
out["eos_token"] = tok.eos_token
json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
print()
