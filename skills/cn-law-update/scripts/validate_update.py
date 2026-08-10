#!/usr/bin/env python3
"""验证法律更新输入的结构、原文哈希和生产门禁。"""

from __future__ import annotations

import argparse
import json
import sys

from update_core import InputError, gate_checks, load_json_file


def main() -> int:
    parser = argparse.ArgumentParser(description="验证中国法律更新比对 JSON。")
    parser.add_argument("input", help="UTF-8 JSON 输入文件")
    args = parser.parse_args()
    try:
        data = load_json_file(args.input)
        fatal, blockers, warnings = gate_checks(data)
    except InputError as exc:
        print(json.dumps({"ok": False, "fatal_errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2

    result = {
        "ok": not fatal and not blockers,
        "structurally_valid": not fatal,
        "mode": data.get("mode"),
        "fatal_errors": fatal,
        "production_blockers": blockers,
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if fatal:
        return 2
    if blockers:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
