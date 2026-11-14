"""Drive TRL's own GRPOTrainer._calculate_rewards (unbound, on a minimal stand-in trainer, CPU, no
model) with SafeTune code rewards. Our code, MIT.

SafeTune ships no TRL reward bridge, so each reward is wrapped the plain way a user hands a
function to GRPOTrainer(reward_funcs=[...]): f(prompts, completions, **dataset_columns) -> list.
Same stand-in trainer as scripts/systemexit_trl_driver.py.
"""
from types import SimpleNamespace


def wrap(reward, mode, name):
    """mode: 'no_tests' | 'test_cases' | 'test_list' (which dataset column carries the tests)."""
    def f(prompts, completions, completion_ids=None, **kw):
        out = []
        for i, c in enumerate(completions):
            if mode == "no_tests":
                out.append(reward.compute(c))
            elif mode == "test_cases":
                out.append(reward.compute(c, None, test_cases=kw["test_cases"][i]))
            else:
                out.append(reward.compute(c, None, test_list=kw["test_list"][i]))
        return out
    f.__name__ = name
    return f


def calculate_rewards(funcs, rows, completions):
    """funcs: list of wrapped reward functions; rows: one dataset row per completion."""
    from trl import GRPOTrainer
    fake = SimpleNamespace(
        accelerator=SimpleNamespace(device="cpu", is_main_process=True),
        reward_funcs=funcs,
        reward_processing_classes=[None] * len(funcs),
        reward_func_names=[f.__name__ for f in funcs],
        environments=None,
        state=SimpleNamespace(global_step=0),
        args=SimpleNamespace(report_to=[]),
        _log_completion_extra=lambda *a, **k: None,
        _log_metric=lambda *a, **k: None,
        async_loop=None,
    )
    out = GRPOTrainer._calculate_rewards(fake, rows, [r["prompt"] for r in rows], completions, [[0]] * len(rows))
    return out.tolist()
