#!/usr/bin/env python3
"""生成不覆盖的 JSON 和 Markdown 计算旁路报告。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from calc_engine import (
    CalcError,
    atomic_write_new,
    calculate_report,
    ensure_distinct_from_input,
    load_json,
    render_markdown,
    serialize_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="确定性计算案件金额、期间、费用与赔偿项目")
    parser.add_argument("input", type=Path, help="输入 JSON 路径")
    parser.add_argument("--json-output", required=True, type=Path, help="新建 JSON 报告路径")
    parser.add_argument("--markdown-output", required=True, type=Path, help="新建 Markdown 报告路径")
    args = parser.parse_args()
    try:
        ensure_distinct_from_input(args.input, [args.json_output, args.markdown_output])
        report = calculate_report(load_json(args.input))
        atomic_write_new(
            {
                args.json_output: serialize_report(report),
                args.markdown_output: render_markdown(report).encode("utf-8"),
            }
        )
    except (CalcError, OSError) as exc:
        print(f"计算失败：{exc}", file=sys.stderr)
        return 1
    print(f"JSON 报告：{args.json_output}")
    print(f"Markdown 报告：{args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
