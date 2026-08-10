#!/usr/bin/env python3
"""原子生成法律版本差异和影响报告。"""

from __future__ import annotations

import argparse
import json
import sys

from update_core import InputError, atomic_write_report, build_report, load_json_file


def main() -> int:
    parser = argparse.ArgumentParser(description="生成中国法律更新变更报告。")
    parser.add_argument("input", help="UTF-8 JSON 输入文件")
    parser.add_argument("--output", required=True, help="必须不存在的输出目录")
    args = parser.parse_args()
    try:
        data = load_json_file(args.input)
        report = build_report(data)
        output = atomic_write_report(report, args.output)
    except (InputError, OSError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "ok": True,
                "output": str(output),
                "gate_status": report["gate"]["status"],
                "change_count": report["summary"]["change_count"],
                "affected_artifact_count": report["summary"]["affected_artifact_count"],
                "production_files_modified": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
