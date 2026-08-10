from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = ROOT.parent


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROUTE = load_module(ROOT / "scripts" / "route.py", "cn_legal_route_for_execution_audit")
AUDIT = load_module(
    ROOT / "scripts" / "verify_execution.py",
    "cn_legal_verify_execution_test",
)
PROCEDURE = load_module(
    SKILLS_ROOT / "cn-procedure" / "scripts" / "fill_templates.py",
    "cn_procedure_for_execution_audit",
)


def route_input() -> dict:
    return {
        "schema_version": "1.0",
        "task_id": "TASK-AUTH-TEST-001",
        "jurisdiction": "中国大陆",
        "track": "dispute",
        "track_status": "user_confirmed",
        "requested_outputs": ["民事授权委托书（律师）"],
        "delivery_format": "docx",
        "urgent_flags": ["none"],
    }


def test_orchestrator_accepts_registered_template_output(tmp_path: Path):
    plan = ROUTE.build(route_input(), tmp_path)
    procedure_dir = Path(plan["requested_deliverables"][0]["output_dir"])
    result = PROCEDURE.main(
        [
            "--data",
            str(SKILLS_ROOT / "cn-procedure" / "examples" / "case-data.example.json"),
            "--template",
            "civil-power-attorney",
            "--output",
            str(procedure_dir),
        ]
    )
    assert result == 0
    verify_dir = Path(plan["case_root"]) / "cn-verify"
    docx_path = next(procedure_dir.glob("*.docx"))
    artifact_verify_dir = verify_dir / docx_path.stem
    artifact_verify_dir.mkdir(parents=True)
    report_schema = json.loads(
        (
            SKILLS_ROOT
            / "cn-verify"
            / "schemas"
            / "review-report.schema.json"
        ).read_text(encoding="utf-8")
    )
    report = {
        "schema_version": "1.0",
        "report_id": "REVIEW-TASK-AUTH-TEST-001",
        "matter_id": "TASK-AUTH-TEST-001",
        "artifact_id": "ARTIFACT-AUTH-TEST-001",
        "mode": "training_fixture",
        "request_sha256": "0" * 64,
        "input_sha256": hashlib.sha256(docx_path.read_bytes()).hexdigest(),
        "text_sha256": "0" * 64,
        "generated_at": "2026-07-26T09:00:00+08:00",
        "state": "lawyer_review_required",
        "summary": {"blocker": 0, "warning": 1, "note": 0, "total": 1},
        "checked_categories": ["confirmation"],
        "findings": [
            {
                "finding_id": "FND-0001",
                "severity": "warning",
                "category": "confirmation",
                "code": "CONFIRMATION.LAWYER_REVIEW",
                "message": "仍须由执业律师逐项复核。",
                "location": "",
                "evidence": "",
                "source_refs": [],
                "action": "完成律师复核并保留记录。",
                "human_confirmation_required": True,
            }
        ],
        "limitations": ["机器核验不替代律师审查。"],
        "disclaimers": report_schema["properties"]["disclaimers"]["const"],
    }
    (artifact_verify_dir / "review-report.json").write_text(
        json.dumps(report, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (artifact_verify_dir / "review-report.md").write_text("# 核验报告\n", encoding="utf-8")

    audit = AUDIT.audit(plan)
    assert audit["status"] == "passed"
    assert not audit["errors"]


def test_orchestrator_blocks_generic_docx_for_unimplemented_deliverable(tmp_path: Path):
    value = route_input()
    value["requested_outputs"] = ["民事起诉状"]
    plan = ROUTE.build(value, tmp_path)
    assert plan["blocked"]
    audit = AUDIT.audit(plan)
    assert audit["status"] == "blocked"
    assert "执行计划仍有阻断项，不得验收下游替代产物" in audit["errors"]


def test_plan_hash_detects_changed_child_output_path(tmp_path: Path):
    plan = ROUTE.build(route_input(), tmp_path)
    changed = json.loads(json.dumps(plan, ensure_ascii=False))
    changed["requested_deliverables"][0]["output_dir"] = str(tmp_path / "other")
    assert not AUDIT.validate_plan_hash(changed)


def test_orchestrator_rejects_uncovered_docx(tmp_path: Path):
    plan = ROUTE.build(route_input(), tmp_path)
    procedure_dir = Path(plan["requested_deliverables"][0]["output_dir"])
    assert PROCEDURE.main(
        [
            "--data",
            str(SKILLS_ROOT / "cn-procedure" / "examples" / "case-data.example.json"),
            "--template",
            "civil-power-attorney",
            "--output",
            str(procedure_dir),
        ]
    ) == 0
    (Path(plan["case_root"]) / "cn-verify").mkdir(parents=True)
    audit = AUDIT.audit(plan)
    assert audit["status"] == "blocked"
    assert any("未逐份覆盖 1 份 DOCX" in error for error in audit["errors"])
