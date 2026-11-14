"""Run from repository root: PYTHONPATH=harness python -m rewardcheck ..."""
import argparse
import hashlib
import importlib
import importlib.metadata as md
import json
import os
import logging
from pathlib import Path
import platform
import sys
import time

from .core import check_cell, check_sequence, require_linux

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/"scripts"))

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def fingerprint(package):
    files=list((ROOT/"harness/rewardcheck").glob("*.py"))
    if package=="securegrade":
        module=importlib.import_module("securegrade"); version=module.__version__
    else:
        module=importlib.import_module(package); version=md.version(package)
    source=Path(module.__file__).parent
    return {"package":package,"distribution_version":version,"import_origin":str(module.__file__),
            "source_hashes":{str(p.relative_to(source)):digest(p) for p in sorted(source.rglob("*.py"))},
            "fixture_hashes":{str(p.relative_to(ROOT)):digest(p) for p in [ROOT/"exploits/exploits.json",ROOT/"exploits/tasks.json",ROOT/"exploits/tasks_all.json"]},
            "harness_hashes":{p.name:digest(p) for p in files},"python":sys.version,"kernel":platform.release(),
            "runtime_controls":{"nice":os.getpriority(os.PRIO_PROCESS,0),"cuda_visible_devices":os.environ.get("CUDA_VISIBLE_DEVICES"),"omp_num_threads":os.environ.get("OMP_NUM_THREADS"),"openblas_num_threads":os.environ.get("OPENBLAS_NUM_THREADS"),"parallel_cells":1,"per_cell_timeout_s":30},
            "memory_read_slot":{"status":"withheld","public_payload":None}}

def columns(package,reward,task,mode):
    if mode=="missing_tests": return {}
    tests=[] if mode=="empty_tests" else task["dict_tests"] if "[dicts]" in reward or reward=="code_correctness" and package=="aligntune" else task["assert_tests"]
    if package=="securegrade": return {"test_list":[tests],"entry_point":[task["entry_point"]],"test_imports":[[task.get("setup_code","")]]}
    if reward=="code_verifiable": return {"reference":[tests]}
    if reward=="counterfact_grpo_code": return {"test_cases":[tests],"entry_point":[task["entry_point"]],"setup_code":[task["setup_code"]]}
    return {"test_list" if package=="safetune" and reward=="mbpp_reward" else "test_cases":[tests]}

def target(package,reward):
    if package=="securegrade": return "rewardcheck.targets:securegrade_factory",{}
    if reward=="counterfact_grpo_code": return "rewardcheck.targets:counterfact_factory",{}
    return "rewardcheck.targets:registry_factory",{"package":package,"reward":reward}

def reference_jobs(package,tasks):
    from m1_fn_rate import asserts_of,dict_tests
    rewards=["code_execution","mbpp_reward","code_verifiable","code_correctness[asserts]","code_correctness[dicts]"] if package=="aligntune" else ["code_execution","mbpp_reward","code_correctness"] if package=="safetune" else ["secure_code_reward"]
    jobs=[]
    for t in tasks:
        tests=asserts_of(t); dt=dict_tests(tests)
        for reward in rewards:
            if reward.endswith("[dicts]") and not dt: continue
            modes=["lifted"]+(["native"] if t["kind"]=="humaneval" and not reward.endswith("[dicts]") else [])
            if package=="securegrade": modes=["native"]
            for mode in modes:
                if mode=="native" and t["kind"]=="humaneval":
                    col={"test":[t["tests"]],"entry_point":[t["entry_point"]],"prompts" if package=="securegrade" else "prompt":[t["prompt"]]}
                else:
                    key="reference" if reward=="code_verifiable" else "test_list" if package in ("securegrade","safetune") and reward in ("secure_code_reward","mbpp_reward") else "test_cases"
                    col={key:[dt if reward.endswith("[dicts]") else tests],"test_imports":[[t["setup"]] if t["setup"] else []]}
                for fenced in (True,False):
                    text="```python\n"+t["reference"]+"\n```" if fenced else t["reference"]
                    meta={"task":t["task_id"],"kind":t["kind"],"reward":reward,"mode":mode,"fenced":fenced}
                    jobs.append((meta,text,col,True))
    return jobs

def main():
    require_linux(); logging.disable(logging.CRITICAL)
    ap=argparse.ArgumentParser(); ap.add_argument("--package",choices=["aligntune","safetune","securegrade"],required=True); ap.add_argument("--out",required=True); ap.add_argument("--suite",choices=["gate1","references"],default="gate1"); ap.add_argument("--limit",type=int); ap.add_argument("--time-budget",type=float,default=1800); a=ap.parse_args()
    start=time.monotonic()
    from gate1_run import TASKS,EXPLOITS,render,AT_SPECS,ST_SPECS
    out={"schema_version":1,"complete":False,"provenance":fingerprint(a.package),"suite":a.suite,"rows":[],"cross_completion":[]}
    out["provenance"]["runtime_controls"].update(overall_budget_s=a.time_budget,checkpoint_every_cells=25)
    if a.package!="securegrade": importlib.import_module(a.package+".rewards.registry")
    if a.package=="aligntune": importlib.import_module("aligntune.backends.trl.rl.counterfact_grpo.counterfact_grpo")
    scratch=Path.home()/"p9/build-release-sol/scratch"/a.package
    jobs=[]
    if a.suite=="gate1":
        rewards=list(AT_SPECS if a.package=="aligntune" else ST_SPECS) if a.package!="securegrade" else ["secure_code_reward"]
        tasks=TASKS[:a.limit] if a.limit else TASKS
        for reward in rewards:
            semantic=reward not in ("code_syntax","code_completeness","code_quality")
            for mode in (("tests","missing_tests","empty_tests") if semantic else ("tests",)):
                for task in tasks:
                    for ex in EXPLOITS:
                        for fenced in (True,False):
                            meta={"reward":reward,"mode":mode,"task":task["task_id"],"completion":ex["id"],"fenced":fenced,"solves_nothing":ex.get("solves_nothing",False),"score_scope":"functional" if semantic else "heuristic"}
                            jobs.append((meta,render(ex["id"],task,fenced),columns(a.package,reward,task,mode),semantic))
    else:
        tasks=json.loads((ROOT/"exploits/tasks_all.json").read_text()); tasks=tasks[:a.limit] if a.limit else tasks
        jobs=reference_jobs(a.package,tasks)
    out["expected_cells"]=len(jobs); out["expected_tasks"]=[t["task_id"] for t in tasks]; out["expected_sequences"]=3 if a.suite=="gate1" else 0
    def checkpoint():
        out["elapsed_s"]=round(time.monotonic()-start,2)
        path=Path(a.out); path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix(path.suffix+".tmp"); temp.write_text(json.dumps(out,indent=1)); temp.replace(path)
    def budget():
        if time.monotonic()-start>a.time_budget:
            out["stop_reason"]="overall_time_budget"; checkpoint(); raise SystemExit(2)
    checkpoint()
    for meta,text,col,semantic in jobs:
        budget(); factory,kw=target(a.package,meta["reward"])
        res=check_cell(factory,text,col,factory_kwargs=kw,scratch=scratch,require_tests=semantic,observe_unconfigured=a.suite=="gate1")
        out["rows"].append(dict(meta,**res))
        if len(out["rows"])%25==0: checkpoint()
        if len(out["rows"])%100==0: print(json.dumps({"cells_complete":len(out["rows"]),"seconds":round(time.monotonic()-start,1)}),flush=True)
    if a.suite=="gate1":
        task=next(t for t in TASKS if t["task_id"]=="HumanEval/2")
        rw="secure_code_reward" if a.package=="securegrade" else "code_correctness"
        factory,kw=target(a.package,rw); col=columns(a.package,rw,task,"tests")
        A=render("patch_isclose_A",task,False); B=render("wrong_float_B",task,False)
        for name,batches in [("B_baseline",[([B],col)]),("A_then_B",[([A],col),([B],col)]),("B_fresh",[([B],col)])]:
            budget(); out["cross_completion"].append({"sequence":name,**check_sequence(factory,batches,factory_kwargs=kw,scratch=scratch)}); checkpoint()
    out["complete"]=True; checkpoint()
    print(json.dumps({"complete":True,"cells":len(out["rows"]),"seconds":out["elapsed_s"]}),flush=True)

if __name__=="__main__": main()
