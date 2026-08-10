#!/usr/bin/env python3
"""中国法律尽调底稿的共享验证、分区与原子输出逻辑。"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


MAX_INPUT_BYTES = 8 * 1024 * 1024
SKILL_DIR = Path(__file__).resolve().parent.parent
INPUT_SCHEMA = SKILL_DIR / "schemas" / "diligence-input.schema.json"
OUTPUT_SCHEMA = SKILL_DIR / "schemas" / "diligence-output.schema.json"


class InputError(ValueError):
    """输入或输出目标无法安全处理。"""


def load_json_file(path_value: str | Path) -> dict[str, Any]:
    path = Path(path_value)
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise InputError(f"输入文件不存在：{path}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise InputError("拒绝读取符号链接输入。")
    if not stat.S_ISREG(info.st_mode):
        raise InputError("输入必须是普通 JSON 文件。")
    if info.st_size > MAX_INPUT_BYTES:
        raise InputError(f"输入超过 {MAX_INPUT_BYTES} 字节限制。")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise InputError("输入必须使用 UTF-8 编码。") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"JSON 解析失败：{exc}") from exc
    if not isinstance(value, dict):
        raise InputError("JSON 顶层必须是对象。")
    return value


def _schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _path(error: Any) -> str:
    return "$" + "".join(
        f"[{part}]" if isinstance(part, int) else f".{part}"
        for part in error.absolute_path
    )


def schema_errors(data: dict[str, Any], *, output: bool = False) -> list[str]:
    schema = _schema(OUTPUT_SCHEMA if output else INPUT_SCHEMA)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path))
    return [f"{_path(error)}: {error.message}" for error in errors]


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: set[str] = set()
    for value in values:
        if value in seen:
            result.add(value)
        seen.add(value)
    return sorted(result)


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def gate_checks(data: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """返回（结构错误、复核阻断项、警告）。"""
    fatal = schema_errors(data)
    if fatal:
        return fatal, [], []

    blockers: list[str] = []
    warnings: list[str] = []
    cutoff = _parse_datetime(data["data_room_cutoff"])

    documents = {item["document_id"]: item for item in data["documents"]}
    duplicate_document_ids = _duplicates([item["document_id"] for item in data["documents"]])
    if duplicate_document_ids:
        fatal.append(f"存在重复 document_id：{', '.join(duplicate_document_ids)}")

    known_spans: set[tuple[str, str]] = set()
    for document in data["documents"]:
        span_ids = [span["span_id"] for span in document["spans"]]
        duplicates = _duplicates(span_ids)
        if duplicates:
            fatal.append(f"资料 {document['document_id']} 存在重复 span_id：{', '.join(duplicates)}")
        known_spans.update((document["document_id"], span_id) for span_id in span_ids)
        if _parse_datetime(document["received_at"]) > cutoff:
            blockers.append(f"资料 {document['document_id']} 接收时间晚于数据室截止时间。")
        if not document["hash_verified"]:
            blockers.append(f"资料 {document['document_id']} 未完成文件 SHA-256 核验。")

    def check_span_refs(owner: str, refs: list[dict[str, str]]) -> None:
        for ref in refs:
            key = (ref["document_id"], ref["span_id"])
            if key not in known_spans:
                fatal.append(f"{owner} 引用未登记来源定位：{key[0]}/{key[1]}")

    request_ids = [item["request_id"] for item in data["material_requests"]]
    duplicates = _duplicates(request_ids)
    if duplicates:
        fatal.append(f"存在重复 request_id：{', '.join(duplicates)}")
    for request in data["material_requests"]:
        missing = sorted(set(request["related_document_ids"]) - set(documents))
        if missing:
            fatal.append(f"资料请求 {request['request_id']} 引用未登记文件：{', '.join(missing)}")

    representation_ids = [item["representation_id"] for item in data["management_representations"]]
    duplicates = _duplicates(representation_ids)
    if duplicates:
        fatal.append(f"存在重复 representation_id：{', '.join(duplicates)}")
    for item in data["management_representations"]:
        check_span_refs(f"管理层陈述 {item['representation_id']}", item["source_spans"])
        if item["confirmation_status"] != "independently_corroborated":
            warnings.append(f"管理层陈述 {item['representation_id']} 尚未经独立资料交叉验证。")

    authorities = {item["authority_id"]: item for item in data["authorities"]}
    duplicates = _duplicates([item["authority_id"] for item in data["authorities"]])
    if duplicates:
        fatal.append(f"存在重复 authority_id：{', '.join(duplicates)}")
    cutoff_date = cutoff.date()
    for authority in data["authorities"]:
        if date.fromisoformat(authority["verified_on"]) > cutoff_date:
            blockers.append(f"法源 {authority['authority_id']} 核验日晚于数据室截止日。")
        if authority["verification_status"] != "verified_official":
            blockers.append(f"法源 {authority['authority_id']} 尚未完成官方全文核验。")
        if authority["effect_status"] != "effective":
            blockers.append(f"法源 {authority['authority_id']} 效力状态为 {authority['effect_status']}。")

    finding_ids = [item["finding_id"] for item in data["findings"]]
    duplicates = _duplicates(finding_ids)
    if duplicates:
        fatal.append(f"存在重复 finding_id：{', '.join(duplicates)}")
    for finding in data["findings"]:
        check_span_refs(f"发现 {finding['finding_id']}", finding["source_spans"])
        missing = sorted(set(finding["authority_ids"]) - set(authorities))
        if missing:
            fatal.append(f"发现 {finding['finding_id']} 引用未登记法源：{', '.join(missing)}")
        if finding["kind"] == "legal" and not finding["authority_ids"]:
            fatal.append(f"法律发现 {finding['finding_id']} 缺少法源核验记录。")

    if data["mode"] == "training_fixture":
        warnings.append("当前为教学测试模式，不得当作真实尽调结果。")

    return sorted(set(fatal)), sorted(set(blockers)), sorted(set(warnings))


def build_workpaper(data: dict[str, Any]) -> dict[str, Any]:
    fatal, blockers, warnings = gate_checks(data)
    if fatal:
        raise InputError("输入验证失败：" + "；".join(fatal))

    by_kind = {
        kind: sorted(
            (item for item in data["findings"] if item["kind"] == kind),
            key=lambda item: item["finding_id"],
        )
        for kind in ("fact", "legal", "exception", "red_flag")
    }
    missing = []
    for request in sorted(data["material_requests"], key=lambda item: item["request_id"]):
        if request["status"] not in {"partial", "not_provided"}:
            continue
        copy = dict(request)
        copy["interpretation_limit"] = (
            "仅表示截至数据室截止时点尚未提供或未完整提供，"
            "不推定相关资料或事实不存在。"
        )
        missing.append(copy)

    workpaper = {
        "schema_version": "1.0",
        "matter_id": data["matter_id"],
        "mode": data["mode"],
        "jurisdiction": data["jurisdiction"],
        "data_room_cutoff": data["data_room_cutoff"],
        "artifact_state": "lawyer_review_required",
        "transaction_assessment": "not_performed",
        "documents": sorted(data["documents"], key=lambda item: item["document_id"]),
        "material_requests": sorted(data["material_requests"], key=lambda item: item["request_id"]),
        "fact_findings": by_kind["fact"],
        "legal_findings": by_kind["legal"],
        "exceptions": by_kind["exception"],
        "red_flags": by_kind["red_flag"],
        "not_provided_materials": missing,
        "management_representations": sorted(data["management_representations"], key=lambda item: item["representation_id"]),
        "authorities": sorted(data["authorities"], key=lambda item: item["authority_id"]),
        "blockers": blockers,
        "warnings": warnings,
    }
    output_errors = schema_errors(workpaper, output=True)
    if output_errors:
        raise RuntimeError("内部输出未通过 Schema：" + "；".join(output_errors))
    return workpaper


def render_markdown(workpaper: dict[str, Any]) -> str:
    lines = [
        "# 中国法律尽职调查律师复核底稿",
        "",
        f"- 项目编号：{workpaper['matter_id']}",
        f"- 数据室截止时间：{workpaper['data_room_cutoff']}",
        "- 底稿状态：律师复核必需",
        "- 交易评估：未执行",
        "",
    ]
    sections = [
        ("事实发现", "fact_findings"), ("法律发现", "legal_findings"),
        ("例外项", "exceptions"), ("红旗线索", "red_flags"),
    ]
    for title, key in sections:
        lines.extend([f"## {title}", ""])
        items = workpaper[key]
        if not items:
            lines.extend(["暂无录入项。", ""])
            continue
        for item in items:
            refs = "、".join(f"{ref['document_id']}/{ref['span_id']}" for ref in item["source_spans"])
            lines.extend([f"### {item['finding_id']} {item['title']}", "", item["statement"], "", f"来源定位：{refs}", ""])
    lines.extend(["## 未提供或未完整提供材料", ""])
    if workpaper["not_provided_materials"]:
        for item in workpaper["not_provided_materials"]:
            lines.append(f"- {item['request_id']}：{item['description']}（{item['status']}）。{item['interpretation_limit']}")
    else:
        lines.append("暂无录入项。")
    lines.extend(["", "## 管理层陈述", ""])
    for item in workpaper["management_representations"]:
        lines.append(f"- {item['representation_id']}：{item['statement']}（{item['confirmation_status']}）")
    lines.extend(["", "## 阻断项", ""])
    lines.extend([f"- {item}" for item in workpaper["blockers"]] or ["- 无额外结构性阻断项；仍须律师实质复核。"])
    lines.extend(["", "## 警告", ""])
    lines.extend([f"- {item}" for item in workpaper["warnings"]] or ["- 无。"])
    lines.extend(["", "> 本文件仅为律师复核底稿，不是正式尽调报告，不包含交易通过或否的自动评估。", ""])
    return "\n".join(lines)


def atomic_write_workpaper(workpaper: dict[str, Any], output_value: str | Path) -> Path:
    output = Path(output_value)
    if output.exists() or output.is_symlink():
        raise InputError(f"输出目标已存在，拒绝覆盖：{output}")
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=parent))
    try:
        (temp / "diligence-workpaper.json").write_text(
            json.dumps(workpaper, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (temp / "diligence-workpaper.md").write_text(render_markdown(workpaper), encoding="utf-8")
        os.replace(temp, output)
    except Exception:
        for child in temp.iterdir() if temp.exists() else []:
            child.unlink()
        if temp.exists():
            temp.rmdir()
        raise
    return output
