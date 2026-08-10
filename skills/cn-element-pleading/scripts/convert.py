#!/usr/bin/env python3
"""传统民事起诉状转要素式核验稿命令行入口。"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

from build_docx import build_output
from common import ConversionError, SUPPORTED_CASE_TYPES, dump_json, load_json
from ingest import build_mapping_skeleton, build_snapshot
from validate_mapping import validate_mapping


def prepare(input_path: Path, output_dir: Path, case_type: str | None) -> None:
    if output_dir.exists():
        raise ConversionError(f"为防止覆盖，工作目录必须不存在：{output_dir}")
    snapshot = build_snapshot(input_path, case_type)
    mapping = build_mapping_skeleton(snapshot)
    report = validate_mapping(snapshot, mapping, require_final=False)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        dump_json(staging / "source-snapshot.json", snapshot)
        dump_json(staging / "element-mapping.json", mapping)
        dump_json(
            staging / "prepare-report.json",
            {
                "classification": snapshot["classification"],
                "mapping_validation": report,
                "next_action": "逐项填充 element-mapping.json，并确认案由与所有未映射片段。",
            },
        )
        os.replace(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def command_validate(snapshot_path: Path, mapping_path: Path, final: bool) -> int:
    snapshot = load_json(snapshot_path)
    mapping = load_json(mapping_path)
    report = validate_mapping(snapshot, mapping, require_final=final)
    print("验证通过" if report["valid"] else "验证失败")
    for item in report["errors"]:
        print(f"错误：{item}")
    for item in report["warnings"]:
        print(f"警告：{item}")
    print(f"统计：{report['counts']}")
    return 0 if report["valid"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="传统民事起诉状转要素式转换核验稿")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="建立源快照和映射骨架")
    prepare_parser.add_argument("--input", required=True, type=Path)
    prepare_parser.add_argument("--output", required=True, type=Path)
    prepare_parser.add_argument("--case-type", choices=SUPPORTED_CASE_TYPES)

    validate_parser = subparsers.add_parser("validate", help="验证来源映射")
    validate_parser.add_argument("--snapshot", required=True, type=Path)
    validate_parser.add_argument("--mapping", required=True, type=Path)
    validate_parser.add_argument("--final", action="store_true", help="按生成前终检门槛验证")

    build_parser = subparsers.add_parser("build", help="生成 DOCX 转换核验稿")
    build_parser.add_argument("--snapshot", required=True, type=Path)
    build_parser.add_argument("--mapping", required=True, type=Path)
    build_parser.add_argument("--output", required=True, type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            prepare(args.input, args.output, args.case_type)
            print(f"已建立工作目录：{args.output}")
            return 0
        if args.command == "validate":
            return command_validate(args.snapshot, args.mapping, args.final)
        snapshot = load_json(args.snapshot)
        mapping = load_json(args.mapping)
        manifest = build_output(snapshot, mapping, args.output)
        print(f"已生成：{args.output / '要素式民事起诉状-转换核验稿.docx'}")
        print(f"状态：{manifest['validation_status']}")
        return 0
    except ConversionError as exc:
        print(f"转换失败：\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
