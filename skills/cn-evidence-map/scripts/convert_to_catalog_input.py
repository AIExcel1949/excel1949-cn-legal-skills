#!/usr/bin/env python3
"""Convert a cn-evidence-map product (evidence-map.json) into the
evidence-catalog-input.json consumed by the cn-evidence-catalog renderer
(scripts/render_evidence_catalog.py).

Mapping contract (evidence-map -> catalog-input):

  map.matter_id                     -> matter_id
  map.matrix[].name                 -> items[].title
  map.matrix[].source_file          -> items[].source
  map.matrix[].proof_purposes[].text -> items[].proof_purpose (joined as "1、…；2、…；")
  map.matrix[].source_locations     -> items[].notes (location digest, factual only)

Fields the evidence-map product does not carry (case_title, submitter_role,
submitter, submit_date, case_cause, plaintiff, defendant, volume_note,
items[].form, items[].pages) are left as empty strings / omitted and reported
in the top-level "_conversion_gaps" array.  Nothing is fabricated; those values
may be supplied via CLI options so the renderer receives them verbatim.

Usage:
    python3 convert_to_catalog_input.py \
        --input evidence-map.json \
        --output evidence-catalog-input.json \
        [--case-title "恒固建设与蓝湾置业建设工程施工合同纠纷案"] \
        [--submitter-role 原告] [--submitter 恒固建设] \
        [--submit-date 2026年8月10日] [--case-cause 建设工程施工合同纠纷] \
        [--plaintiff 恒固建设] [--defendant 蓝湾置业] [--volume-note ""]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SUBMITTER_ROLES = ("原告", "被告", "第三人", "申请执行人", "被执行人", "其他")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def format_cn_date(raw: str) -> str:
    """Normalize an ISO date (2026-08-10) to YYYY年M月D日; pass through anything else."""
    if ISO_DATE.match(raw):
        year, month, day = raw.split("-")
        return f"{int(year)}年{int(month)}月{int(day)}日"
    return raw


def build_items(matrix: list[dict], gaps: list[dict]) -> list[dict]:
    """Map matrix rows to catalog items.  Proof purposes join only texts that
    exist in the map; missing ones are reported as gaps, never invented."""
    items = []
    for row in matrix:
        texts = [p.get("text", "").strip() for p in row.get("proof_purposes", []) if p.get("text", "").strip()]
        if not texts:
            gaps.append({
                "item": row.get("evidence_id", ""),
                "field": "proof_purpose",
                "detail": "该证据在证据映射中无已确认证明目的（如 LINK-EF-018 proof_purpose_unconfirmed），待律师核验材料后补充",
            })
        proof_purpose = "；".join(f"{i}、{text}" for i, text in enumerate(texts, 1))

        locations = row.get("source_locations", [])
        paragraphs = sorted({str(loc["paragraph"]) for loc in locations if "paragraph" in loc})
        source_id = row.get("source_id", "")
        notes_parts = []
        if locations:
            digest = f"来源定位：{source_id} 第{'、'.join(paragraphs)}段（共{len(locations)}处引文）" if paragraphs \
                else f"来源定位：{source_id}（共{len(locations)}处引文）"
            notes_parts.append(digest)
        three_nature = row.get("three_nature", {})
        if any(three_nature.get(k) == "unreviewed" for k in ("authenticity", "legality", "relevance")):
            notes_parts.append("三性：真实性/合法性/关联性均未审查（unreviewed）")

        item = {
            "title": row.get("name", "").strip(),
            "proof_purpose": proof_purpose,
        }
        if row.get("source_file"):
            item["source"] = row["source_file"]
        if notes_parts:
            item["notes"] = "；".join(notes_parts)
        items.append(item)
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="evidence-map.json -> evidence-catalog-input.json 转换")
    parser.add_argument("--input", type=Path, required=True, help="cn-evidence-map 产物 evidence-map.json 路径")
    parser.add_argument("--output", type=Path, required=True, help="输出的 evidence-catalog-input.json 路径")
    parser.add_argument("--case-title", default="", help="案件名称（map 未含，建议律师提供）")
    parser.add_argument("--submitter-role", default="", choices=SUBMITTER_ROLES, help="提交人角色：原告/被告/第三人/申请执行人/被执行人/其他")
    parser.add_argument("--submitter", default="", help="提交人（单位或个人名称）")
    parser.add_argument("--submit-date", default="", help="提交时间，格式 YYYY年M月D日（或 ISO 日期自动转换）")
    parser.add_argument("--case-cause", default="", help="案由（格式二目录头部用）")
    parser.add_argument("--plaintiff", default="", help="原告（申请人）")
    parser.add_argument("--defendant", default="", help="被告（被申请人）")
    parser.add_argument("--volume-note", default="", help="证据册说明")
    args = parser.parse_args()

    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"无法读取输入 JSON：{args.input}（{exc}）", file=sys.stderr)
        return 2

    if "matrix" not in data or not isinstance(data.get("matrix"), list):
        print(f"输入不是 evidence-map 产物：缺少 matrix 数组（{args.input}）", file=sys.stderr)
        return 2

    gaps: list[dict] = []
    meta_fields = {
        "case_title": args.case_title,
        "submitter_role": args.submitter_role,
        "submitter": args.submitter,
        "submit_date": format_cn_date(args.submit_date) if args.submit_date else "",
        "case_cause": args.case_cause,
        "plaintiff": args.plaintiff,
        "defendant": args.defendant,
        "volume_note": args.volume_note,
    }
    for field, value in meta_fields.items():
        if not value:
            gaps.append({"field": field, "detail": "evidence-map 产物不含此元数据，缺省留空；请律师经 CLI 参数补填后再渲染"})

    result = {
        "schema_version": "1.0",
        "matter_id": data.get("matter_id", ""),
        "case_title": meta_fields["case_title"],
        "submitter_role": meta_fields["submitter_role"],
        "submitter": meta_fields["submitter"],
        "submit_date": meta_fields["submit_date"],
        "items": build_items(data["matrix"], gaps),
        "case_cause": meta_fields["case_cause"],
        "plaintiff": meta_fields["plaintiff"],
        "defendant": meta_fields["defendant"],
        "volume_note": meta_fields["volume_note"],
        "_conversion_gaps": gaps,
    }
    if not result["matter_id"]:
        gaps.append({"field": "matter_id", "detail": "输入 evidence-map 缺失 matter_id"})

    result["_conversion_gaps"] = gaps
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "output": str(args.output),
        "item_count": len(result["items"]),
        "gap_count": len(gaps),
        "gaps": gaps,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
