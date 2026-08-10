#!/usr/bin/env python3
"""根据显式输入规则计算期限，原子且不覆盖地输出 JSON。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from deadline_lib import InputError, calculate, load_json


def write_new_atomic(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"输出已存在，拒绝覆盖：{path}")
    if not path.parent.is_dir():
        raise FileNotFoundError(f"输出目录不存在：{path.parent}")
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="计算中国法律期限并输出可审计 JSON。")
    parser.add_argument("input", type=Path, help="UTF-8 JSON 输入文件")
    parser.add_argument("--output", required=True, type=Path, help="新建的 JSON 输出路径，不得已存在")
    args = parser.parse_args()
    try:
        data, raw = load_json(args.input)
        result = calculate(data, raw)
        payload = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        write_new_atomic(args.output, payload)
    except (InputError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    blocked = sum(1 for item in result["results"] if item["status"] == "blocked")
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output),
                "deadline_count": len(result["results"]),
                "calculated_count": len(result["results"]) - blocked,
                "blocked_count": blocked,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
