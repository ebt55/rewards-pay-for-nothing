"""Preserve this project's tested MIT baseline externally before later hardening."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"results/release-reaudit-2026-11-08"
BASE=Path.home()/"p9/build-release-sol/baselines/securegrade-0.1.1"

def main():
    if sys.platform!="linux":raise SystemExit("WSL/Linux required")
    gate=json.loads((DATA/"securegrade-011-gate1.json").read_text())
    refs=json.loads((DATA/"securegrade-011-references.json").read_text())
    if not gate.get("complete") or not refs.get("complete"):raise SystemExit("completed baseline artifacts required")
    if gate["provenance"]["distribution_version"]!="0.1.1" or refs["provenance"]["distribution_version"]!="0.1.1":raise SystemExit("wrong source version")
    expected=refs["provenance"]["source_hashes"]
    if gate["provenance"]["source_hashes"]!=expected:raise SystemExit("baseline runs used different source bytes")
    files=[ROOT/"securegrade"/rel for rel in expected]+[ROOT/"securegrade/LICENSE",ROOT/"securegrade/README.md"]
    hashes={}
    for path in files:
        rel=path.relative_to(ROOT).as_posix(); content=path.read_bytes(); digest=hashlib.sha256(content).hexdigest()
        if path.suffix==".py" and digest!=expected[path.relative_to(ROOT/"securegrade").as_posix()]:raise SystemExit("canonical baseline changed before snapshot")
        dest=BASE/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and dest.read_bytes()!=content:raise SystemExit("refusing to overwrite a different preserved baseline")
        if not dest.exists():dest.write_bytes(content)
        hashes[rel]=digest
    manifest={"version":"0.1.1","license":"MIT; this project's own code only","snapshot_root":str(BASE),"source_hashes":hashes,"baseline_gate1_artifact_sha256":hashlib.sha256((DATA/"securegrade-011-gate1.json").read_bytes()).hexdigest(),"baseline_references_artifact_sha256":hashlib.sha256((DATA/"securegrade-011-references.json").read_bytes()).hexdigest(),"reconstruction":"Copy the securegrade/ package from this snapshot into an isolated copy of the audit repository, retaining its harness and fixture versions. Do not replace or silently relabel the current hardened canonical source."}
    (BASE/"source-hash-manifest.json").write_text(json.dumps(manifest,indent=2))
    (DATA/"securegrade-011-source-snapshot.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps({"version":"0.1.1","snapshot_root":str(BASE),"files":len(files),"python_files":len(expected),"both_completed_runs_match":True}))

if __name__=="__main__":main()
