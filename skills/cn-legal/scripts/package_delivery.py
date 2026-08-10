#!/usr/bin/env python3
"""交付打包：收集各 Skill 成品 DOCX 到 delivery/<中文分类目录>/，剔除中间产物，生成 delivery-manifest.json。

BUG-C 修复：交付包 = 全部正式 DOCX + 中文序号分类目录；MD/JSON 仅保留在各自 Skill 工作目录（计划展示层）。
用法：
    python3 package_delivery.py --plan <route-plan.json> --output <case_root>/delivery
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="收集各 Skill DOCX 成品到中文分类交付包")
    parser.add_argument("--plan", type=Path, required=True, help="执行计划（00-route-plan-*.json）")
    parser.add_argument("--output", type=Path, required=True, help="交付包目录（必须不存在）")
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    if args.output.exists():
        print(f"[ERROR] 交付包目录已存在，拒绝覆盖：{args.output}", file=sys.stderr)
        return 2

    ready = [d for d in plan.get("requested_deliverables", []) if d.get("status") == "ready"]
    docx_deliverables = [d for d in ready if d.get("docx_supported")]

    if not docx_deliverables:
        print("[ERROR] 计划中没有 DOCX 交付物", file=sys.stderr)
        return 2

    records = []
    missing = []
    for item in docx_deliverables:
        source_dir = Path(item["output_dir"])
        artifact = item.get("docx_artifact") or item.get("deliverable_id") + ".docx"
        delivery_dir = item.get("delivery_dir") or "交付文书"
        # 多产物支持（docx_artifacts 列表，如证据目录三格式）
        if item.get("docx_artifacts"):
            for art in item["docx_artifacts"]:
                src = source_dir / art
                if not src.is_file():
                    missing.append(f"{item['deliverable_id']} 缺少 {art}")
                    continue
                target_dir = args.output / delivery_dir
                target_dir.mkdir(parents=True, exist_ok=True)
                tgt = target_dir / art
                shutil.copy2(src, tgt)
                records.append({
                    "deliverable_id": item["deliverable_id"], "source": str(src),
                    "target": str(tgt), "sha256": sha256(tgt),
                    "skill": item.get("skill", ""), "delivery_dir": delivery_dir,
                })
            continue
        # 查找成品 DOCX：优先精确名，其次目录内唯一 *.docx
        source = source_dir / artifact
        if not source.is_file():
            candidates = sorted(source_dir.glob("*.docx"))
            # 缺省 docx_artifact 时按 deliverable_id 前缀匹配（safe_filename：template_id-客户-案由.docx）
            if len(candidates) == 1:
                source = candidates[0]
            else:
                matched = [c for c in candidates if c.name.startswith((item.get("template_id") or item["deliverable_id"]) + "-")]
                if len(matched) == 1:
                    source = matched[0]
                elif not matched:
                    missing.append(f"{item['deliverable_id']}（{source_dir}）无 DOCX 成品")
                    continue
                else:
                    missing.append(f"{item['deliverable_id']}（{source_dir}）DOCX 不唯一，无法确定成品")
                    continue
        target_dir = args.output / delivery_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        shutil.copy2(source, target)
        records.append({
            "deliverable_id": item["deliverable_id"],
            "source": str(source),
            "target": str(target),
            "sha256": sha256(target),
            "skill": item.get("skill", ""),
            "delivery_dir": delivery_dir,
        })

    manifest = {
        "schema_version": "1.0",
        "task_id": plan.get("task_id"),
        "package_dir": str(args.output),
        "docx_count": len(records),
        "items": records,
        "note": "交付包仅含正式 DOCX；MD/JSON 底稿保留于各 Skill 工作目录，属计划展示层，不进入交付包",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "delivery-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps({"ok": True, "docx_count": len(records), "missing": missing, "manifest": str(args.output / "delivery-manifest.json")}, ensure_ascii=False))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
