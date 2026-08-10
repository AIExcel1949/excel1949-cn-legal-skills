#!/usr/bin/env python3
"""生成中国法律尽调律师复核底稿。"""

from __future__ import annotations

import argparse
import json
import sys

from diligence_core import InputError, atomic_write_workpaper, build_workpaper, load_json_file


def main() -> int:
    parser = argparse.ArgumentParser(description="生成中国法律尽调律师复核底稿。")
    parser.add_argument("input", help="UTF-8 JSON 输入文件")
    parser.add_argument("--output", required=True, help="必须不存在的输出目录")
    args = parser.parse_args()
    try:
        workpaper = build_workpaper(load_json_file(args.input))
        output = atomic_write_workpaper(workpaper, args.output)
    except (InputError, OSError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "output": str(output), "artifact_state": "lawyer_review_required", "transaction_assessment": "not_performed", "blocker_count": len(workpaper["blockers"])}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
