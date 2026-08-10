#!/usr/bin/env python3
"""诉状转换器共享常量与安全工具。"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import zipfile
from pathlib import Path, PurePosixPath


SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = SKILL_DIR / "configs"
ASSET_DIR = SKILL_DIR / "assets" / "templates"
AUTHOR = "AIOffice职场通关-excel1949"
GENERATOR_VERSION = "3.0.0"
SUPPORTED_CASE_TYPES = ("private_lending", "divorce", "sales_contract", "traffic_accident")
MAX_INPUT_BYTES = 20 * 1024 * 1024
MAX_ZIP_MEMBERS = 5000
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
SAFE_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ConversionError(ValueError):
    """表示转换数据、源文件或输出不满足安全门禁。"""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConversionError(f"无法读取 JSON：{path}：{exc}") from exc
    if not isinstance(value, dict):
        raise ConversionError(f"JSON 顶层必须是对象：{path}")
    return value


def dump_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def detect_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return "text/plain"
    if suffix == ".md":
        return "text/markdown"
    if suffix == ".docx":
        return SAFE_DOCX_MIME
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def assert_safe_docx(path: Path) -> None:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ConversionError(f"DOCX 超过 {MAX_INPUT_BYTES // 1024 // 1024} MB 限制")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_MEMBERS:
                raise ConversionError("DOCX ZIP 成员数量异常")
            if sum(item.file_size for item in infos) > MAX_UNCOMPRESSED_BYTES:
                raise ConversionError("DOCX 解压后体积异常")
            for item in infos:
                member = PurePosixPath(item.filename)
                if member.is_absolute() or ".." in member.parts:
                    raise ConversionError(f"DOCX 含路径越界成员：{item.filename}")
                lowered = item.filename.lower()
                if lowered.endswith(("vbaproject.bin", ".bin")) or "embeddings/" in lowered:
                    raise ConversionError(f"DOCX 含宏或嵌入对象：{item.filename}")
            for name in archive.namelist():
                if name.endswith(".rels"):
                    xml = archive.read(name).decode("utf-8", errors="ignore")
                    if re.search(r'TargetMode\s*=\s*["\']External["\']', xml, re.I):
                        raise ConversionError(f"DOCX 含外部关系：{name}")
    except zipfile.BadZipFile as exc:
        raise ConversionError("输入不是有效 DOCX") from exc


def normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ").strip()


def field_catalog(case_type: str) -> tuple[dict, list[dict]]:
    catalog = load_json(CONFIG_DIR / "element-fields.json")
    if case_type not in catalog["case_types"]:
        raise ConversionError(f"不支持的案由：{case_type}")
    case_spec = catalog["case_types"][case_type]
    fields = catalog["common"] + case_spec["fields"]
    return case_spec, fields
