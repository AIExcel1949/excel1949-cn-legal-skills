#!/usr/bin/env python3
"""对结构化中国法律文书核验包执行只读、确定性终检。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


SEVERITY_ORDER = {"blocker": 0, "warning": 1, "note": 2}
MAX_ARTIFACT_BYTES = 100 * 1024 * 1024
CATEGORIES = [
    "fact",
    "evidence",
    "authority",
    "number",
    "date",
    "citation",
    "consistency",
    "privacy",
    "confirmation",
    "scope",
]
LIMITATIONS = [
    "本报告只证明已按结构化输入执行机器规则，不证明事实真实、证据可采或法律适用正确。",
    "AI 不能替代律师对案件具体情况进行独立法律判断，最终文书须经执业律师逐项审查与确认。",
    "原稿内容、哈希或案件台账发生变化后，本报告失效，必须重新终检。",
]
DISCLAIMERS = [
    "AI 生成的法律文书仅供学习参考，不得直接用于提交法院或对方当事人。",
    "使用 AI 生成文书前，必须由专业执业律师人工核验事实与法律适用。",
    "AI 不能替代律师对案件具体情况进行独立法律判断。",
    "本课程 AI 仅用于辅助写法律文书，最终法律文书须经专业律师逐案审查与确认。",
    "AI 生成文书质量高低，起决定性因素的是使用者自身法律水平的高低。",
]

PLACEHOLDER_PATTERNS = [
    re.compile(r"\{\{[^{}\n]{1,100}\}\}"),
    re.compile(r"\{[A-Za-z_][A-Za-z0-9_.-]{1,80}\}"),
    re.compile(r"【(?:待补|待填|待确认|未定|请填)[^】]{0,40}】"),
    re.compile(r"(?<![A-Za-z])(?:TBD|TODO|XXX)(?![A-Za-z])", re.IGNORECASE),
]
SENSITIVE_PATTERNS = {
    "身份证号": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "手机号": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "银行卡号": re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)"),
    "邮箱": re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])"),
}
PARTIAL_EMAIL_PATTERN = re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]*")
LONG_DIGIT_PATTERN = re.compile(r"(?<!\d)\d{6,}(?!\d)")
MONEY_PATTERN = re.compile(r"(?:人民币\s*)?[0-9０-９][0-9０-９,，.．\s]{0,24}元")
DATE_PATTERN = re.compile(r"(?<!\d)(?:20\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])|20\d{2}年(?:0?[1-9]|1[0-2])月(?:0?[1-9]|[12]\d|3[01])日)(?!\d)")
STABLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def mask_sensitive(value: str) -> str:
    result = value
    for label, pattern in SENSITIVE_PATTERNS.items():
        result = pattern.sub(f"【{label}已脱敏】", result)
    # 摘录窗口可能截断完整号码或邮箱，必须继续清理残留片段。
    result = PARTIAL_EMAIL_PATTERN.sub("【邮箱片段已脱敏】", result)
    result = LONG_DIGIT_PATTERN.sub("【数字标识已脱敏】", result)
    return result


def excerpt(value: str, start: int = 0, end: int | None = None, radius: int = 28) -> str:
    if end is None:
        end = start
    left = max(0, start - radius)
    right = min(len(value), end + radius)
    selected = value[left:right].replace("\n", " ").strip()
    if left:
        selected = "…" + selected
    if right < len(value):
        selected += "…"
    return mask_sensitive(selected)


def compact(value: Any) -> str:
    return re.sub(r"[\s,，]", "", str(value))


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def safe_id(value: Any, fallback: str) -> str:
    candidate = str(value or "")
    return candidate if STABLE_ID_PATTERN.fullmatch(candidate) else fallback


def safe_datetime(value: Any) -> str:
    candidate = str(value or "")
    if not DATETIME_PATTERN.fullmatch(candidate):
        return "1970-01-01T00:00:00+00:00"
    try:
        parse_datetime(candidate)
    except (TypeError, ValueError):
        return "1970-01-01T00:00:00+00:00"
    return candidate


def safe_sha256(value: Any) -> str:
    candidate = str(value or "")
    return candidate if SHA256_PATTERN.fullmatch(candidate) else "0" * 64


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("输入 JSON 根节点必须是对象")
    return value, raw


def load_artifact_bytes(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError("拒绝读取符号链接原文件")
    if not path.is_file():
        raise FileNotFoundError(f"原文件不存在：{path}")
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError(f"原文件超过 {MAX_ARTIFACT_BYTES} 字节限制")
    return path.read_bytes()


def build_registry(skill_root: Path):
    try:
        from referencing import Registry, Resource
    except ImportError as exc:
        raise RuntimeError("缺少 referencing 依赖") from exc
    registry = Registry()
    roots = [skill_root / "schemas", skill_root.parent / "cn-legal-core" / "schemas"]
    for root in roots:
        if not root.is_dir():
            raise RuntimeError(f"缺少 Schema 目录：{root}")
        for path in sorted(root.glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            schema_id = schema.get("$id")
            if schema_id:
                registry = registry.with_resource(schema_id, Resource.from_contents(schema))
    return registry


def schema_errors(value: dict[str, Any], schema_path: Path, registry: Any) -> list[str]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise RuntimeError("缺少 jsonschema 依赖") from exc
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda item: tuple(str(part) for part in item.absolute_path))
    output: list[str] = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        output.append(f"{location}：{error.message}")
    return output


class Findings:
    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = []

    def add(
        self,
        severity: str,
        category: str,
        code: str,
        message: str,
        *,
        location: str = "",
        evidence: str = "",
        source_refs: Iterable[str] = (),
        action: str,
        human: bool = False,
    ) -> None:
        self._items.append(
            {
                "severity": severity,
                "category": category,
                "code": code,
                "message": message,
                "location": location,
                "evidence": mask_sensitive(evidence),
                "source_refs": sorted({value for value in source_refs if value}),
                "action": action,
                "human_confirmation_required": human,
            }
        )

    def finalized(self) -> list[dict[str, Any]]:
        ordered = sorted(
            self._items,
            key=lambda item: (
                SEVERITY_ORDER[item["severity"]],
                item["category"],
                item["code"],
                item["location"],
                item["message"],
            ),
        )
        for index, item in enumerate(ordered, start=1):
            item["finding_id"] = f"FND-{index:04d}"
        return ordered


def check_placeholders(text: str, findings: Findings) -> None:
    seen: set[str] = set()
    for pattern in PLACEHOLDER_PATTERNS:
        for match in pattern.finditer(text):
            token = match.group(0)
            if token in seen:
                continue
            seen.add(token)
            findings.add(
                "blocker",
                "consistency",
                "CONSISTENCY.PLACEHOLDER",
                "原稿存在未处理占位符。",
                location=f"字符 {match.start()}",
                evidence=excerpt(text, match.start(), match.end()),
                action="回到事实或人工确认台账补齐内容，由律师确认后重新生成原稿。",
                human=True,
            )


def check_facts(data: dict[str, Any], text: str, findings: Findings) -> None:
    confirmed_by_field: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    supported_fact_ids: set[str] = set()
    for wrapper in data.get("evidence", []):
        record = wrapper.get("record", {})
        supported_fact_ids.update(record.get("fact_ids", []))

    for wrapper in data.get("facts", []):
        record = wrapper.get("record", {})
        fact_id = str(record.get("fact_id", "未知事实"))
        status = record.get("status")
        field = str(record.get("field", ""))
        refs = [span.get("source_id", "") for span in record.get("source_spans", []) if span.get("source_id")]
        if status in {"missing", "conflict", "unreadable"}:
            findings.add(
                "blocker", "fact", "FACT.UNRESOLVED", f"事实 {fact_id} 的状态为 {status}。",
                location=f"facts.{fact_id}", source_refs=refs,
                action="核对原始材料并将真实结果回写事实台账，不得用推测值填补。", human=True,
            )
        elif status == "disputed":
            findings.add(
                "warning", "fact", "FACT.DISPUTED", f"事实 {fact_id} 仍有争议。",
                location=f"facts.{fact_id}", source_refs=refs,
                action="在文书中如实区分己方主张、对方异议和待证事实。", human=True,
            )
        if status == "derived" and not record.get("derivation_rule"):
            findings.add(
                "warning", "fact", "FACT.DERIVATION_MISSING", f"推导事实 {fact_id} 未记录推导规则。",
                location=f"facts.{fact_id}", source_refs=refs,
                action="补录计算、换算或推理过程，并由律师核对。", human=True,
            )
        display_text = wrapper.get("display_text", "")
        if wrapper.get("required_in_document") and (not display_text or display_text not in text):
            findings.add(
                "blocker", "fact", "FACT.TEXT_MISSING", f"事实 {fact_id} 的必填字面内容未在原稿中出现。",
                location=f"facts.{fact_id}.display_text", evidence=display_text,
                source_refs=refs, action="核对事实台账与原稿版本，由律师决定是否补入或取消必填标记。", human=True,
            )
        if wrapper.get("evidence_required") and fact_id not in supported_fact_ids:
            findings.add(
                "blocker", "evidence", "EVIDENCE.FACT_GAP", f"必要事实 {fact_id} 没有关联证据。",
                location=f"facts.{fact_id}", action="在证据台账中关联已取得的真实证据；如尚未取得，明确标记证据缺口。", human=True,
            )
        if field and status in {"stated", "user_confirmed"}:
            confirmed_by_field[field].append((fact_id, record.get("normalized_value", record.get("raw_value"))))

    for field, items in sorted(confirmed_by_field.items()):
        values = {json.dumps(value, ensure_ascii=False, sort_keys=True) for _, value in items}
        if len(values) > 1:
            findings.add(
                "blocker", "consistency", "CONSISTENCY.FACT_CONFLICT", f"字段 {field} 存在多个不一致的已记录值。",
                location=f"facts.field.{field}", source_refs=[item[0] for item in items],
                action="回查原始来源，保留冲突状态并由律师确定原稿表述。", human=True,
            )


def check_evidence(data: dict[str, Any], findings: Findings) -> None:
    known_fact_ids = {wrapper.get("record", {}).get("fact_id") for wrapper in data.get("facts", [])}
    for wrapper in data.get("evidence", []):
        record = wrapper.get("record", {})
        evidence_id = str(record.get("evidence_id", "未知证据"))
        for dimension in ("authenticity", "legality", "relevance"):
            status = record.get(dimension, "unknown")
            if status == "disputed":
                findings.add(
                    "blocker", "evidence", "EVIDENCE.DISPUTED", f"证据 {evidence_id} 的 {dimension} 存在争议。",
                    location=f"evidence.{evidence_id}.{dimension}", source_refs=[record.get("source_id", "")],
                    action="核对原件、取得过程和待证关系，并在文书中如实处理争议。", human=True,
                )
            elif status in {"unknown", "unreviewed"}:
                findings.add(
                    "warning", "evidence", "EVIDENCE.UNREVIEWED", f"证据 {evidence_id} 的 {dimension} 尚未完成审查。",
                    location=f"evidence.{evidence_id}.{dimension}", source_refs=[record.get("source_id", "")],
                    action="由律师完成证据三性审查并更新台账。", human=True,
                )
        if record.get("verification_status") != "human_checked":
            findings.add(
                "warning", "evidence", "EVIDENCE.HUMAN_CHECK_PENDING", f"证据 {evidence_id} 未标记为已人工核验。",
                location=f"evidence.{evidence_id}.verification_status", source_refs=[record.get("source_id", "")],
                action="由负责律师对照原始载体完成人工核验。", human=True,
            )
        for fact_id in record.get("fact_ids", []):
            if fact_id not in known_fact_ids:
                findings.add(
                    "blocker", "evidence", "EVIDENCE.UNKNOWN_FACT", f"证据 {evidence_id} 关联了不存在的事实 {fact_id}。",
                    location=f"evidence.{evidence_id}.fact_ids", source_refs=[record.get("source_id", "")],
                    action="修正证据与事实台账的稳定标识关联。", human=False,
                )


def check_authorities(data: dict[str, Any], findings: Findings) -> None:
    as_of = parse_datetime(data["review_context"]["as_of"])
    max_age = data["review_context"].get("max_authority_age_days", 90)
    for wrapper in data.get("authorities", []):
        record = wrapper.get("record", {})
        authority_id = str(record.get("authority_id", "未知法源"))
        status = record.get("effect_status")
        if wrapper.get("relied_upon") and status in {"repealed", "not_yet_effective", "unknown"}:
            findings.add(
                "blocker", "authority", "AUTHORITY.INVALID_EFFECT", f"当前依据 {authority_id} 的效力状态为 {status}。",
                location=f"authorities.{authority_id}.effect_status", source_refs=[record.get("source_url", "")],
                action="从官方来源核验现行文本和时间效力，由律师重新确定法律依据。", human=True,
            )
        elif wrapper.get("relied_upon") and status == "amended":
            findings.add(
                "warning", "authority", "AUTHORITY.AMENDED", f"当前依据 {authority_id} 已修改。",
                location=f"authorities.{authority_id}.effect_status", source_refs=[record.get("source_url", "")],
                action="核对案件时点应适用的条文版本及衔接规则。", human=True,
            )
        verified_at = record.get("verified_at")
        if verified_at:
            age = (as_of - parse_datetime(verified_at)).total_seconds() / 86400
            if age < 0:
                findings.add(
                    "blocker", "authority", "AUTHORITY.FUTURE_VERIFICATION", f"法源 {authority_id} 的核验时间晚于本次终检时点。",
                    location=f"authorities.{authority_id}.verified_at", action="核对时区与时间记录。", human=False,
                )
            elif wrapper.get("relied_upon") and age > max_age:
                findings.add(
                    "warning", "authority", "AUTHORITY.STALE_CHECK", f"法源 {authority_id} 距上次核验已超过 {max_age} 日。",
                    location=f"authorities.{authority_id}.verified_at", source_refs=[record.get("source_url", "")],
                    action="在官方来源重新核验效力状态和现行文本。", human=True,
                )


def check_numbers_and_dates(data: dict[str, Any], text: str, findings: Findings) -> None:
    tracked_amounts: set[str] = set()
    for wrapper in data.get("calculations", []):
        record = wrapper.get("record", {})
        calc_id = str(record.get("calculation_id", "未知计算"))
        display_text = wrapper.get("display_text", "")
        tracked_amounts.add(compact(display_text))
        if display_text not in text:
            findings.add(
                "blocker", "number", "NUMBER.TEXT_MISSING", f"计算 {calc_id} 的展示值未在原稿中出现。",
                location=f"calculations.{calc_id}.display_text", evidence=display_text,
                action="对照计算台账与原稿版本，核对金额、币种、精度和四舍五入规则。", human=True,
            )
        try:
            expected = Decimal(str(record.get("output")))
            recalculated = Decimal(str(wrapper.get("recalculated_value")))
            tolerance = Decimal(str(wrapper.get("tolerance", 0.01)))
            if abs(expected - recalculated) > tolerance:
                findings.add(
                    "blocker", "number", "NUMBER.RECALC_MISMATCH", f"计算 {calc_id} 的台账结果与重算值不一致。",
                    location=f"calculations.{calc_id}", evidence=f"台账结果：{expected}；重算值：{recalculated}；容差：{tolerance}",
                    action="回查输入、公式、分步计算与取整规则，由律师确认采用结果。", human=True,
                )
        except (InvalidOperation, TypeError):
            findings.add(
                "blocker", "number", "NUMBER.NOT_NUMERIC", f"计算 {calc_id} 的输出无法作数值比对。",
                location=f"calculations.{calc_id}.output", action="将数值结果与文本说明分字段记录。", human=False,
            )
    for amount in sorted(set(MONEY_PATTERN.findall(text))):
        if compact(amount) not in tracked_amounts:
            start = text.find(amount)
            findings.add(
                "warning", "number", "NUMBER.UNTRACKED_AMOUNT", "原稿中的金额未进入计算台账。",
                location=f"字符 {start}", evidence=excerpt(text, start, start + len(amount)),
                action="将需要校验的金额及计算过程纳入 calculations；如无需计算，由律师记录核对结论。", human=True,
            )

    tracked_dates: set[str] = set()
    for item in data.get("date_checks", []):
        date_id = str(item.get("date_id", "未知日期"))
        display_text = item.get("display_text", "")
        tracked_dates.add(compact(display_text))
        if item.get("required_in_document") and display_text not in text:
            findings.add(
                "blocker", "date", "DATE.TEXT_MISSING", f"日期 {date_id} 的必填文本未在原稿中出现。",
                location=f"date_checks.{date_id}.display_text", evidence=display_text, source_refs=[item.get("source", "")],
                action="核对原始来源、时区和文书版本，不得根据上下文猜测日期。", human=True,
            )
    for wrapper in data.get("deadlines", []):
        record = wrapper.get("record", {})
        deadline_id = str(record.get("deadline_id", "未知期限"))
        status = record.get("status")
        display_text = wrapper.get("display_text", "")
        if display_text:
            tracked_dates.add(compact(display_text))
        if wrapper.get("relied_upon") and status == "blocked":
            findings.add(
                "blocker", "date", "DATE.DEADLINE_BLOCKED", f"当前依据期限 {deadline_id} 无法计算。",
                location=f"deadlines.{deadline_id}.status", action="补齐起算事件、送达日期、期间性质和例外规则，再重新计算。", human=True,
            )
        elif wrapper.get("relied_upon") and status == "provisional":
            findings.add(
                "warning", "date", "DATE.DEADLINE_PROVISIONAL", f"当前依据期限 {deadline_id} 仍为临时结果。",
                location=f"deadlines.{deadline_id}.status", action="由律师核对起算日、顺延、时区和特别规则。", human=True,
            )
        if wrapper.get("relied_upon") and display_text and display_text not in text:
            findings.add(
                "blocker", "date", "DATE.DEADLINE_TEXT_MISSING", f"期限 {deadline_id} 的展示文本未在原稿中出现。",
                location=f"deadlines.{deadline_id}.display_text", evidence=display_text,
                action="核对原稿是否应使用该期限，并由律师确认。", human=True,
            )
    for date_text in sorted(set(DATE_PATTERN.findall(text))):
        if compact(date_text) not in tracked_dates:
            start = text.find(date_text)
            findings.add(
                "warning", "date", "DATE.UNTRACKED", "原稿中的日期未进入日期或期限台账。",
                location=f"字符 {start}", evidence=excerpt(text, start, start + len(date_text)),
                action="确认该日期的性质与来源，需影响结论时纳入核验台账。", human=True,
            )


def check_citations(data: dict[str, Any], text: str, findings: Findings) -> None:
    authorities = {wrapper.get("record", {}).get("authority_id"): wrapper.get("record", {}) for wrapper in data.get("authorities", [])}
    for citation in data.get("citations", []):
        citation_id = str(citation.get("citation_id", "未知引文"))
        authority_id = citation.get("authority_id")
        quote = citation.get("exact_quote", "")
        authority = authorities.get(authority_id)
        if authority is None:
            findings.add(
                "blocker", "citation", "CITATION.UNKNOWN_AUTHORITY", f"引文 {citation_id} 无法对应法源 {authority_id}。",
                location=f"citations.{citation_id}.authority_id", action="建立引文与已核验法源的稳定标识关联。", human=False,
            )
            continue
        if quote not in text:
            findings.add(
                "blocker", "citation", "CITATION.NOT_IN_DOCUMENT", f"引文 {citation_id} 的精确文本未在原稿中出现。",
                location=f"citations.{citation_id}.exact_quote", evidence=quote, source_refs=[authority.get("source_url", "")],
                action="对照官方原文和当前原稿，核定引文、省略与标点。", human=True,
            )
        verified_quote = authority.get("quoted_text", "")
        if not verified_quote or quote not in verified_quote:
            findings.add(
                "blocker", "citation", "CITATION.SOURCE_MISMATCH", f"引文 {citation_id} 不在法源台账的已核验原文中。",
                location=f"citations.{citation_id}", evidence=quote, source_refs=[authority.get("source_url", "")],
                action="打开官方全文，核对条文版本、上下文和文字，再更新台账。", human=True,
            )
        if not citation.get("locator"):
            findings.add(
                "warning", "citation", "CITATION.LOCATOR_MISSING", f"引文 {citation_id} 缺少条、款、页码或段落定位。",
                location=f"citations.{citation_id}.locator", source_refs=[authority.get("source_url", "")],
                action="补录可回查的精确定位。", human=False,
            )


def check_consistency(data: dict[str, Any], findings: Findings) -> None:
    for item in data.get("consistency_checks", []):
        check_id = str(item.get("check_id", "未知检查"))
        left = item.get("left_value")
        right = item.get("right_value")
        operator = item.get("operator")
        passed = left == right if operator == "equal" else left != right
        if not passed:
            findings.add(
                "blocker", "consistency", "CONSISTENCY.EXPLICIT_MISMATCH", f"一致性检查 {check_id} 未通过。",
                location=f"consistency_checks.{check_id}", evidence=f"{item.get('left_label')}：{left}；{item.get('right_label')}：{right}；条件：{operator}",
                action="回查两个值的原始来源，保留冲突并由律师确认原稿应采表述。", human=True,
            )


def check_privacy(data: dict[str, Any], text: str, findings: Findings) -> None:
    mode = data.get("review_context", {}).get("privacy_mode")
    occupied: list[tuple[int, int]] = []
    for label, pattern in SENSITIVE_PATTERNS.items():
        match = next(
            (
                candidate
                for candidate in pattern.finditer(text)
                if not any(candidate.start() < end and candidate.end() > start for start, end in occupied)
            ),
            None,
        )
        if not match:
            continue
        occupied.append((match.start(), match.end()))
        severity = "blocker" if mode == "external_public" else "warning"
        message = f"公开稿检出{label}。" if mode == "external_public" else f"原稿包含{label}，需核验处理必要性和授权。"
        findings.add(
            severity, "privacy", "PRIVACY.SENSITIVE_DATA", message,
            location=f"字符 {match.start()}", evidence=excerpt(text, match.start(), match.end()),
            action="根据收件人、处理目的和最小必要原则进行脱敏，并由律师确认共享范围。", human=True,
        )


def check_confirmations(data: dict[str, Any], findings: Findings) -> None:
    for item in data.get("human_confirmations", []):
        confirmation_id = str(item.get("confirmation_id", "未知确认项"))
        status = item.get("status")
        if status == "pending":
            severity = "blocker" if item.get("required") else "warning"
            findings.add(
                severity, "confirmation", "CONFIRMATION.PENDING", f"人工确认项 {confirmation_id} 尚未完成。",
                location=f"human_confirmations.{confirmation_id}", evidence=item.get("question", ""),
                action="由有权确认人员给出明确结论并记录姓名与时间，脚本不代为确认。", human=True,
            )
        elif status == "rejected":
            findings.add(
                "blocker", "confirmation", "CONFIRMATION.REJECTED", f"人工确认项 {confirmation_id} 已被否定。",
                location=f"human_confirmations.{confirmation_id}", evidence=item.get("question", ""),
                action="重新评估原稿中相关事实、授权或策略表述。", human=True,
            )


def check_unique_ids(data: dict[str, Any], findings: Findings) -> None:
    groups = {
        "facts": ("record", "fact_id"),
        "evidence": ("record", "evidence_id"),
        "authorities": ("record", "authority_id"),
        "calculations": ("record", "calculation_id"),
        "deadlines": ("record", "deadline_id"),
        "citations": (None, "citation_id"),
        "date_checks": (None, "date_id"),
        "consistency_checks": (None, "check_id"),
        "human_confirmations": (None, "confirmation_id"),
    }
    for group, (wrapper_key, id_key) in groups.items():
        values: list[str] = []
        for item in data.get(group, []):
            record = item.get(wrapper_key, {}) if wrapper_key else item
            value = record.get(id_key)
            if value:
                values.append(str(value))
        duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
        for value in duplicates:
            findings.add(
                "blocker", "consistency", "CONSISTENCY.DUPLICATE_ID", f"台账 {group} 中的稳定标识 {value} 重复。",
                location=f"{group}.{value}",
                action="为每条记录分配唯一且稳定的标识，并同步修正所有引用。", human=False,
            )
def build_report(
    data: dict[str, Any],
    raw: bytes,
    skill_root: Path,
    artifact_bytes: bytes | None = None,
) -> dict[str, Any]:
    findings = Findings()
    registry = build_registry(skill_root)
    errors = schema_errors(data, skill_root / "schemas" / "verify-input.schema.json", registry)
    for message in errors:
        findings.add(
            "blocker", "consistency", "SCHEMA.INVALID", "核验包不符合数据契约。",
            location=message.split("：", 1)[0], evidence=message,
            action="按 verify-input.schema.json 修正结构，不得删除未知、冲突或待确认状态。", human=False,
        )

    artifact = data.get("artifact", {}) if isinstance(data.get("artifact"), dict) else {}
    text = artifact.get("text", "") if isinstance(artifact.get("text", ""), str) else ""
    actual_text_sha = sha256_bytes(text.encode("utf-8"))
    if artifact.get("text_sha256") != actual_text_sha:
        findings.add(
            "blocker", "consistency", "HASH.TEXT_MISMATCH", "待检文本与 text_sha256 不一致。",
            location="artifact.text_sha256", evidence=f"计算值：{actual_text_sha}",
            action="从未修改的原稿快照重新提取文本并计算 SHA-256。", human=False,
        )
    if artifact_bytes is None:
        findings.add(
            "note", "scope", "HASH.INPUT_FILE_NOT_PROVIDED", "本次未传入原文件，未重新核对 input_sha256。",
            location="artifact.input_sha256",
            action="生产终检使用 --artifact-file 传入只读原文件并重新运行。", human=False,
        )
    else:
        actual_input_sha = sha256_bytes(artifact_bytes)
        if artifact.get("input_sha256") != actual_input_sha:
            findings.add(
                "blocker", "consistency", "HASH.INPUT_FILE_MISMATCH", "原文件与 input_sha256 不一致。",
                location="artifact.input_sha256", evidence=f"本次回读值：{actual_input_sha}",
                action="确认核验包和原文件属于同一版本，不得沿用其他版本的报告。", human=False,
            )
        else:
            findings.add(
                "note", "scope", "HASH.INPUT_FILE_VERIFIED", "本次已回读原文件并核对 input_sha256。",
                location="artifact.input_sha256",
                action="原文件发生任何变化后重新生成核验包。", human=False,
            )

    if not errors:
        check_unique_ids(data, findings)
        check_placeholders(text, findings)
        check_facts(data, text, findings)
        check_evidence(data, findings)
        check_authorities(data, findings)
        check_numbers_and_dates(data, text, findings)
        check_citations(data, text, findings)
        check_consistency(data, findings)
        check_privacy(data, text, findings)
        check_confirmations(data, findings)

    findings.add(
        "note", "scope", "SCOPE.READ_ONLY", "本次终检未直接改写原稿。",
        action="将问题清单交由律师逐项处理，修改后重新终检。", human=True,
    )
    findings.add(
        "note", "scope", "SCOPE.HUMAN_REVIEW", "机器终检不构成执业律师审查或定稿。",
        action="由执业律师核验事实、证据和法律适用并完成最终签发。", human=True,
    )
    final_findings = findings.finalized()
    counts = Counter(item["severity"] for item in final_findings)
    state = "blocked" if counts["blocker"] else "lawyer_review_required" if counts["warning"] else "machine_checked"
    context = data.get("review_context", {}) if isinstance(data.get("review_context"), dict) else {}
    report = {
        "schema_version": "1.0",
        "report_id": safe_id(context.get("review_id"), "REVIEW-UNKNOWN"),
        "matter_id": safe_id(data.get("matter_id"), "MATTER-UNKNOWN"),
        "artifact_id": safe_id(artifact.get("artifact_id"), "ARTIFACT-UNKNOWN"),
        "mode": context.get("mode") if context.get("mode") in {"production", "training_fixture"} else "production",
        "request_sha256": sha256_bytes(raw),
        "input_sha256": safe_sha256(artifact.get("input_sha256")),
        "text_sha256": actual_text_sha,
        "generated_at": safe_datetime(context.get("as_of")),
        "state": state,
        "summary": {
            "blocker": counts["blocker"],
            "warning": counts["warning"],
            "note": counts["note"],
            "total": len(final_findings),
        },
        "checked_categories": CATEGORIES,
        "findings": final_findings,
        "limitations": LIMITATIONS,
        "disclaimers": DISCLAIMERS,
    }
    report_errors = schema_errors(report, skill_root / "schemas" / "review-report.schema.json", registry)
    if report_errors:
        raise RuntimeError("生成的审计报告未通过 Schema 校验：" + "；".join(report_errors))
    return report


def render_markdown(report: dict[str, Any]) -> str:
    severity_titles = {"blocker": "Blocker", "warning": "Warning", "note": "Note"}
    state_titles = {"blocked": "阻断交付", "lawyer_review_required": "需律师复核", "machine_checked": "机器检查完成"}
    lines = [
        "# 中国法律文书终检报告",
        "",
        f"- 报告编号：`{report['report_id']}`",
        f"- 案件编号：`{report['matter_id']}`",
        f"- 文书编号：`{report['artifact_id']}`",
        f"- 数据模式：`{report['mode']}`",
        f"- 核验时点：`{report['generated_at']}`",
        f"- 结果：**{state_titles[report['state']]}**",
        f"- 问题统计：Blocker {report['summary']['blocker']} / Warning {report['summary']['warning']} / Note {report['summary']['note']}",
        f"- 原文件 SHA-256：`{report['input_sha256']}`",
        f"- 待检文本 SHA-256：`{report['text_sha256']}`",
        f"- 核验包 SHA-256：`{report['request_sha256']}`",
        "",
    ]
    for severity in ("blocker", "warning", "note"):
        lines.extend([f"## {severity_titles[severity]}", ""])
        items = [item for item in report["findings"] if item["severity"] == severity]
        if not items:
            lines.extend(["无。", ""])
            continue
        for item in items:
            lines.extend(
                [
                    f"### {item['finding_id']} · {item['code']}",
                    "",
                    f"- 类别：`{item['category']}`",
                    f"- 问题：{item['message']}",
                    f"- 定位：{item['location'] or '未定位'}",
                    f"- 证据片段：{item['evidence'] or '无'}",
                    f"- 处理方向：{item['action']}",
                    f"- 需人工确认：{'是' if item['human_confirmation_required'] else '否'}",
                    "",
                ]
            )
    lines.extend(["## 范围与限制", ""])
    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")
    lines.extend(["", "## 使用提示", ""])
    for index, disclaimer in enumerate(report["disclaimers"], start=1):
        lines.append(f"{index}. {disclaimer}")
    lines.append("")
    return "\n".join(lines)


def write_atomic(output_dir: Path, report: dict[str, Any]) -> None:
    if os.path.lexists(output_dir):
        raise FileExistsError(f"输出目录已存在，拒绝覆盖：{output_dir}")
    parent = output_dir.parent
    if not parent.is_dir():
        raise FileNotFoundError(f"输出父目录不存在：{parent}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=parent))
    try:
        json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        (temporary / "review-report.json").write_text(json_text, encoding="utf-8", newline="\n")
        (temporary / "review-report.md").write_text(render_markdown(report), encoding="utf-8", newline="\n")
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="对中国法律文书核验包执行只读终检")
    parser.add_argument("input", type=Path, help="结构化核验包 JSON")
    parser.add_argument("--artifact-file", type=Path, help="可选的只读原文件，用于核对 input_sha256")
    parser.add_argument("--output-dir", required=True, type=Path, help="必须尚不存在的输出目录")
    args = parser.parse_args()
    input_path = args.input.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    try:
        if not input_path.is_file():
            raise FileNotFoundError(f"输入文件不存在：{input_path}")
        if output_dir == input_path or input_path in output_dir.parents:
            raise ValueError("输出目录不得是输入文件或位于输入文件之下")
        data, raw = load_json(input_path)
        artifact_bytes = load_artifact_bytes(args.artifact_file.expanduser()) if args.artifact_file else None
        report = build_report(data, raw, Path(__file__).resolve().parent.parent, artifact_bytes)
        write_atomic(output_dir, report)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"终检失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps({"ok": report["state"] != "blocked", "state": report["state"], "summary": report["summary"], "output_dir": str(output_dir)}, ensure_ascii=False, indent=2))
    return 1 if report["state"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
