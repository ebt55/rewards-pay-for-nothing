import math
import os
from pathlib import Path
import signal
import sys
import time

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))

from rewardcheck.core import check_cell,check_sequence,has_tests,ConfigurationError

pytestmark=pytest.mark.skipif(sys.platform!="linux",reason="candidate execution is Linux/WSL only")
FACTORY="test_rewardcheck:factory"
COL={"test_cases":[["assert f(1)==2"]]}

def factory(mode="scores"):
    def reward_fn(completions,**kwargs):
        if mode=="exit": raise SystemExit(3)
        if mode=="hard_exit": os._exit(4)
        if mode=="deadline":
            signal.signal(signal.SIGALRM,signal.SIG_IGN)
            while True: time.sleep(.05)
        if mode=="malformed": return [float("nan")]
        if mode=="almost": return [.98]*len(completions)
        if mode=="shared":
            scores=[]
            for text in completions:
                if text=="A": math.isclose=lambda *a,**kw:True
                scores.append(float(math.isclose(1,2)))
            return scores
        return [1.0 if text=="reference" else 0.0 for text in completions]
    return reward_fn

def run(tmp_path,text="wrong",**kwargs):
    return check_cell(FACTORY,text,COL,scratch=tmp_path,**kwargs)

@pytest.mark.parametrize("columns",[{}, {"test_cases":[]}, {"test_cases":[[]]}, {"reference":[None]}, {"test":[""]}])
def test_missing_empty_is_configuration_error(columns,tmp_path):
    assert not has_tests(columns)
    result=check_cell("missing:factory","wrong",columns,scratch=tmp_path)
    assert result["status"]=="configuration_error"

def test_wrong_answer_and_reference_have_scores(tmp_path):
    assert run(tmp_path)["score"]==0
    assert run(tmp_path,"reference")["full_score"]

def test_compatibility_threshold_is_separate_from_full_score(tmp_path):
    result=run(tmp_path,factory_kwargs={"mode":"almost"})
    assert result["at_least_095"] is True
    assert result["full_score"] is False

@pytest.mark.parametrize("mode,status",[("exit","exception"),("hard_exit","child_exit"),("deadline","deadline"),("malformed","configuration_error")])
def test_containment(tmp_path,mode,status):
    result=run(tmp_path,factory_kwargs={"mode":mode},timeout=.25 if mode=="deadline" else 3)
    assert result["status"]==status
    assert not list(tmp_path.iterdir()) if mode=="malformed" else True

def test_audit_observes_native_but_remains_configuration_error(tmp_path):
    result=check_cell(FACTORY,"reference",{},scratch=tmp_path,observe_unconfigured=True)
    assert result["status"]=="configuration_error"
    assert result["native_observation"]["scores"]==[[1.0]]

def test_sequence_detects_cross_completion_state_and_fresh_cell(tmp_path):
    args={"factory_kwargs":{"mode":"shared"},"scratch":tmp_path}
    baseline=check_sequence(FACTORY,[(["B"],COL)],**args)
    shared=check_sequence(FACTORY,[(["A"],COL),(["B"],COL)],**args)
    fresh=check_sequence(FACTORY,[(["B"],COL)],**args)
    assert baseline["scores"]==fresh["scores"]==[[0.0]]
    assert shared["scores"][-1]==[1.0]
    assert not math.isclose(1,2)

def test_native_humaneval_includes_trusted_prompt():
    from rewardcheck.__main__ import reference_jobs,ROOT
    import json
    task=next(t for t in json.loads((ROOT/"exploits/tasks_all.json").read_text()) if t["task_id"]=="HumanEval/32")
    for package in ("aligntune","safetune","securegrade"):
        jobs=[j for j in reference_jobs(package,[task]) if j[0]["mode"]=="native"]
        assert jobs
        for _,_,columns,_ in jobs:
            assert columns["prompts" if package=="securegrade" else "prompt"]==[task["prompt"]]

def test_reports_reject_partial_and_wrong_count_artifacts(tmp_path):
    import json
    from release_report import load_complete
    path=tmp_path/"run.json"
    path.write_text(json.dumps({"complete":False,"expected_cells":1,"rows":[{}]}))
    with pytest.raises(ValueError,match="incomplete"): load_complete(path)
    path.write_text(json.dumps({"complete":True,"expected_cells":2,"rows":[{}]}))
    with pytest.raises(ValueError,match="count"): load_complete(path)

def test_report_rejects_uncontrolled_runtime():
    from release_report import validate_runtime
    with pytest.raises(ValueError,match="controls"):
        validate_runtime({"provenance":{"runtime_controls":{"nice":0}}})

def test_unconsumed_native_columns_do_not_become_compatibility_passes():
    from release_report import reference_summary
    run={"provenance":{"package":"safetune"},"rows":[{"reward":"code_execution","kind":"humaneval","mode":"native","fenced":True,"task":"HumanEval/0","status":"scored","score":1.0}]}
    row=reference_summary(run)["code_execution|humaneval|native|fenced"]
    assert row["functional_compatibility"] is False
    assert row["full"] is None
    assert row["raw_native_observation"]["full"]==1
    assert row["outcomes"]=={"configuration_error":1}

def test_driver_refuses_changed_baseline_before_writing(monkeypatch):
    import json
    import release_run
    artifact=release_run.ROOT/"results/release-reaudit-2026-11-08/securegrade-011-gate1.json"
    previous=artifact.read_bytes() if artifact.exists() else None
    monkeypatch.setattr(sys,"argv",["release_run.py","--suite","gate1","--target","securegrade-011"])
    monkeypatch.setattr(release_run.subprocess,"check_output",lambda *a,**kw:json.dumps({"version":"0.1.2"}))
    with pytest.raises(SystemExit,match="requires source version 0.1.1"):
        release_run.main()
    assert (artifact.read_bytes() if artifact.exists() else None)==previous
