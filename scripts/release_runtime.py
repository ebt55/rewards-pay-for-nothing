"""Record a small allowlist of runtime facts, never environment dumps/process commands."""
import json
import os
from pathlib import Path
import platform

def main():
    if platform.system()!="Linux":raise SystemExit("Linux required")
    root=Path(__file__).resolve().parents[1]
    yama=Path("/proc/sys/kernel/yama/ptrace_scope")
    lsm=Path("/sys/kernel/security/lsm")
    out={"kernel":platform.release(),"architecture":platform.machine(),"uid":os.getuid(),"gid":os.getgid(),
         "yama_ptrace_scope":yama.read_text().strip() if yama.exists() else "absent (kernel exposes no Yama ptrace_scope)",
         "lsm":lsm.read_text().strip() if lsm.exists() else "unavailable",
         "nice":os.getpriority(os.PRIO_PROCESS,0),"cuda_visible_devices":os.environ.get("CUDA_VISIBLE_DEVICES"),
         "omp_num_threads":os.environ.get("OMP_NUM_THREADS"),"openblas_num_threads":os.environ.get("OPENBLAS_NUM_THREADS"),
         "candidate_concurrency":"serial fork cells; each target may create its own one candidate child",
         "memory_limit_scope":"gentle CPU runs; primary monitors WSL memory; no new cgroup limit applied"}
    (root/"results/release-reaudit-2026-11-08/runtime.json").write_text(json.dumps(out,indent=2))
    print(json.dumps(out))

if __name__=="__main__":main()
