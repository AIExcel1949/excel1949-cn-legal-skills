#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_ROOT = SKILL_ROOT / "references"
AUTHOR = "AIOffice职场通关-excel1949"
REQUIRED_GUIDANCE = {
    "references/output-contract.md",
    "references/template-catalog.md",
    "references/data-contract.md",
    "references/legal-basis.md",
    "references/judicial-practice-guide.md",
    "references/source-governance.md",
    "schemas/template-manifest.json",
}


def load_core_audit():
    skills_root = Path(__file__).resolve().parent.parent.parent
    path = skills_root / "cn-legal-core" / "scripts" / "audit_docx.py"
    spec = importlib.util.spec_from_file_location("cn_legal_core_audit", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 cn-legal-core DOCX 审计组件")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() == ".docx" else []
    if path.is_dir():
        return sorted(path.rglob("*.docx"))
    return []


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_manifest(directory: Path, docx_paths: list[Path]) -> list[str]:
    errors: list[str] = []
    manifest_path = directory / "generation-manifest.json"
    if not manifest_path.is_file():
        return ["生成目录缺少 generation-manifest.json"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"generation-manifest.json 无法读取：{exc}"]

    if manifest.get("author") != AUTHOR:
        errors.append("生成清单作者不合规")
    if manifest.get("generator_version") != "2.2.0":
        errors.append("生成器版本不是 2.2.0")
    if manifest.get("validation_status") != "machine-check-passed-human-review-required":
        errors.append("生成清单状态不合规")

    guidance = manifest.get("guidance_sources")
    if not isinstance(guidance, list):
        errors.append("生成清单缺少 guidance_sources")
    else:
        records = {
            item.get("path"): item.get("sha256")
            for item in guidance
            if isinstance(item, dict)
        }
        if set(records) != REQUIRED_GUIDANCE:
            errors.append("生成清单记录的强制参考文件集合不完整")
        for relative, digest in records.items():
            source = SKILL_ROOT / relative
            if not source.is_file() or sha256(source) != digest:
                errors.append(f"强制参考文件哈希不匹配：{relative}")

    file_records = manifest.get("files")
    if not isinstance(file_records, list):
        return errors + ["生成清单缺少 files"]
    recorded_names = {
        item.get("file") for item in file_records
        if isinstance(item, dict) and isinstance(item.get("file"), str)
    }
    actual_names = {path.name for path in docx_paths}
    if recorded_names != actual_names:
        errors.append("生成清单登记的 DOCX 集合与目录实际文件不一致")

    for item in file_records:
        if not isinstance(item, dict):
            errors.append("生成清单 files 中存在无效记录")
            continue
        output = directory / str(item.get("file", ""))
        if not output.is_file() or sha256(output) != item.get("sha256"):
            errors.append(f"生成文件哈希不匹配：{item.get('file', '未知文件')}")
        source_label = item.get("source")
        source = REFERENCE_ROOT / str(source_label or "")
        if (
            not source_label
            or not source.is_file()
            or sha256(source) != item.get("source_sha256")
        ):
            errors.append(f"预设模板来源或哈希不匹配：{source_label or '未记录'}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="审计程序文书 DOCX")
    parser.add_argument("--path", required=True, type=Path)
    parser.add_argument("--expect-placeholders", action="store_true")
    parser.add_argument("--forbidden-term", action="append", default=[])
    args = parser.parse_args()
    paths = collect(args.path)
    if not paths:
        print("未找到 DOCX", file=sys.stderr)
        return 2
    try:
        audit_module = load_core_audit()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    failed = 0
    if args.path.is_dir() and not args.expect_placeholders:
        manifest_errors = audit_manifest(args.path, paths)
        if manifest_errors:
            print("[失败] 生成清单与产物集合")
            for error in manifest_errors:
                print(f"  错误：{error}")
            failed += 1
        else:
            print("[通过] 生成清单与产物集合")
    for path in paths:
        result = audit_module.audit(path, args.forbidden_term, args.expect_placeholders)
        status = "通过" if result["ok"] else "失败"
        print(f"[{status}] {path}")
        for error in result["errors"]:
            print(f"  错误：{error}")
        for warning in result["warnings"]:
            print(f"  警告：{warning}")
        failed += not result["ok"]
    print(f"汇总：{len(paths)} 份，失败 {failed} 份")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
