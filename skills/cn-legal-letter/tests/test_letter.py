from __future__ import annotations
import importlib.util,json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parent.parent
def mod():
    s=importlib.util.spec_from_file_location("letter",ROOT/"scripts"/"build_letter.py"); assert s and s.loader; m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def sample(): return json.loads((ROOT/"examples"/"letter.example.json").read_text(encoding="utf-8"))
def test_safe_draft_has_no_blockers(): assert mod().build(sample())["blockers"]==[]
def test_never_sent_or_signed():
    result=mod().build(sample()); assert result["sent"] is False and result["signed"] is False
def test_unverified_authority_blocks():
    value=sample(); value["authorities"][0]["full_text_checked"]=False; assert mod().build(value)["blockers"]
def test_unreviewed_calculation_blocks():
    value=sample(); value["calculations"][0]["lawyer_confirmed"]=False; assert "calculation_not_lawyer_confirmed:CALC-001" in mod().build(value)["blockers"]
def test_missing_fact_provenance_blocks():
    value=sample(); value["facts"][0]["source_spans"]=[]; assert mod().build(value)["blockers"]
def test_prohibited_content_blocks():
    value=sample(); value["prohibited_content_declared"]=["threat"]; assert "prohibited_content_declared" in mod().build(value)["blockers"]
def test_external_action_blocks():
    value=sample(); value["external_action_requested"]=True; assert "external_action_forbidden" in mod().build(value)["blockers"]
def test_refuses_overwrite(tmp_path:Path):
    path=tmp_path/"out"; path.mkdir()
    with pytest.raises(FileExistsError): mod().write_dir(path,mod().build(sample()))
