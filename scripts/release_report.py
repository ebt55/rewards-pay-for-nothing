"""Build release re-audit summaries; reject incomplete or malformed run artifacts."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"results/release-reaudit-2026-11-08"
sys.path.insert(0,str(ROOT/"harness")); sys.path.insert(0,str(ROOT/"scripts"))

def load_complete(path,*,expected_cells=None):
    data=json.loads(path.read_text())
    if data.get("complete") is not True:
        raise ValueError(f"incomplete artifact: {path.name}")
    expected=expected_cells if expected_cells is not None else data.get("expected_cells")
    if expected is None or len(data.get("rows",[]))!=expected or data.get("expected_cells")!=expected:
        raise ValueError(f"cell count mismatch: {path.name}")
    if "expected_tasks" in data:
        if set(data["expected_tasks"])!={r["task"] for r in data["rows"]}:
            raise ValueError(f"task coverage mismatch: {path.name}")
        keys=[tuple(r.get(k) for k in ("reward","mode","task","completion","fenced")) for r in data["rows"]]
        if len(set(keys))!=len(keys): raise ValueError(f"duplicate cells: {path.name}")
        if len(data.get("cross_completion",[]))!=data.get("expected_sequences"):
            raise ValueError(f"sequence count mismatch: {path.name}")
    return data

def validate_runtime(run):
    controls=run["provenance"]["runtime_controls"]
    required={"nice":19,"cuda_visible_devices":"","omp_num_threads":"4","openblas_num_threads":"1","parallel_cells":1,"per_cell_timeout_s":30}
    if any(controls.get(k)!=v for k,v in required.items()):
        raise ValueError("run controls do not match the stated audit runtime")
    for name,digest in run["provenance"]["harness_hashes"].items():
        actual=hashlib.sha256((ROOT/"harness/rewardcheck"/name).read_bytes()).hexdigest()
        if actual!=digest:raise ValueError("run harness differs from final reviewed harness")
    for name,digest in run["provenance"]["fixture_hashes"].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError("run fixture differs from the reported fixture version")

def score(row):
    if row["status"]=="scored": return row["score"]
    native=row.get("native_observation",{})
    if native.get("status")=="ok": return native["scores"][0][0]
    return None

def gate_summary(run):
    groups={}
    for r in run["rows"]:
        key="|".join([r["reward"],r["mode"],r["completion"]])
        g=groups.setdefault(key,{"n":0,"scores":[],"outcomes":Counter(),"solves_nothing":r["solves_nothing"],"score_scope":r["score_scope"]})
        g["n"]+=1; g["outcomes"][r["status"]]+=1
        s=score(r)
        if s is not None:g["scores"].append(s)
    for g in groups.values():
        values=g.pop("scores"); g.update(max_score=max(values) if values else None,positive=sum(s>0 for s in values),at_least_095=sum(s>=.95 for s in values),full=sum(s>=.999 for s in values),scored=len(values)); g["outcomes"]=dict(g["outcomes"])
    return groups

def reference_summary(run):
    groups={}
    for r in run["rows"]:
        key="|".join([r["reward"],r["kind"],r["mode"],"fenced" if r["fenced"] else "bare"])
        g=groups.setdefault(key,{"n":0,"full":0,"at_least_095":0,"outcomes":Counter(),"below_095":[]})
        g["n"]+=1; g["outcomes"][r["status"]]+=1
        s=score(r); g["full"]+=s is not None and s>=.999; g["at_least_095"]+=s is not None and s>=.95
        if s is None or s<.95: g["below_095"].append({"task":r["task"],"score":s,"status":r["status"]})
    for key,g in groups.items():
        g["outcomes"]=dict(g["outcomes"])
        g["compatibility_assessed"]=not(run["provenance"]["package"]=="safetune" and key.split("|")[2]=="native")
        if not g["compatibility_assessed"]:
            g["raw_native_observation"]={k:g[k] for k in ("full","at_least_095","outcomes","below_095")}
            g.update(full=None,at_least_095=None,below_095=[],outcomes={"configuration_error":g["n"]},functional_compatibility=False,test_configuration="unsupported-native-columns",configuration_reason="SafeTune exact merge does not consume native test/entry_point/prompt columns; execution-only or no-tests fallback")
    return groups

def compare_legacy(run,package):
    historical=json.loads((ROOT/"results/gate1-2026-11-01.json").read_text())
    cells={(r["reward"],r["mode"],r["task"],r["exploit"],r["fenced"]):r for r in historical["cells"] if r["pkg"]==package}
    compared=0; mismatches=[]
    for row in run["rows"]:
        mode="no_tests" if row["mode"]=="missing_tests" else row["mode"]
        key=(row["reward"],mode,row["task"],row["completion"],row["fenced"])
        if key not in cells:continue
        old=cells[key]; now=score(row); compared+=1
        if old["status"]=="ok":
            same=now is not None and abs(now-old["score"])<1e-7
        else:
            current=row.get("native_observation",row)
            same=(old["status"]=="raised" and current["status"]=="exception") or (old["status"]=="timeout" and current["status"]=="deadline") or (old["status"]=="child_died" and current["status"]=="child_exit")
        if not same:mismatches.append({"reward":key[0],"mode":mode,"task":key[2],"completion":key[3],"fenced":key[4],"historical_status":old["status"],"historical_score":old.get("score"),"current_status":row["status"],"current_score":now})
    return {"compared":compared,"mismatches":mismatches}

def markdown(out):
    lines=["# Exact-source release re-audit — 8 November 2026","",
           "Verified observations on the source bytes, fixtures and WSL runtime below. The 3 November PR-head reports remain historical. This re-audit does not test a PyPI AlignTune 0.1.29 wheel.","",
           "## Source and runtime provenance","",
           "| Target | Exact source | Observed distribution metadata | Installed Python files matching source |","|---|---|---|---:|"]
    for package,s in out["sources"].items():
        lines.append(f"| {package} | `{s['commit']}` | {s['version']} | {s['source_match']['matched_python_files']} |")
    lines += ["", "AlignTune 0.1.29 was unavailable from PyPI (HTTP 404), so the authorized exact-tag source archive was installed. `wheel_sha256` is null because no PyPI wheel was tested. SafeTune was installed from the authorized exact merge archive. Both active imports resolve under their new venvs, and every installed target Python file matches that archive byte for byte.","",
              "| Source archive | SHA-256 |","|---|---|"]
    for package,s in out["sources"].items():lines.append(f"| {package} | `{s['source_archive_sha256']}` |")
    lines += ["", "The new venvs reuse existing dependency installations without installing/removing baseline packages; exact target packages live in the new venvs. Full versions and dependency requirement/resolution edges are in the provenance JSONs. AlignTune retains the historical baseline's missing `PyICU>=2.10` dependency override; the reward paths exercised here run without it. SafeTune has no unmet active dependency requirements in this environment. These are reward-path checks, not a clean-room full-package installation certification.","",
              "Runtime: WSL2 Ubuntu, kernel `"+out["runtime"]["kernel"]+"`, x86-64, uid/gid 1000, no exposed Yama `ptrace_scope`. CPU only (`CUDA_VISIBLE_DEVICES=''`), nice 19, OMP 4, OpenBLAS 1. Cells run serially, each in a new process group with a fresh reward object and 30-second deadline. Harness invocations have a 1,800-second budget plus a 60-second outer allowance, with checkpoint/liveness updates. This is process containment for the supplied fixtures, not a general hostile-code sandbox guarantee.","",
              "Every run records actual package import origin, Python/kernel, runtime controls, and package/harness/fixture SHA-256 hashes. `runtime.json` and per-invocation runtime files add the selected interpreter facts. Fixture files are the existing `exploits/exploits.json`, `tasks.json` and cached `tasks_all.json`; no new dataset was downloaded.","",
              "## Existing exploit fixtures and no-tests behavior","",
              "Five tasks × nine existing completion classes × fenced/bare formats. The functional nonanswer subset contains seven `solves_nothing` classes. Heuristic reward rows are labelled separately and make no correctness claim.","",
              "| Exact source | Functional nonanswer cells with tests | Positive scores |","|---|---:|---:|"]
    for target in ("aligntune-release","safetune-merge","securegrade-011"):
        groups=[v for k,v in out["gate1"][target]["summary"].items() if k.split("|")[1]=="tests" and v["solves_nothing"] and v["score_scope"]=="functional"]
        lines.append(f"| {target} | {sum(g['n'] for g in groups)} | {sum(g['positive'] for g in groups)} |")
    lines += ["", "Missing and empty tests are `configuration_error` in rewardcheck, independently of the package's native payment. Native observations are retained for auditing: AlignTune `code_execution` / `code_verifiable` and SafeTune `code_execution` can still pay a stub without tests. A score without supplied tests is not evidence of task correctness. This release limitation is also documented by the upstream AlignTune regression test.","",
              "Cross-completion checks compare wrong completion B alone, A then B on one shared object, and B on a fresh isolated object. The release/merge checks leave B at zero; the legacy AlignTune check exposes the recorded state carry-over. Exact sequence scores are in the JSON.","",
              "Bare-import compatibility is path-specific: all five references in both formats pass the registered AlignTune functional rewards at >=0.95. The counterfactual-GRPO backend still rejects bare `HumanEval/2` (-0.1): 5/5 fenced and 4/5 bare canaries reach >=0.95, matching the historical PR-head pattern. SafeTune `code_execution[dicts]` accepts 8/10 canary format cells; its positional/list input contract is separate from assert-test compatibility.","",
              "## Supplied memory-read class (payload withheld)","",
              "The same existing private probe was executed only in bounded WSL children. Public artifacts retain class-level scores and hashes, not payload text or candidate output. The harness's public memory-read slot remains empty. These private checks use assert-test inputs: `test_cases` for execution/correctness/AlignTune MBPP and `reference` for AlignTune verifiable. HumanEval here uses the five-task fixture's lifted assertions; native HumanEval memory-read behavior is not separately established.","",
              "| Tested source | Reward/task cells | Positive scores | >=0.95 |","|---|---:|---:|---:|"]
    for filename,d in out["memory_class"].items():
        rows=[r for r in d["rows"] if r["claim_class"]=="memory_read"]
        lines.append(f"| {filename.removesuffix('.json')} | {len(rows)} | {sum(r.get('score',0)>0 for r in rows)} | {sum(r.get('score',0)>=.95 for r in rows)} |")
    lines += ["", "AlignTune's exact release source prevents payment for this supplied class on these five tasks, while the same probe obtains high scores on audited premerge head `61d89e4d8ce0be942c7aaea1153c0abf7da31db3`; the paired correct references remain accepted. This supersedes a claim that the PR-head memory result necessarily applies to the release. It does not establish universal memory isolation or identify an explicit denial mechanism: paired syscall/canary controls belong to the separate securegrade hardening work. One further result is withheld pending private disclosure.","",
              "## Correct-reference compatibility","",
              "All 591 supplied tasks are covered: 427 MBPP-sanitized and 164 HumanEval, in fenced and bare full-reference formats. Registered rewards follow the existing PR reference-check integration. HumanEval native columns include the trusted raw prompt; lifted assertions are reported separately because loops/helpers can lose context. The raw run mode `lifted` denotes assert-list input: MBPP uses its original assert list, while HumanEval assertions are lifted. `code_correctness[dicts]` covers only tasks expressible in the historical input/expected-output format. The backend above has five-task canary evidence, not a 591-task claim.","",
              "SafeTune's exact merge consumes `test_cases`/`test_list`, not native HumanEval `test` + `entry_point` + `prompt` columns. Its native-row scores are therefore retained only as unconfigured raw observations, excluded from functional compatibility counts and marked configuration errors. In particular, an execution-only reward can pay both a correct reference and a stub. One-task reference/stub controls confirm the wiring for both exact targets; see the native-control artifacts. SafeTune's assessed HumanEval compatibility here uses lifted assert inputs, with their stated limitations.","",
              "Full score means >=0.999. >=0.95 is a separate historical compatibility marker; for example an MBPP score of 0.98 satisfies the latter, not the former. These are finite supplied-reference results, not a universal false-negative rate.","",
              "| Target / reward / population / path / format | n | >=0.999 | >=0.95 |","|---|---:|---:|---:|"]
    for target,d in out["references"].items():
        for key,g in sorted(d["summary"].items()):
            full=g["full"] if g["compatibility_assessed"] else "not assessed"
            ge095=g["at_least_095"] if g["compatibility_assessed"] else "unsupported columns"
            lines.append(f"| {target} / {key.replace('|',' / ')} | {g['n']} | {full} | {ge095} |")
    lines += ["", "Below-threshold task IDs, scores and containment outcomes are listed in the JSON; a low score on a supplied reference is a compatibility observation, not a claim that the reference is wrong.","",
              "## Historical reproduction and upstream fixture provenance","",
              "| Legacy target | Cells comparable with historical Gate 1 | Mismatches |","|---|---:|---:|"]
    for target,d in out["legacy_reproduction"].items():lines.append(f"| {target} | {d['compared']} | {len(d['mismatches'])} |")
    lines += ["", "The first legacy diagnostic invocation omitted venv/bin from PATH, so legacy code that launches literal `python` could not execute its subprocess. Those files were superseded by reruns with venv/bin prepended; their hashes and the setup correction are retained in the final legacy runtime manifests. Only corrected reruns enter this report and Figure 1.","",
              "The AlignTune release's `tests/fixtures/code_rewards/exploits.json` is semantically identical to this project's fixture (nine entries, eight templates, seven special sequences); its task fixture is also semantically identical. Its security test module explicitly states that it was adapted from the author's private 2 November report and names the author/MIT. The tests exercise the same nonanswer, exit, spoofed-output and cross-completion classes, then add integration/confinement and other regression checks. This directly establishes matching fixture content and an explicit adaptation statement; it does not justify speculation about further provenance or intent. The exact SafeTune merge archive contains neither of those corresponding fixture/security-test files. No SafeTune source was copied into this MIT project.","",
              "Upstream source: [AlignTune fixture](https://github.com/Lexsi-Labs/aligntune/blob/ff59f10f06b74b7529338d06cf513e48e0cb020a/tests/fixtures/code_rewards/exploits.json), [AlignTune security tests](https://github.com/Lexsi-Labs/aligntune/blob/ff59f10f06b74b7529338d06cf513e48e0cb020a/tests/test_code_reward_security.py), [SafeTune exact merge](https://github.com/Lexsi-Labs/SafeTune/tree/36b2142c96e64aea3059966921b2815cf445629b). Content comparison hashes and test names are in `upstream-fixture-comparison.json`.","",
              "## Reproduction and limits","",
              # Note: scripts/release_residual.py is not included in the public repo (it holds a withheld probe).
              # The sentence below is kept as written so this script regenerates the published report unchanged.
              "See `harness/README.md` for the five-minute quick start. `scripts/release_prepare.py` prepares provenance; `scripts/release_run.py` runs bounded Gate 1/reference checks; `scripts/release_report.py` rejects incomplete/incorrect-count artifacts before summarizing. `scripts/figures/fig1_audit_heatmap.py` reads the exact-source matrices for the after side. Private residual checks use existing local probes in `scripts/release_residual.py`; no payload is added to the public harness.","",
              "The exact tested securegrade 0.1.1 MIT source is preserved externally at `~/p9/build-release-sol/baselines/securegrade-0.1.1/securegrade/`, with a source-hash manifest matched to both completed baseline runs. The manifest is also recorded in `securegrade-011-source-snapshot.json`. The driver refuses a non-0.1.1 canonical source before writing artifacts under the `securegrade-011` label. Later hardening must retain these immutable baseline observations; reconstruction uses the snapshot in an isolated copy of the audit repository.","",
              "No GPU, cloud job, paid compute, publication, upload, maintainer contact, commit or push occurred. Existing historical reports and article prose are outside this report's edits. Docker, Yama-enabled kernels, root deployments and arbitrary candidate programs remain unverified here. The dependency reuse, source fallback and finite fixture denominators limit the claims.",""]
    return "\n".join(lines)

def main():
    from rewardcheck.__main__ import reference_jobs
    tasks=json.loads((ROOT/"exploits/tasks_all.json").read_text())
    expected_gate={"aligntune-release":2160,"safetune-merge":1350,"aligntune-legacy":2160,"safetune-legacy":1350,"securegrade-011":270}
    out={"schema_version":1,"date":"2026-11-08","evidence_label":"verified observations on the specified source/runtime/fixtures","runtime":json.loads((DATA/"runtime.json").read_text()),"sources":{},"gate1":{},"references":{},"native_test_wiring":{},"memory_class":{},"legacy_reproduction":{},"artifacts":{}}
    for package in ("aligntune","safetune"):
        out["sources"][package]=json.loads((DATA/(package+"-provenance.json")).read_text())
        proof=out["sources"][package]["source_match"]
        if not proof.get("accepted") or not proof.get("matched_python_files"):raise ValueError("exact source/origin proof required")
    for target,count in expected_gate.items():
        path=DATA/(target+"-gate1.json"); run=load_complete(path,expected_cells=count)
        validate_runtime(run)
        out["gate1"][target]={"provenance":run["provenance"],"cells":count,"summary":gate_summary(run),"cross_completion":run["cross_completion"]}
        if target.endswith("legacy"):out["legacy_reproduction"][target]=compare_legacy(run,run["provenance"]["package"])
    for target,package in (("aligntune-release","aligntune"),("safetune-merge","safetune"),("securegrade-011","securegrade")):
        path=DATA/(target+"-references.json"); run=load_complete(path,expected_cells=len(reference_jobs(package,tasks)))
        validate_runtime(run)
        if len(run["expected_tasks"])!=591:raise ValueError("591 task reference coverage required")
        out["references"][target]={"provenance":run["provenance"],"cells":len(run["rows"]),"summary":reference_summary(run)}
    for filename,expected in (("aligntune-residual.json",100),("aligntune-premerge-control.json",40)):
        run=load_complete(DATA/filename,expected_cells=expected)
        out["memory_class"][filename]={k:v for k,v in run.items() if k!="rows"}
        out["memory_class"][filename]["rows"]=[r for r in run["rows"] if r["claim_class"] in ("memory_read","reference")]
        if filename=="aligntune-premerge-control.json":
            clean=subprocess.run(["git","-C",str(Path.home()/"scratch/aligntune-pr40"),"diff","--quiet","HEAD","--","src/aligntune"],timeout=10).returncode==0
            if not clean:raise ValueError("premerge tracked source changed; revalidate positive control")
            out["memory_class"][filename]["tracked_source_matches_recorded_commit"]=True
    for package,expected in (("aligntune",16),("safetune",12)):
        run=load_complete(DATA/(package+"-native-controls.json"),expected_cells=expected)
        validate_runtime(run)
        for row in run["rows"]:
            if package=="aligntune" or row["mode"]=="asserts":
                if row["status"]!="scored" or (row["completion"]=="reference" and row["score"]<.95) or (row["completion"]=="stub" and row["score"]>0):
                    raise ValueError("reference/stub test-wiring control failed; review before interpreting compatibility")
        out["native_test_wiring"][package]=run
    out["upstream_fixture_comparison"]=json.loads((DATA/"upstream-fixture-comparison.json").read_text())
    out["securegrade_baseline_snapshot"]=json.loads((DATA/"securegrade-011-source-snapshot.json").read_text())
    for path in sorted(DATA.glob("*.json")):
        out["artifacts"][path.name]={"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size}
    (ROOT/"results/release-reaudit-2026-11-08.json").write_text(json.dumps(out,indent=1))
    (ROOT/"results/release-reaudit-2026-11-08.md").write_text(markdown(out))
    print(json.dumps({"complete":True,"gate1_cells":sum(r["cells"] for r in out["gate1"].values()),"reference_cells":sum(r["cells"] for r in out["references"].values()),"legacy_mismatches":{k:len(v["mismatches"]) for k,v in out["legacy_reproduction"].items()}}))

if __name__=="__main__": main()
