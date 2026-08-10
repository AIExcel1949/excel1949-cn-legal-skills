from __future__ import annotations
import importlib.util,json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parent.parent
def mod():
    spec=importlib.util.spec_from_file_location("matter",ROOT/"scripts"/"build_snapshot.py"); assert spec and spec.loader; value=importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value
def sample(): return json.loads((ROOT/"examples"/"matter.example.json").read_text(encoding="utf-8"))
def test_intake_to_active_allowed(): assert mod().build(sample())["transition_allowed"]
def test_conflict_pending_blocks_active():
    value=sample(); value["controls"]["conflict_check"]["status"]="pending"; assert "control_pending:conflict_check" in mod().build(value)["blockers"]
def test_unconfirmed_transition_blocks():
    value=sample(); value["transition_confirmed"]=False; assert mod().build(value)["proposed_state"]=="intake"
def test_invalid_transition_blocks():
    value=sample(); value["requested_state"]="closed"; assert "state_transition_not_allowed" in mod().build(value)["blockers"]
def test_close_requires_all_tasks_disposed():
    value=sample(); value["current_state"]="closing"; value["requested_state"]="closed"
    for key in ("final_review","billing_review","archive_checklist","retention_classification"): value["controls"][key]={"status":"confirmed","confirmation_note":"人工确认"}
    assert "pending_tasks_before_close" in mod().build(value)["blockers"]
def test_closed_state_never_deletes_materials():
    value=sample(); value["current_state"]="closing"; value["requested_state"]="closed"; value["tasks"][0]["status"]="completed"
    for key in ("final_review","billing_review","archive_checklist","retention_classification"): value["controls"][key]={"status":"confirmed","confirmation_note":"人工确认"}
    result=mod().build(value); assert result["transition_allowed"] and result["materials_deleted"] is False
def test_refuses_overwrite(tmp_path:Path):
    path=tmp_path/"out"; path.mkdir()
    with pytest.raises(FileExistsError): mod().write_dir(path,mod().build(sample()))
