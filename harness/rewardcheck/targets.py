"""Repository targets exposed through the one TRL callable contract."""
import importlib

def registry_factory(package, reward):
    registry = importlib.import_module(package+".rewards.registry").RewardRegistry
    base = reward.split("[")[0]
    obj = registry.get_reward_function(base,{"type":base,"weight":1.0,"params":{}})
    def reward_fn(completions, **columns):
        values=[]
        for i,text in enumerate(completions):
            kw={k:v[i] for k,v in columns.items()}
            reference=kw.pop("reference",None)
            values.append(float(obj.compute(text,reference,**kw)))
        return values
    return reward_fn

def securegrade_factory():
    from securegrade.trl_reward import make_secure_code_reward
    return make_secure_code_reward(max_workers=1)

def counterfact_factory():
    from types import SimpleNamespace
    from aligntune.backends.trl.rl.counterfact_grpo.counterfact_grpo import TRLCounterFactGRPOTrainer
    def reward_fn(completions, **columns):
        tests=columns.get("test_cases",[])
        prompts=["rewardcheck-"+str(i) for i in range(len(completions))]
        fake=SimpleNamespace(prompt_to_data={p:{"tests":tests[i],"setup":columns.get("setup_code",[""]*len(completions))[i],"expected_func":columns.get("entry_point",[None]*len(completions))[i]} for i,p in enumerate(prompts)} if tests else {})
        return [float(v) for v in TRLCounterFactGRPOTrainer._compute_code_rewards(fake,completions,prompts=prompts)]
    return reward_fn
