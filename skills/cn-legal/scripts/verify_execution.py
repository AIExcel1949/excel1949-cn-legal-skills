#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = SKILL_ROOT.parent
REGISTRY_PATH = SKILL_ROOT / "references" / "deliverable-registry.json"
PROCEDURE_MANIFEST_PATH = SKILLS_ROOT / "cn-procedure" / "schemas" / "template-manifest.json"
AUTHOR = "AIOffice职场通关-excel1949"


class ExecutionAuditError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionAuditError(f"无法读取 JSON：{path}：{exc}") from exc
    if not isinstance(value, dict):
        raise ExecutionAuditError(f"JSON 顶层必须是对象：{path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ExecutionAuditError(f"无法加载审计组件：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_plan_hash(plan: dict[str, Any]) -> bool:
    expected = plan.get("plan_sha256")
    payload = dict(plan)
    payload.pop("plan_sha256", None)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return actual == expected


def expected_matches(actual_names: set[str], patterns: list[str]) -> tuple[list[str], list[str]]:
    missing = [
        pattern
        for pattern in patterns
        if not any(fnmatch.fnmatch(name, pattern) for name in actual_names)
    ]
    unexpected = [
        name
        for name in actual_names
        if not any(fnmatch.fnmatch(name, pattern) for pattern in patterns)
    ]
    return missing, unexpected


def audit_procedure(
    output_dir: Path,
    deliverables: list[dict[str, Any]],
    file_records: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    audit_module = load_module(
        SKILLS_ROOT / "cn-procedure" / "scripts" / "audit_templates.py",
        "cn_procedure_audit_from_orchestrator",
    )
    docx_paths = sorted(p for p in output_dir.glob("*.docx") if not p.name.startswith("~$"))
    errors.extend(audit_module.audit_manifest(output_dir, docx_paths))
    manifest_path = output_dir / "generation-manifest.json"
    if manifest_path.is_file():
        manifest = load_json(manifest_path)
        selected = set(manifest.get("templates", []))
        required_templates = {
            item["template_id"] for item in deliverables if item.get("template_id")
        }
        if not required_templates.issubset(selected):
            errors.append(
                "cn-procedure 未使用执行计划指定模板："
                + "、".join(sorted(required_templates - selected))
            )
    for path in docx_paths:
        file_records.append(
            {
                "path": str(path),
                "sha256": sha256(path),
                "source_skill": "cn-procedure",
            }
        )
    return errors


def audit_docx_files(
    output_dir: Path,
    source_skill: str,
    file_records: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    audit_module = load_module(
        SKILLS_ROOT / "cn-legal-core" / "scripts" / "audit_docx.py",
        "cn_legal_core_docx_audit_from_orchestrator",
    )
    for path in sorted(p for p in output_dir.glob("*.docx") if not p.name.startswith("~$")):
        result = audit_module.audit(path, [])
        if not result["ok"]:
            errors.extend(f"{path.name}：{item}" for item in result["errors"])
        if not any(record["path"] == str(path) for record in file_records):
            file_records.append(
                {
                    "path": str(path),
                    "sha256": sha256(path),
                    "source_skill": source_skill,
                }
            )
    return errors


def audit(plan: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    file_records: list[dict[str, str]] = []

    if not validate_plan_hash(plan):
        errors.append("执行计划哈希不匹配，计划可能被修改")
    if sha256(REGISTRY_PATH) != plan.get("deliverable_registry_sha256"):
        errors.append("交付物登记表哈希与执行计划不一致")
    if sha256(PROCEDURE_MANIFEST_PATH) != plan.get("procedure_template_manifest_sha256"):
        errors.append("程序文书模板清单哈希与执行计划不一致")
    if plan.get("blocked"):
        errors.append("执行计划仍有阻断项，不得验收下游替代产物")

    case_root = Path(str(plan.get("case_root", ""))).resolve(strict=False)
    if not case_root.is_absolute():
        errors.append("案件输出根目录不是绝对路径")
    skills_root = SKILLS_ROOT.resolve()
    if case_root == skills_root or is_relative_to(case_root, skills_root):
        errors.append("案件输出根目录位于 Skill 安装目录")

    ready = [
        item
        for item in plan.get("requested_deliverables", [])
        if isinstance(item, dict) and item.get("status") == "ready"
    ]
    by_output: dict[Path, list[dict[str, Any]]] = {}
    for item in ready:
        output_dir = Path(item["output_dir"]).resolve(strict=False)
        if output_dir != case_root and not is_relative_to(output_dir, case_root):
            errors.append(f"交付物输出目录越出案件根目录：{output_dir}")
            continue
        by_output.setdefault(output_dir, []).append(item)

    for output_dir, items in sorted(by_output.items(), key=lambda pair: str(pair[0])):
        if not output_dir.is_dir():
            errors.append(f"缺少下游输出目录：{output_dir}")
            continue
        actual_names = {
            path.name for path in output_dir.iterdir()
            if path.is_file()
            and not path.name.startswith(".")
            and not path.name.startswith("~$")
        }
        patterns = sorted(
            {
                pattern
                for item in items
                for pattern in item.get("expected_artifacts", [])
            }
        )
        # BUG-A/D 修复：docx_supported 交付物必须产出 DOCX 成品（精确名或唯一 *.docx），且计入期望产物
        for item in items:
            if not item.get("docx_supported"):
                continue
            artifact = item.get("docx_artifact") or ""
            if artifact:
                patterns.append(artifact)
            for name in item.get("docx_artifacts") or []:
                patterns.append(name)
            candidates = sorted(p for p in output_dir.glob("*.docx") if not p.name.startswith("~$"))
            if item.get("docx_artifacts") and all(
                (output_dir / name).is_file() for name in item["docx_artifacts"]
            ):
                continue
            if artifact and any(c.name == artifact for c in candidates):
                continue
            if not artifact and len(candidates) == 1:
                continue
            if not artifact and any(
                c.name.startswith((item.get("template_id") or item["deliverable_id"]) + "-") for c in candidates
            ):
                continue
            errors.append(
                f"{item['deliverable_id']} 缺少 DOCX 成品（docx_supported=true；期望 {artifact or '唯一 *.docx 或以交付物 id 开头'}）"
            )
        missing, unexpected = expected_matches(actual_names, patterns)
        if missing:
            errors.append(
                f"{items[0]['skill']} 缺少规定产物：{'、'.join(sorted(missing))}"
            )
        if unexpected:
            errors.append(
                f"{items[0]['skill']} 出现未登记产物：{'、'.join(sorted(unexpected))}"
            )

        source_skill = items[0]["skill"]
        if source_skill == "cn-procedure":
            errors.extend(audit_procedure(output_dir, items, file_records))
        errors.extend(audit_docx_files(output_dir, source_skill, file_records))
        for path in sorted(output_dir.iterdir()):
            if path.is_file() and path.suffix.lower() != ".docx":
                file_records.append(
                    {
                        "path": str(path),
                        "sha256": sha256(path),
                        "source_skill": source_skill,
                    }
                )

    # BUG-C/D 修复：交付包检查——delivery/ 存在、manifest 齐全、每项 DOCX 副本哈希一致、无中间产物
    delivery_package = case_root / "delivery"
    if not delivery_package.is_dir():
        errors.append("缺少 delivery 交付包目录（打包步骤未执行）")
    else:
        manifest_path = delivery_package / "delivery-manifest.json"
        if not manifest_path.is_file():
            errors.append("delivery 交付包缺少 delivery-manifest.json")
        else:
            try:
                manifest = load_json(manifest_path)
            except ExecutionAuditError as exc:
                errors.append(str(exc))
                manifest = None
            if manifest is not None:
                for item in ready:
                    if not item.get("docx_supported"):
                        continue
                    delivery_dir = item.get("delivery_dir") or "交付文书"
                    source_docx = None
                    artifact = item.get("docx_artifact")
                    source_out = Path(item["output_dir"])
                    if item.get("docx_artifacts"):
                        for art in item["docx_artifacts"]:
                            tgt = delivery_package / delivery_dir / art
                            if not tgt.is_file():
                                errors.append(f"交付包缺少 {item['deliverable_id']}：{delivery_dir}/{art}")
                            elif sha256(tgt) != sha256(source_out / art):
                                errors.append(f"交付包副本哈希不一致：{item['deliverable_id']}（{art}）")
                        continue
                    if artifact:
                        source_docx = source_out / artifact
                    else:
                        candidates = sorted(source_out.glob("*.docx"))
                        if len(candidates) == 1:
                            source_docx = candidates[0]
                        else:
                            matched = [c for c in candidates if c.name.startswith((item.get("template_id") or item["deliverable_id"]) + "-")]
                            if len(matched) == 1:
                                source_docx = matched[0]
                    if source_docx is None or not source_docx.is_file():
                        continue  # 缺失已在 DOCX 成品检查中报错
                    target = delivery_package / delivery_dir / source_docx.name
                    if not target.is_file():
                        errors.append(
                            f"交付包缺少 {item['deliverable_id']}：{delivery_dir}/{source_docx.name}"
                        )
                    elif sha256(target) != sha256(source_docx):
                        errors.append(f"交付包副本哈希不一致：{item['deliverable_id']}")
                stray = [
                    str(path.relative_to(delivery_package))
                    for path in sorted(delivery_package.rglob("*"))
                    if path.is_file()
                    and path.suffix.lower() in (".md", ".json")
                    and path.name != "delivery-manifest.json"
                ]
                if stray:
                    errors.append("交付包混入中间产物：" + "、".join(stray[:5]))

    verify_dir = case_root / "cn-verify"
    if not verify_dir.is_dir():
        # 2026-08-10 收纳兼容：中间产物收纳到 workspace/ 后，cn-verify 位于 workspace/
        alt_verify = case_root / "workspace" / "cn-verify"
        if alt_verify.is_dir():
            verify_dir = alt_verify
        else:
            errors.append("缺少 cn-verify 最终核验目录")
    if verify_dir.is_dir():
        review_paths = sorted(verify_dir.rglob("review-report.json"))
        if not review_paths:
            errors.append("cn-verify 缺少逐文书 review-report.json")
        reviewed_docx_hashes: set[str] = set()
        verify_module = load_module(
            SKILLS_ROOT / "cn-verify" / "scripts" / "verify_document.py",
            "cn_verify_report_schema_from_orchestrator",
        )
        try:
            verify_registry = verify_module.build_registry(SKILLS_ROOT / "cn-verify")
        except RuntimeError as exc:
            errors.append(f"无法加载 cn-verify 报告 Schema：{exc}")
            verify_registry = None
        report_schema_path = SKILLS_ROOT / "cn-verify" / "schemas" / "review-report.schema.json"
        docx_hashes = {
            record["sha256"]
            for record in file_records
            if Path(record["path"]).suffix.lower() == ".docx"
        }
        for review_path in review_paths:
            markdown_path = review_path.with_suffix(".md")
            if not markdown_path.is_file():
                errors.append(f"cn-verify 报告缺少 Markdown 副本：{review_path.parent}")
                continue
            try:
                report = load_json(review_path)
            except ExecutionAuditError as exc:
                errors.append(str(exc))
                continue
            if verify_registry is not None:
                schema_issues = verify_module.schema_errors(
                    report,
                    report_schema_path,
                    verify_registry,
                )
                errors.extend(f"{review_path}：{issue}" for issue in schema_issues)
            state = report.get("state")
            blocker_count = report.get("summary", {}).get("blocker")
            input_sha256 = report.get("input_sha256")
            if state == "blocked" or blocker_count != 0:
                errors.append(f"cn-verify 仍有 blocker：{review_path}")
            if state not in {"lawyer_review_required", "machine_checked"}:
                errors.append(f"cn-verify 报告状态无效：{review_path}")
            if input_sha256 in reviewed_docx_hashes:
                errors.append(f"cn-verify 重复核验同一 DOCX：{review_path}")
            if input_sha256 in docx_hashes:
                reviewed_docx_hashes.add(input_sha256)
            elif docx_hashes:
                errors.append(f"cn-verify 报告未对应本次 DOCX：{review_path}")
            for path in (review_path, markdown_path):
                file_records.append(
                    {
                        "path": str(path),
                        "sha256": sha256(path),
                        "source_skill": "cn-verify",
                    }
                )
        missing_reviews = sorted(docx_hashes - reviewed_docx_hashes)
        if missing_reviews:
            errors.append(f"cn-verify 未逐份覆盖 {len(missing_reviews)} 份 DOCX")

    return {
        "schema_version": "1.0",
        "task_id": plan.get("task_id"),
        "plan_sha256": plan.get("plan_sha256"),
        "author": AUTHOR,
        "audited_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "passed" if not errors else "blocked",
        "errors": errors,
        "warnings": warnings,
        "files": sorted(file_records, key=lambda item: item["path"]),
        "artifact_state": "lawyer_review_required",
    }


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 主路由交付审计",
        "",
        f"- 任务编号：{result.get('task_id', '')}",
        f"- 审计状态：{result['status']}",
        f"- 执行计划哈希：`{result.get('plan_sha256', '')}`",
        f"- 文件数量：{len(result['files'])}",
        "",
        "## 阻断项",
        "",
    ]
    if result["errors"]:
        lines.extend(f"- {item}" for item in result["errors"])
    else:
        lines.append("- 无")
    lines.extend(["", "## 已核对文件", ""])
    lines.extend(
        f"- `{item['source_skill']}`：`{item['path']}`（SHA-256：`{item['sha256']}`）"
        for item in result["files"]
    )
    lines.extend(
        [
            "",
            "本报告仅表示机器流程、文件集合、来源与品牌检查结果，最终文书仍须由执业律师逐项复核。",
            "",
        ]
    )
    return "\n".join(lines)


def write_new(output: Path, result: dict[str, Any]) -> None:
    if not output.is_absolute():
        raise ExecutionAuditError("交付审计输出目录必须使用绝对路径")
    resolved = output.resolve(strict=False)
    skills_root = SKILLS_ROOT.resolve()
    if resolved == skills_root or is_relative_to(resolved, skills_root):
        raise ExecutionAuditError(f"禁止把交付审计写入 Skill 目录：{resolved}")
    if resolved.exists():
        raise FileExistsError(f"拒绝覆盖：{resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{resolved.name}-", dir=resolved.parent))
    try:
        (temporary / "delivery-audit.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (temporary / "delivery-audit.md").write_text(markdown(result), encoding="utf-8")
        os.replace(temporary, resolved)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="按主路由计划验收全部下游产物")
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = audit(load_json(args.plan))
        write_new(args.output, result)
    except (ExecutionAuditError, FileExistsError) as exc:
        print(f"[ERROR] {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
