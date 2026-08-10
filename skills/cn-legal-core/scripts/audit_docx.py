#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET


AUTHOR = "AIOffice职场通关-excel1949"
BRAND = "AIOffice职场通关"
CATEGORY = "AIOffice职场通关法律Skill"
COMMENT = "AI辅助生成，须由执业律师逐项核验"
CORE_NS = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
}
APP_NS = {"ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PLACEHOLDER = re.compile(r"\{\{[^{}]+\}\}|\[\[[^\[\]]+\]\]")


def read_text(archive: zipfile.ZipFile, name: str) -> str:
    try:
        return archive.read(name).decode("utf-8", errors="replace")
    except KeyError:
        return ""


def audit(path: Path, forbidden_terms: list[str], allow_placeholders: bool = False) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    details: dict[str, object] = {}
    if not path.is_file() or path.suffix.lower() != ".docx":
        return {"ok": False, "errors": ["文件不存在或不是 DOCX"], "warnings": [], "details": {}}

    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            for name in names:
                pure = PurePosixPath(name)
                if pure.is_absolute() or ".." in pure.parts:
                    errors.append(f"OOXML 路径异常：{name}")

            lower_names = {name.lower() for name in names}
            if any(name.endswith("vbaproject.bin") for name in lower_names):
                errors.append("存在 VBA 宏")
            if any("/embeddings/" in name for name in lower_names):
                errors.append("存在 OLE 或嵌入对象")
            if "word/comments.xml" in lower_names:
                errors.append("存在未处理批注")

            core_xml = read_text(archive, "docProps/core.xml")
            core = ET.fromstring(core_xml)
            creator = core.findtext("dc:creator", default="", namespaces=CORE_NS)
            modifier = core.findtext("cp:lastModifiedBy", default="", namespaces=CORE_NS)
            category = core.findtext("cp:category", default="", namespaces=CORE_NS)
            comment = core.findtext("dc:description", default="", namespaces=CORE_NS)
            details["creator"] = creator
            details["last_modified_by"] = modifier
            details["category"] = category
            details["comment"] = comment
            if creator != AUTHOR:
                errors.append(f"作者属性不合规：{creator or '空'}")
            if modifier != AUTHOR:
                errors.append(f"最后修改者属性不合规：{modifier or '空'}")
            if category != CATEGORY:
                errors.append(f"分类属性不合规：{category or '空'}")
            if comment != COMMENT:
                errors.append(f"备注属性不合规：{comment or '空'}")

            app_xml = read_text(archive, "docProps/app.xml")
            app = ET.fromstring(app_xml)
            company = app.findtext("ep:Company", default="", namespaces=APP_NS)
            details["company"] = company
            if company != BRAND:
                errors.append(f"公司属性不合规：{company or '空'}")

            headers = [name for name in names if re.fullmatch(r"word/header\d+\.xml", name)]
            footers = [name for name in names if re.fullmatch(r"word/footer\d+\.xml", name)]
            details["header_parts"] = headers
            details["footer_parts"] = footers
            if not headers or not all("a:blip" in read_text(archive, name) for name in headers):
                errors.append("页眉缺少 Logo 图片")
            # 2026-08-09 规范：页脚不放内容（去品牌/页码），不再强制检查

            document_xml = read_text(archive, "word/document.xml")
            document_root = ET.fromstring(document_xml)
            if document_root.findall(f".//{{{W_NS}}}ins") or document_root.findall(f".//{{{W_NS}}}del"):
                errors.append("存在未处理修订")
            visible_parts = ["word/document.xml", *headers, *footers]
            visible_text = "\n".join(read_text(archive, name) for name in visible_parts)
            if not allow_placeholders and PLACEHOLDER.search(visible_text):
                errors.append("存在未替换占位符")
            for term in forbidden_terms:
                if term and term in visible_text + core_xml:
                    errors.append(f"发现禁止词：{term}")

            external: list[str] = []
            for name in names:
                if not name.endswith(".rels"):
                    continue
                rel_xml = read_text(archive, name)
                try:
                    root = ET.fromstring(rel_xml)
                except ET.ParseError:
                    errors.append(f"关系文件损坏：{name}")
                    continue
                for rel in root.findall("r:Relationship", REL_NS):
                    if rel.attrib.get("TargetMode") == "External":
                        external.append(f"{name}:{rel.attrib.get('Target', '')}")
            if external:
                errors.append("存在外部关系")
                details["external_relationships"] = external
    except (ET.ParseError, OSError, zipfile.BadZipFile) as exc:
        errors.append(f"DOCX 无法安全读取：{exc}")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "details": details}


def main() -> int:
    parser = argparse.ArgumentParser(description="审计 DOCX 品牌、作者属性和 OOXML 安全")
    parser.add_argument("docx", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--forbidden-term", action="append", default=[])
    parser.add_argument("--allow-placeholders", action="store_true")
    args = parser.parse_args()
    result = audit(args.docx, args.forbidden_term, args.allow_placeholders)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
