#!/usr/bin/env python3
"""校验期限计算输入，不执行计算。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from deadline_lib import InputError, load_json, validate_input


def main() -> int:
    parser = argparse.ArgumentParser(description="校验中国法律期限计算 JSON 输入。")
    parser.add_argument("input", type=Path, help="UTF-8 JSON 输入文件")
    args = parser.parse_args()
    try:
        data, raw = load_json(args.input)
        validate_input(data)
    except (InputError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "input": str(args.input),
                "bytes": len(raw),
                "matter_id": data["matter_id"],
                "deadline_count": len(data["deadlines"]),
                "calendar_count": len(data["calendars"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
