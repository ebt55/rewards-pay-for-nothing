"""Small test-wiring negative control, with all reward calls in WSL child cells."""
import argparse
import importlib
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"harness"));sys.path.insert(0,str(ROOT/"scripts"));sys.path.insert(0,str(ROOT))
from rewardcheck.core import check_cell,require_linux
from rewardcheck.__main__ import fingerprint,target,columns

def main():
    require_linux();logging.disable(logging.CRITICAL)
    p=argparse.ArgumentParser();p.add_argument("--package",choices=["aligntune","safetune"],required=True);p.add_argument("--out",required=True);a=p.parse_args()
    start=time.monotonic()
    from gate1_run import TASKS,render
    t=next(x for x in TASKS if x["task_id"]=="HumanEval/0")
    importlib.import_module(a.package+".rewards.registry")
    rewards=["code_execution","code_correctness","mbpp_reward"]+(["code_verifiable"] if a.package=="aligntune" else [])
    out={"complete":False,"expected_cells":len(rewards)*4,"provenance":fingerprint(a.package),"rows":[],"overall_budget_s":300,"runner_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    path=Path(a.out)
    for reward in rewards:
        factory,kw=target(a.package,reward)
        for mode in ("native","asserts"):
            col={"test":[t["raw_columns"]["test"]],"entry_point":[t["entry_point"]],"prompt":[t["raw_columns"]["prompt"]]} if mode=="native" else columns(a.package,"code_correctness[asserts]" if reward=="code_correctness" else reward,t,"tests")
            for completion in ("reference","stub"):
                if time.monotonic()-start>300:out["stop_reason"]="overall_time_budget";path.write_text(json.dumps(out,indent=2));raise SystemExit(2)
                result=check_cell(factory,render(completion,t),col,factory_kwargs=kw,scratch=Path.home()/"p9/build-release-sol/scratch/native-controls")
                out["rows"].append(dict(reward=reward,mode=mode,task=t["task_id"],completion=completion,**result))
                path.write_text(json.dumps(out,indent=2))
    out["complete"]=True;out["elapsed_s"]=round(time.monotonic()-start,3);path.write_text(json.dumps(out,indent=2))
    print(json.dumps({"package":a.package,"complete":True,"cells":len(out["rows"]),"rows":out["rows"]}),flush=True)

if __name__=="__main__":main()
