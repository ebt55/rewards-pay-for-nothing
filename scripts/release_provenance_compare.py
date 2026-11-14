"""Inspect external upstream archives without copying upstream source into this repo."""
import hashlib
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"results/release-reaudit-2026-11-08"
BASE=Path.home()/"p9/build-release-sol/downloads"
PINS={"aligntune":"ff59f10f06b74b7529338d06cf513e48e0cb020a","safetune":"36b2142c96e64aea3059966921b2815cf445629b"}

def main():
    local_ex=json.loads((ROOT/"exploits/exploits.json").read_text())
    local_tasks=json.loads((ROOT/"exploits/tasks.json").read_text())
    out={}
    for package,commit in PINS.items():
        with tarfile.open(BASE/(package+"-"+commit+".tar.gz")) as tf:
            members={m.name.split("/",1)[1]:m for m in tf.getmembers() if m.isfile() and "/" in m.name}
            fixture="tests/fixtures/code_rewards/exploits.json"
            test="tests/test_code_reward_security.py"
            data={"commit":commit,"fixture_present":fixture in members,"security_test_present":test in members}
            if fixture in members:
                raw=tf.extractfile(members[fixture]).read(); upstream=json.loads(raw)
                data.update(exploit_fixture_sha256=hashlib.sha256(raw).hexdigest(),exploit_fixture_semantic_equal=upstream==local_ex,
                            exact_template_ids=[e["id"] for e in upstream["exploits"] if "template" in e and e["template"]==next((x.get("template") for x in local_ex["exploits"] if x["id"]==e["id"]),None)],
                            exact_special_ids=[k for k,v in upstream.get("special",{}).items() if local_ex.get("special",{}).get(k)==v])
                taskfile="tests/fixtures/code_rewards/tasks.json"
                if taskfile in members:
                    data["task_fixture_semantic_equal"]=json.loads(tf.extractfile(members[taskfile]).read())==local_tasks
            if test in members:
                raw=tf.extractfile(members[test]).read(); text=raw.decode()
                data["security_test_sha256"]=hashlib.sha256(raw).hexdigest()
                data["explicit_adaptation_note_present"]="Adapted from the regression suite in the private report of 2 Nov 2026 (Ebin Babu Thomas, MIT)." in text
                data["test_names"]=[line.split("(",1)[0][4:] for line in text.splitlines() if line.startswith("def test_")]
            version_members=[p for p in members if p.count("/")==0 and p in ("pyproject.toml","setup.py","setup.cfg")]
            data["archive_version_declarations"]={p:[line.strip() for line in tf.extractfile(members[p]).read().decode().splitlines() if line.strip().startswith(("version", "__version__"))] for p in version_members}
            out[package]=data
    (OUT/"upstream-fixture-comparison.json").write_text(json.dumps(out,indent=2))
    print(json.dumps(out,indent=2))

if __name__=="__main__": main()
