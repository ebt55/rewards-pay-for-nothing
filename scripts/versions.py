import importlib.metadata as m, json, sys, platform
out = {"python": sys.version.split()[0], "platform": platform.platform()}
for p in ["aligntune", "safetune", "trl", "transformers", "torch", "datasets", "vllm", "curatorkit", "accelerate", "peft"]:
    try:
        out[p] = m.version(p)
    except m.PackageNotFoundError:
        out[p] = None
print(json.dumps(out))
