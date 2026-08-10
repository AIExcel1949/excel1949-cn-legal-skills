#!/usr/bin/env python3
"""校验 cn-calc 输入，并在内存中完成计算以捕获算术错误。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from calc_engine import CalcError, calculate_report, load_json


def main() -> int:
    parser = argparse.ArgumentParser(description="校验中国律师案件计算输入")
    parser.add_argument("input", type=Path, help="输入 JSON 路径")
    args = parser.parse_args()
    try:
        calculate_report(load_json(args.input))
    except (CalcError, OSError) as exc:
        print(f"校验失败：{exc}", file=sys.stderr)
        return 1
    print("校验通过：结构、来源、公式、币种、期间和舍入规则均可计算。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
