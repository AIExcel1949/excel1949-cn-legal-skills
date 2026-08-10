from __future__ import annotations
import importlib.util,json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parent.parent
def mod():
    s=importlib.util.spec_from_file_location("review",ROOT/"scripts"/"build_review.py"); assert s and s.loader; m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def sample(): return json.loads((ROOT/"examples"/"review.example.json").read_text(encoding="utf-8"))
def test_safe_example(): assert mod().build(sample())["blockers"]==[]
def test_never_determines_violation(): assert mod().build(sample())["violation_determined"] is False
def test_remediation_not_implemented(): assert mod().build(sample())["remediation_implemented"] is False
def test_unverified_authority_blocks():
    value=sample(); value["authorities"][0]["effect_status"]="unknown"; assert mod().build(value)["blockers"]
def test_failed_test_requires_source():
    value=sample(); value["control_tests"][0]["source_spans"]=[]; assert "tested_without_source:TEST-001" in mod().build(value)["blockers"]
def test_not_tested_is_not_failure():
    value=sample(); value["control_tests"][0]["result"]="not_tested"; value["control_tests"][0]["source_spans"]=[]; assert not any("tested_without_source" in x for x in mod().build(value)["blockers"])
def test_dangling_finding_blocks():
    value=sample(); value["findings"][0]["test_ids"]=["TEST-MISSING"]; assert mod().build(value)["blockers"]
def test_external_action_blocks():
    value=sample(); value["external_action_requested"]=True; assert "external_action_forbidden" in mod().build(value)["blockers"]
def test_refuses_overwrite(tmp_path:Path):
    path=tmp_path/"out"; path.mkdir()
    with pytest.raises(FileExistsError): mod().write_dir(path,mod().build(sample()))
