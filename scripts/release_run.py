"""Bounded CPU-only driver; emits structured progress, never raw target logs."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
BASE=Path.home()/"p9/build-release-sol"
TARGETS={"aligntune-release":("at-0129","aligntune"),"safetune-merge":("st-merge","safetune"),"aligntune-legacy":("at","aligntune"),"safetune-legacy":("st","safetune"),"securegrade-011":("tools","securegrade")}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--suite",choices=["gate1","references"],required=True); p.add_argument("--target",choices=list(TARGETS),action="append",required=True); p.add_argument("--budget",type=int,default=1800); a=p.parse_args()
    if sys.platform!="linux" or "microsoft" not in os.uname().release.lower(): raise SystemExit("WSL required")
    logs=BASE/"logs"; logs.mkdir(parents=True,exist_ok=True)
    for target in a.target:
        venv,package=TARGETS[target]
        output=ROOT/"results/release-reaudit-2026-11-08"/(target+"-"+a.suite+".json")
        env=os.environ.copy(); env.update(CUDA_VISIBLE_DEVICES="",OMP_NUM_THREADS="4",OPENBLAS_NUM_THREADS="1",PYTHONPATH=str(ROOT/"harness")+":"+str(ROOT))
        env["PATH"]=str(Path.home()/"p9"/venv/"bin")+os.pathsep+env.get("PATH","")
        env["PYTHONDONTWRITEBYTECODE"]="1"
        if target=="securegrade-011":
            guard_code="import sys,json;sys.path.insert(0,"+repr(str(ROOT))+");import securegrade;print(json.dumps({'version':securegrade.__version__,'origin':securegrade.__file__}))"
            guard=json.loads(subprocess.check_output([str(Path.home()/"p9"/venv/"bin/python"),"-c",guard_code],env=env,text=True,timeout=30))
            if guard["version"]!="0.1.1":
                raise SystemExit("securegrade-011 requires source version 0.1.1; refusing before touching baseline artifacts")
        runtime={"target":target,"suite":a.suite,"interpreter":str(Path.home()/"p9"/venv/"bin/python"),"python_on_PATH":shutil.which("python",path=env["PATH"]),"path_method":"prepend selected venv/bin (equivalent interpreter selection to venv activation)","dependency_bytecode_writes_disabled":True}
        if target.endswith("legacy") and output.exists():
            runtime["superseded_artifact_sha256"]=hashlib.sha256(output.read_bytes()).hexdigest()
            runtime["superseded_reason"]="first diagnostic invocation omitted venv/bin from PATH; literal python subprocesses could not run, invalidating legacy comparisons"
        output.with_name(target+"-"+a.suite+"-runtime.json").write_text(json.dumps(runtime,indent=2))
        cmd=[str(Path.home()/"p9"/venv/"bin/python"),"-m","rewardcheck","--package",package,"--suite",a.suite,"--out",str(output),"--time-budget",str(a.budget)]
        start=time.monotonic()
        with (logs/(target+"-"+a.suite+".stdout.log")).open("w") as stdout,(logs/(target+"-"+a.suite+".stderr.log")).open("w") as stderr:
            proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
            print(json.dumps({"target":target,"suite":a.suite,"status":"started","pid":proc.pid,"outer_timeout_s":a.budget+60}),flush=True)
            last=0
            while proc.poll() is None:
                elapsed=time.monotonic()-start
                if elapsed>a.budget+60:
                    os.killpg(proc.pid,signal.SIGKILL); proc.wait(); raise SystemExit("outer invocation timeout")
                if elapsed-last>=30:
                    if output.exists():
                        try:
                            checkpoint=json.loads(output.read_text())
                            print(json.dumps({"target":target,"suite":a.suite,"cells_complete":len(checkpoint.get("rows",[])),"expected_cells":checkpoint.get("expected_cells"),"elapsed_s":round(elapsed,1)}),flush=True)
                        except json.JSONDecodeError: pass
                    last=elapsed
                time.sleep(.5)
        print(json.dumps({"target":target,"suite":a.suite,"exitcode":proc.returncode,"elapsed_s":round(time.monotonic()-start,1)}),flush=True)
        if proc.returncode: raise SystemExit(proc.returncode)

if __name__=="__main__": main()
