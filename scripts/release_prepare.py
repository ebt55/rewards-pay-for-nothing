"""Exact-package provenance preparation; WSL only, no candidate execution."""
import hashlib
import importlib.metadata as md
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = Path.home() / "p9/build-release-sol"
OUT = ROOT / "results/release-reaudit-2026-11-08"
PINS = {"aligntune": ("at", "at-0129", "0.1.29", "Lexsi-Labs/aligntune", "ff59f10f06b74b7529338d06cf513e48e0cb020a"),
        "safetune": ("st", "st-merge", None, "Lexsi-Labs/SafeTune", "36b2142c96e64aea3059966921b2815cf445629b")}

def download(url, dest):
    if not dest.exists():
        with urllib.request.urlopen(url, timeout=60) as r:
            dest.write_bytes(r.read())
    return hashlib.sha256(dest.read_bytes()).hexdigest()

def inspect_metadata(name):
    from packaging.requirements import Requirement
    chosen = {}
    for d in md.distributions():
        chosen.setdefault(d.metadata["Name"].lower().replace("_","-"), d)
    edges=[]
    for key,d in sorted(chosen.items()):
        for raw in d.requires or []:
            req=Requirement(raw)
            active=req.marker is None or req.marker.evaluate({"extra":""})
            resolved=chosen.get(req.name.lower().replace("_","-"))
            satisfied=bool(resolved and (not req.specifier or resolved.version in req.specifier))
            edges.append({"from":key,"requirement":raw,"active_without_extras":active,"resolved_version":resolved.version if resolved else None,"satisfied":satisfied if active else None})
    origin=importlib.util.find_spec(name).origin
    return {"version":md.version(name),"active_import_origin":origin,"distribution_path":str(md.distribution(name)._path),
            "dependencies":[{"name":d.metadata["Name"],"version":d.version,"path":str(d._path)} for d in chosen.values()],
            "dependency_edges":edges,"unsatisfied_active_requirements":[e for e in edges if e["active_without_extras"] and not e["satisfied"]]}

def main():
    if sys.platform != "linux" or "microsoft" not in os.uname().release.lower():
        raise SystemExit("WSL required")
    for p in (BASE / "downloads", BASE / "logs", BASE / "scratch", OUT):
        p.mkdir(parents=True, exist_ok=True)
    name = sys.argv[1]
    if len(sys.argv)>2 and sys.argv[2]=="--metadata":
        print(json.dumps(inspect_metadata(name))); return
    if len(sys.argv)>2 and sys.argv[2]=="--refresh":
        path=OUT/(name+"-provenance.json"); manifest=json.loads(path.read_text())
        manifest["installation_artifact"]={"kind":"source_archive","sha256":manifest["source_archive_sha256"],"wheel_sha256":None,"reason":"PyPI 0.1.29 unavailable; installed exact source archive" if name=="aligntune" else "installed explicitly authorized exact merge source archive"}
        target=Path(manifest["venv"])
        metadata=json.loads(subprocess.check_output([str(target/"bin/python"),str(Path(__file__)),name,"--metadata"],text=True,timeout=30))
        manifest.update(metadata)
        with tarfile.open(BASE/"downloads"/(name+"-"+manifest["commit"]+".tar.gz")) as tf:
            manifest["archive_project_versions"]={m.name.split("/",1)[1]:[line for line in tf.extractfile(m).read().decode().splitlines() if line.strip().startswith("version")][:5] for m in tf.getmembers() if m.isfile() and m.name.count("/")==1 and m.name.endswith("pyproject.toml")}
        manifest["source_match"]["origin_under_new_venv"]=metadata["active_import_origin"].startswith(str(target)+"/")
        manifest["source_match"]["accepted"]=bool(manifest["source_match"]["matched_python_files"] and not manifest["source_match"]["different"] and not manifest["source_match"]["absent"] and manifest["source_match"]["origin_under_new_venv"])
        path.write_text(json.dumps(manifest,indent=2)); print(json.dumps({"name":name,"version":metadata["version"],"unsatisfied_count":len(metadata["unsatisfied_active_requirements"]),"source_match":manifest["source_match"]})); return
    old, new, version, repo, commit = PINS[name]
    target = Path.home() / "p9" / new
    oldsite = Path.home() / "p9" / old / "lib/python3.12/site-packages"
    venv.EnvBuilder(with_pip=False).create(target)
    site = target / "lib/python3.12/site-packages"
    # New venv owns target package; existing dependencies are reused read-only.
    (site / "baseline-dependencies.pth").write_text(str(oldsite) + "\n")
    archive = BASE / "downloads" / (name + "-" + commit + ".tar.gz")
    archive_hash = download(f"https://api.github.com/repos/{repo}/tarball/{commit}", archive)
    artifact = archive
    state_path=BASE/"logs/install-failures.json"
    failures=json.loads(state_path.read_text()) if state_path.exists() else {}
    if failures.get(name,0)>=2: raise SystemExit("Two installation failures: user input required")
    manifest = {"name": name, "requested_version": version, "commit": commit,
                "repository": f"https://github.com/{repo}", "source_archive_sha256": archive_hash,
                "dependency_method": "new venv, .pth read-only reuse of existing baseline dependencies; exact target installed into new site-packages with --no-deps",
                "baseline_site_packages": str(oldsite), "venv": str(target), "install_failures": failures.get(name,0),
                "baseline_override": "historical AlignTune installation excluded PyICU; baseline is reused as-is" if name=="aligntune" else None}
    if version:
        try:
            with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as r:
                data = json.load(r)
            wheels = [x for x in data["urls"] if x["filename"].endswith(".whl")]
            if wheels:
                wheel = wheels[0]
                artifact = BASE / "downloads" / wheel["filename"]
                digest = download(wheel["url"], artifact)
                if digest != wheel["digests"]["sha256"]:
                    raise RuntimeError("wheel digest mismatch")
                manifest.update(wheel_sha256=digest, wheel_filename=artifact.name)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            manifest["pypi_status"] = "version absent (HTTP 404); authorized tag fallback"
    log = BASE / "logs" / (name + "-install.log")
    command = [str(Path.home()/".local/bin/uv"), "pip", "install", "--python", str(target/"bin/python"), "--no-deps", str(artifact)]
    try:
        with log.open("w") as f:
            run = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, timeout=300)
        failed=bool(run.returncode)
    except subprocess.TimeoutExpired:
        failed=True
    if failed:
        manifest["install_failures"] += 1
        failures[name]=manifest["install_failures"]; state_path.write_text(json.dumps(failures,indent=2))
        (OUT/(name+"-provenance.json")).write_text(json.dumps(manifest, indent=2))
        raise SystemExit("installation failed; see dedicated log")
    package = site / name
    with tarfile.open(archive) as tf:
        source = {m.name: tf.extractfile(m).read() for m in tf.getmembers() if m.isfile() and "/"+name+"/" in m.name and m.name.endswith(".py")}
    matched, different, absent = [], [], []
    for path in sorted(package.rglob("*.py")):
        rel = path.relative_to(site).as_posix()
        candidates = [b for n,b in source.items() if n.endswith("/"+rel)]
        if not candidates:
            absent.append(rel)
        elif path.read_bytes() == candidates[0]:
            matched.append(rel)
        else:
            different.append(rel)
    manifest.update(source_match={"matched_python_files": len(matched), "different": different, "absent": absent},
                    installed_source_sha256={p.relative_to(site).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(package.rglob("*.py"))})
    metadata = json.loads(subprocess.check_output([str(target/"bin/python"),str(Path(__file__)),name,"--metadata"],text=True,timeout=30))
    manifest.update(metadata)
    if not matched or different or absent or not metadata["active_import_origin"].startswith(str(site)+"/"):
        raise SystemExit("source/origin validation failed")
    # SafeTune remains external; only metadata/hashes are placed in the MIT repository.
    with tarfile.open(archive) as tf:
        testfiles = [m for m in tf.getmembers() if m.isfile() and (m.name.endswith("tests/fixtures/code_rewards/exploits.json") or m.name.endswith("test_code_reward_security.py"))]
        manifest["upstream_security_files"] = [{"path":m.name.split("/",1)[1],"sha256":hashlib.sha256(tf.extractfile(m).read()).hexdigest()} for m in testfiles]
        manifest["archive_project_versions"] = {m.name.split("/",1)[1]:[line for line in tf.extractfile(m).read().decode().splitlines() if line.strip().startswith("version")][:5] for m in tf.getmembers() if m.isfile() and m.name.count("/")==1 and m.name.endswith("pyproject.toml")}
    (OUT/(name+"-provenance.json")).write_text(json.dumps(manifest, indent=2))
    print(json.dumps({k:manifest.get(k) for k in ["name","version","commit","wheel_sha256","source_match","install_failures"]}), flush=True)

if __name__ == "__main__":
    main()
