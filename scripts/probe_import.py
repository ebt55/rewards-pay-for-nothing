import time, sys, importlib
t = time.time()
pkg = sys.argv[1]
reg = importlib.import_module(f"{pkg}.rewards.registry")
core = importlib.import_module(f"{pkg}.rewards.core" if pkg == "aligntune" else f"{pkg}.rewards.base")
print("import seconds", round(time.time() - t, 1))
names = reg.RewardRegistry.list_rewards()
print("registry entries:", len(names)); print(names)
print("RewardType members:", len(list(core.RewardType)))
print("modules loaded containing unsloth/vllm:", sorted(m for m in sys.modules if m.split('.')[0] in ("unsloth", "vllm", "unsloth_zoo"))[:5])

