#!/usr/bin/env python3
"""用版本化 JSON 确定性填充程序文书模板。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from lxml import etree


SKILL_DIR = Path(__file__).resolve().parent.parent
REFERENCE_DIR = SKILL_DIR / "references"
SCHEMA_PATH = SKILL_DIR / "schemas/case-data.schema.json"
MANIFEST_PATH = SKILL_DIR / "schemas/template-manifest.json"
AUTHOR = "AIOffice职场通关-excel1949"
COMMENT = "AI辅助生成，须由执业律师逐项核验"
GENERATOR_VERSION = "2.2.0"
GUIDANCE_PATHS = (
    SKILL_DIR / "references/output-contract.md",
    SKILL_DIR / "references/template-catalog.md",
    SKILL_DIR / "references/data-contract.md",
    SKILL_DIR / "references/legal-basis.md",
    SKILL_DIR / "references/judicial-practice-guide.md",
    SKILL_DIR / "references/source-governance.md",
    MANIFEST_PATH,
)
PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)(?:\|[^{}]*)?\s*\}\}")
SINGLE_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([a-z][a-z0-9_]*)(?:\|[^{}]*)?\}(?!\})")
INVALID_FILENAME_RE = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")
CN_DATE_RE = re.compile(r"^([0-9]{4})\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日$")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CORE_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


class ValidationError(ValueError):
    """表示输入数据或模板不满足确定性生成条件。"""


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_output_path(path: Path) -> Path:
    if not path.is_absolute():
        raise ValidationError(
            "输出目录必须使用绝对路径；请写入当前项目的 output/cases/<matter-id>/cn-procedure"
        )
    resolved = path.resolve(strict=False)
    skills_root = SKILL_DIR.parent.resolve()
    if resolved == skills_root or is_relative_to(resolved, skills_root):
        raise ValidationError(f"禁止把运行时产物写入 Skill 目录：{resolved}")
    if resolved == Path(resolved.anchor):
        raise ValidationError("输出目录不得是文件系统根目录")
    return resolved


def guidance_records() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for path in GUIDANCE_PATHS:
        if not path.is_file():
            raise ValidationError(f"缺少强制参考文件：{path}")
        records.append(
            {
                "path": str(path.relative_to(SKILL_DIR)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return records


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"无法读取 JSON：{path}：{exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"JSON 顶层必须是对象：{path}")
    return value


def validate_schema(data: dict, schema: dict) -> list[str]:
    errors: list[str] = []
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for key in required:
        if key not in data or data[key] in (None, ""):
            errors.append(f"缺少全局必填字段：{key}")

    if schema.get("additionalProperties") is False:
        for key in sorted(set(data) - set(properties)):
            errors.append(f"存在未声明字段：{key}")

    for key, value in data.items():
        rule = properties.get(key)
        if not rule:
            continue
        if rule.get("type") == "string" and not isinstance(value, str):
            errors.append(f"字段 {key} 必须是字符串")
            continue
        if "const" in rule and value != rule["const"]:
            errors.append(f"字段 {key} 必须等于 {rule['const']}")
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"字段 {key} 的值不在允许范围内")
        if isinstance(value, str) and rule.get("minLength", 0) > len(value):
            errors.append(f"字段 {key} 不能为空")
        if isinstance(value, str) and value and rule.get("pattern"):
            if not re.fullmatch(rule["pattern"], value):
                errors.append(f"字段 {key} 格式不正确")

    for amount_key, upper_key in (("fee_amount", "fee_amount_cn"), ("annual_fee", "annual_fee_cn")):
        amount = data.get(amount_key, "")
        upper = data.get(upper_key, "")
        if amount and upper:
            try:
                expected = rmb_upper(amount)
            except ValidationError as exc:
                errors.append(str(exc))
            else:
                if upper != expected:
                    errors.append(f"字段 {upper_key} 与 {amount_key} 不一致，应为：{expected}")

    parsed_dates: dict[str, datetime] = {}
    for key in ("sign_date", "apply_date", "accept_date", "close_date", "service_start_date", "service_end_date"):
        value = data.get(key, "")
        if not value:
            continue
        match = CN_DATE_RE.fullmatch(value)
        if not match:
            continue
        try:
            parsed_dates[key] = datetime(*(int(part) for part in match.groups()))
        except ValueError:
            errors.append(f"字段 {key} 不是有效日期")
    for start_key, end_key in (("accept_date", "close_date"), ("service_start_date", "service_end_date")):
        if start_key in parsed_dates and end_key in parsed_dates and parsed_dates[end_key] < parsed_dates[start_key]:
            errors.append(f"字段 {end_key} 不得早于 {start_key}")
    return errors


def _four_digit_upper(value: int) -> str:
    digits = "零壹贰叁肆伍陆柒捌玖"
    units = ("仟", "佰", "拾", "")
    chars = f"{value:04d}"
    result = ""
    pending_zero = False
    for char, unit in zip(chars, units):
        digit = int(char)
        if digit == 0:
            if result:
                pending_zero = True
            continue
        if pending_zero:
            result += "零"
            pending_zero = False
        result += digits[digit] + unit
    return result


def rmb_upper(value: str) -> str:
    try:
        amount = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"金额格式不正确：{value}") from exc
    if amount < 0 or amount >= Decimal("10000000000000000"):
        raise ValidationError(f"金额超出支持范围：{value}")

    integer = int(amount)
    fraction = int((amount - integer) * 100)
    if integer == 0:
        integer_text = "零元"
    else:
        groups: list[int] = []
        remaining = integer
        while remaining:
            groups.append(remaining % 10000)
            remaining //= 10000
        group_units = ("", "万", "亿", "兆")
        parts: list[str] = []
        need_zero = False
        for index in range(len(groups) - 1, -1, -1):
            group = groups[index]
            if group == 0:
                if parts:
                    need_zero = True
                continue
            if parts and (need_zero or group < 1000):
                parts.append("零")
            parts.append(_four_digit_upper(group) + group_units[index])
            need_zero = False
        integer_text = "".join(parts) + "元"

    jiao, fen = divmod(fraction, 10)
    digits = "零壹贰叁肆伍陆柒捌玖"
    if not fraction:
        fraction_text = "整"
    else:
        fraction_text = (digits[jiao] + "角" if jiao else "")
        if fen:
            if not jiao and integer:
                fraction_text += "零"
            fraction_text += digits[fen] + "分"
    # BUG-001 修复：模板固定文字已含"人民币"前缀，此处仅返回中文大写金额，避免"人民币 人民币"重复
    return integer_text + fraction_text


def select_templates(manifest: dict, bundle: str | None, template_ids: list[str]) -> list[tuple[str, dict]]:
    templates = manifest.get("templates", {})
    selected_ids: list[str] = []
    if bundle:
        bundles = manifest.get("bundles", {})
        if bundle not in bundles:
            raise ValidationError(f"未知文书包：{bundle}")
        selected_ids.extend(bundles[bundle])
    selected_ids.extend(template_ids)
    selected_ids = list(dict.fromkeys(selected_ids))
    if not selected_ids:
        raise ValidationError("必须指定 --bundle 或 --template")

    selected: list[tuple[str, dict]] = []
    for template_id in selected_ids:
        if template_id not in templates:
            raise ValidationError(f"未知模板标识：{template_id}")
        selected.append((template_id, templates[template_id]))
    return selected


def scan_xml_placeholders(xml_bytes: bytes) -> tuple[set[str], set[str]]:
    doubles: set[str] = set()
    singles: set[str] = set()
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return doubles, singles
    for paragraph in root.xpath(".//w:p", namespaces={"w": W_NS}):
        text = "".join(paragraph.xpath(".//w:t/text()", namespaces={"w": W_NS}))
        doubles.update(PLACEHOLDER_RE.findall(text))
        singles.update(SINGLE_PLACEHOLDER_RE.findall(text))
    return doubles, singles


def template_placeholders(path: Path) -> tuple[set[str], set[str]]:
    placeholders: set[str] = set()
    singles: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.startswith("word/") and name.endswith(".xml"):
                double_found, single_found = scan_xml_placeholders(archive.read(name))
                placeholders.update(double_found)
                singles.update(single_found)
    return placeholders, singles


def validate_selected(data: dict, selected: list[tuple[str, dict]]) -> list[str]:
    errors: list[str] = []
    for template_id, spec in selected:
        path = REFERENCE_DIR / spec["path"]
        if not path.is_file():
            errors.append(f"模板不存在：{template_id} → {path}")
            continue
        resolved_path = path.resolve()
        if REFERENCE_DIR.resolve() not in resolved_path.parents:
            errors.append(f"模板路径越界：{template_id}")
            continue
        allowed_procedures = spec.get("procedures", [])
        if allowed_procedures and data.get("procedure_type") not in allowed_procedures:
            errors.append(
                f"模板 {template_id} 不适用于程序 {data.get('procedure_type')}，允许：{', '.join(allowed_procedures)}"
            )
        placeholders, single_placeholders = template_placeholders(path)
        if single_placeholders:
            errors.append(f"模板 {template_id} 含单花括号占位符：{', '.join(sorted(single_placeholders))}")
        required = set(spec.get("required", [])) | placeholders
        # BUG-E 修复：placeholder_fields（如立案前 case_number）豁免必填校验，由填充阶段补占位文本
        placeholder_fields = set(spec.get("placeholder_fields", []))
        missing = [
            key
            for key in sorted(required)
            if data.get(key) in (None, "") and key not in placeholder_fields
        ]
        if missing:
            errors.append(f"模板 {template_id} 缺少字段：{', '.join(missing)}")
    return errors


def replace_in_paragraph(paragraph, data: dict) -> int:
    text_nodes = paragraph.xpath(".//w:t", namespaces={"w": W_NS})
    if not text_nodes:
        return 0
    text = "".join(node.text or "" for node in text_nodes)
    matches = list(PLACEHOLDER_RE.finditer(text))
    if not matches:
        return 0

    replacements = 0
    for match in reversed(matches):
        key = match.group(1)
        if key not in data or data[key] in (None, ""):
            continue
        value = str(data[key])
        starts: list[int] = []
        offset = 0
        for node in text_nodes:
            starts.append(offset)
            offset += len(node.text or "")

        start_index = next(i for i, start in enumerate(starts) if start <= match.start() < start + len(text_nodes[i].text or ""))
        end_pos = match.end() - 1
        end_index = next(i for i, start in enumerate(starts) if start <= end_pos < start + len(text_nodes[i].text or ""))
        start_node = text_nodes[start_index]
        end_node = text_nodes[end_index]
        start_local = match.start() - starts[start_index]
        end_local = match.end() - starts[end_index]
        prefix = (start_node.text or "")[:start_local]
        suffix = (end_node.text or "")[end_local:]

        if start_index == end_index:
            start_node.text = prefix + value + suffix
        else:
            start_node.text = prefix + value
            for index in range(start_index + 1, end_index):
                text_nodes[index].text = ""
            end_node.text = suffix
        replacements += 1
        text = text[: match.start()] + value + text[match.end() :]
    return replacements


def patch_story_xml(xml_bytes: bytes, data: dict) -> tuple[bytes, int]:
    parser = etree.XMLParser(resolve_entities=False, remove_blank_text=False)
    root = etree.fromstring(xml_bytes, parser=parser)
    count = 0
    for paragraph in root.xpath(".//w:p", namespaces={"w": W_NS}):
        count += replace_in_paragraph(paragraph, data)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True), count


def set_core_properties(xml_bytes: bytes, title: str) -> bytes:
    parser = etree.XMLParser(resolve_entities=False, remove_blank_text=False)
    root = etree.fromstring(xml_bytes, parser=parser)

    def set_value(namespace: str, local_name: str, value: str) -> None:
        tag = f"{{{namespace}}}{local_name}"
        node = root.find(tag)
        if node is None:
            node = etree.SubElement(root, tag)
        node.text = value

    set_value(DC_NS, "creator", AUTHOR)
    set_value(CORE_NS, "lastModifiedBy", AUTHOR)
    set_value(DC_NS, "title", title)
    set_value(DC_NS, "subject", "中国律师程序文书")
    set_value(CORE_NS, "category", "AIOffice职场通关法律Skill")
    set_value(DC_NS, "description", COMMENT)
    modified = root.find(f"{{{DCTERMS_NS}}}modified")
    if modified is None:
        modified = etree.SubElement(root, f"{{{DCTERMS_NS}}}modified")
    modified.set(f"{{{XSI_NS}}}type", "dcterms:W3CDTF")
    modified.text = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def unresolved_placeholders(zip_data: dict[str, bytes]) -> tuple[list[str], list[str]]:
    unresolved: set[str] = set()
    singles: set[str] = set()
    for name, content in zip_data.items():
        if name.startswith("word/") and name.endswith(".xml"):
            double_found, single_found = scan_xml_placeholders(content)
            unresolved.update(double_found)
            singles.update(single_found)
    return sorted(unresolved), sorted(singles)


def load_brand_module():
    """加载 cn-legal-core 品牌模块（页眉页脚统一标准 2026-08-10）。"""
    path = Path(__file__).resolve().parent.parent.parent / "cn-legal-core" / "scripts" / "docx_brand.py"
    spec = importlib.util.spec_from_file_location("cn_legal_core_brand", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载品牌模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fill_docx(source: Path, destination: Path, data: dict) -> dict:
    with zipfile.ZipFile(source) as archive:
        zip_data = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}

    replacements = 0
    for name in list(zip_data):
        if name.startswith("word/") and name.endswith(".xml"):
            zip_data[name], count = patch_story_xml(zip_data[name], data)
            replacements += count

    if "docProps/core.xml" not in zip_data:
        raise ValidationError(f"模板缺少核心属性：{source}")
    zip_data["docProps/core.xml"] = set_core_properties(zip_data["docProps/core.xml"], destination.stem)
    unresolved, singles = unresolved_placeholders(zip_data)
    if unresolved or singles:
        names = unresolved + [f"单花括号：{item}" for item in singles]
        raise ValidationError(f"生成后仍有未替换字段：{', '.join(names)}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(zip_data.items()):
            archive.writestr(name, content)

    # 2026-08-10 页眉页脚统一标准：Logo 左上 + 二维码右上 + 页脚仅页码（品牌化后重算哈希）
    brand = load_brand_module()
    raw_path = destination.with_name(destination.stem + ".unbranded.docx")
    os.replace(destination, raw_path)
    try:
        brand.brand_docx(raw_path, destination, title=destination.stem,
                         subject="中国律师程序文书", compact=True)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        raw_path.unlink(missing_ok=True)

    try:
        source_label = str(source.relative_to(REFERENCE_DIR))
    except ValueError:
        source_label = str(source)
    return {
        "file": destination.name,
        "source": source_label,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "replacements": replacements,
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    }


def safe_filename(template_id: str, data: dict) -> str:
    parts = [template_id, str(data.get("client_name", "")), str(data.get("case_cause", ""))]
    cleaned = [INVALID_FILENAME_RE.sub("-", part).strip(" .-") for part in parts if part]
    return "-".join(cleaned)[:180] + ".docx"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="确定性填充中国律师程序文书模板")
    parser.add_argument("--data", required=True, type=Path, help="案件 JSON 路径")
    parser.add_argument("--bundle", help="文书包标识")
    parser.add_argument("--template", action="append", default=[], help="单份模板标识，可重复")
    parser.add_argument("--output", required=True, type=Path, help="输出目录")
    parser.add_argument("--check", action="store_true", help="仅校验，不写出 DOCX")
    parser.add_argument("--append", action="store_true", help="追加模式：输出目录可已存在（仅限 --template）")
    args = parser.parse_args(argv)

    try:
        output_path = validate_output_path(args.output)
        loaded_guidance = guidance_records()
        data = load_json(args.data)
        schema = load_json(SCHEMA_PATH)
        manifest = load_json(MANIFEST_PATH)
        selected = select_templates(manifest, args.bundle, args.template)
        errors = validate_schema(data, schema) + validate_selected(data, selected)
        if errors:
            raise ValidationError("\n".join(f"- {item}" for item in errors))

        print(f"校验通过：{len(selected)} 份模板")
        for template_id, spec in selected:
            print(f"  - {template_id}：{spec['path']}")
        if args.check:
            return 0

        # BUG-007：--append 仅限 --template 单份模式，允许输出到已存在目录（同名冲突仍拒绝）
        append_mode = args.append and not args.bundle
        if output_path.exists() and not append_mode:
            raise ValidationError(f"为防止覆盖，输出目录必须不存在：{output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{output_path.name}-", dir=output_path.parent))
        records = []
        try:
            for template_id, spec in selected:
                source = REFERENCE_DIR / spec["path"]
                destination = staging / safe_filename(template_id, data)
                fill_data = deepcopy(data)
                # BUG-008：立案前无案号等场景，placeholder_fields 缺值填占位文本
                for field in spec.get("placeholder_fields", []):
                    if fill_data.get(field) in (None, ""):
                        fill_data[field] = spec.get("case_number_placeholder", "（立案后填写）") if field == "case_number" else "（待填写）"
                records.append(fill_docx(source, destination, fill_data))
                print(f"已生成：{output_path / destination.name}")

            generation_manifest = {
                "manifest_version": manifest["manifest_version"],
                "generator_version": GENERATOR_VERSION,
                "author": AUTHOR,
                "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "schema_version": data["schema_version"],
                "input_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
                "guidance_sources": loaded_guidance,
                "bundle": args.bundle,
                "templates": [template_id for template_id, _ in selected],
                "validation_status": "machine-check-passed-human-review-required",
                "files": records,
            }
            (staging / "generation-manifest.json").write_text(
                json.dumps(generation_manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            if append_mode:
                # BUG-E 修复：--append 合并既有 generation-manifest.json（此前同名冲突抛错且丢失旧记录）
                existing_manifest_path = output_path / "generation-manifest.json"
                if existing_manifest_path.is_file():
                    existing_manifest = load_json(existing_manifest_path)
                    merged = dict(existing_manifest)
                    merged["templates"] = list(dict.fromkeys(
                        list(existing_manifest.get("templates", [])) + generation_manifest["templates"]
                    ))
                    merged["files"] = list(existing_manifest.get("files", [])) + generation_manifest["files"]
                    merged["input_sha256"] = existing_manifest.get(
                        "input_sha256", generation_manifest["input_sha256"]
                    )
                    generation_manifest = merged
                for item in staging.iterdir():
                    if item.name == "generation-manifest.json":
                        continue  # 由合并逻辑统一写入
                    destination = output_path / item.name
                    if destination.exists():
                        raise ValidationError(f"目标已存在同名文件，拒绝覆盖：{destination}")
                    item.rename(destination)
                (output_path / "generation-manifest.json").write_text(
                    json.dumps(generation_manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                shutil.rmtree(staging, ignore_errors=True)
            else:
                os.replace(staging, output_path)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return 0
    except ValidationError as exc:
        print(f"校验失败：\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
