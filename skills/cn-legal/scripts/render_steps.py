#!/usr/bin/env python3
"""渲染驱动：按执行计划执行全部 40-render-* 步骤，产出 DOCX 成品。

BUG-A/B 修复的执行环节（main_router 调用）。输入映射按交付物 id 约定：
  - 起诉状/答辩状/上诉状/施工合同：build 产物主 JSON → 各 skill render_docx.py
  - 一审代理词：草稿 Markdown → cn-hearing render_docx.py（--markdown）
  - 证据目录：evidence-map.json → convert_to_catalog_input.py → render_evidence_catalog.py → 复制成品
用法：
    python3 render_steps.py --plan <route-plan.json>
输出：case_root/render-report.json（每项含 SHA-256）；任一项失败则 exit 1。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent  # skills/
PYTHON = sys.executable

# 渲染输入映射：deliverable_id -> (输入文件名, 渲染器输入参数形式)
INPUT_MAP = {
    "civil-complaint": ("complaint.json", "json"),
    "defense-matrix": ("defense.json", "json"),
    "appeal-review": ("appeal-review.json", "json"),
    "construction-contract-draft": ("contract-draft.json", "json"),
    "first-instance-agent-submission": ("一审代理词（草稿）-原告代理人.md", "markdown"),
}
EVIDENCE_CATALOG = "evidence-list"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def render_evidence(output_dir: Path, docx_artifact: str) -> dict:
    """证据目录两步链路：evidence-map.json → catalog-input → 渲染 → 复制成品。"""
    evidence_map = output_dir / "evidence-map.json"
    if not evidence_map.is_file():
        return {"ok": False, "error": f"缺少 evidence-map.json：{evidence_map}"}
    convert = SKILLS_ROOT / "cn-evidence-map" / "scripts" / "convert_to_catalog_input.py"
    renderer = SKILLS_ROOT / "cn-evidence-catalog" / "scripts" / "render_evidence_catalog.py"
    with tempfile.TemporaryDirectory(prefix=".render-evidence-") as tmp:
        tmp_dir = Path(tmp)
        catalog_input = tmp_dir / "evidence-catalog-input.json"
        code, out = run([PYTHON, str(convert), "--input", str(evidence_map), "--output", str(catalog_input)])
        if code != 0:
            return {"ok": False, "error": f"转换失败：{out[-800:]}"}
        code, out = run([
            PYTHON, str(renderer), "--input", str(catalog_input),
            "--output", str(tmp_dir / "out"),
        ])
        if code != 0:
            return {"ok": False, "error": f"渲染失败：{out[-800:]}"}
        # 三种格式全量交付：证据清单（表格）/证据目录（表格）/证据目录-叙述式
        rendered_files = sorted((tmp_dir / "out").glob("*.docx"))
        if not rendered_files:
            return {"ok": False, "error": "渲染未产出 DOCX"}
        copied = []
        for rendered in rendered_files:
            target = output_dir / rendered.name
            if target.exists():
                return {"ok": False, "error": f"拒绝覆盖：{target}"}
            shutil.copy2(rendered, target)
            copied.append({"file": rendered.name, "sha256": sha256(target)})
    return {"ok": True, "files": copied}


def main() -> int:
    parser = argparse.ArgumentParser(description="执行计划中全部渲染步骤")
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    case_root = Path(plan["case_root"])
    deliverables = {d["deliverable_id"]: d for d in plan.get("requested_deliverables", [])}
    results: list[dict] = []
    failed = 0

    for step in plan.get("execution_steps", []):
        if step.get("kind") != "render":
            continue
        deliverable_id = (step.get("authorized_deliverable_ids") or [""])[0]
        item = deliverables.get(deliverable_id)
        if item is None:
            results.append({"deliverable_id": deliverable_id, "ok": False, "error": "计划中无此交付物"})
            failed += 1
            continue
        output_dir = Path(item["output_dir"])
        docx_artifact = item.get("docx_artifact") or (deliverable_id + ".docx")
        target = output_dir / docx_artifact

        record = {"deliverable_id": deliverable_id, "skill": step.get("skill"), "renderer": step.get("renderer"), "docx_artifact": docx_artifact}

        if deliverable_id == EVIDENCE_CATALOG:
            result = render_evidence(output_dir, docx_artifact)
            record.update(result)
            if not result.get("ok"):
                failed += 1
        else:
            input_name, kind = INPUT_MAP.get(deliverable_id, (None, None))
            if input_name is None:
                record.update({"ok": False, "error": f"未登记输入映射：{deliverable_id}"})
                failed += 1
                results.append(record)
                continue
            source = output_dir / input_name
            if not source.is_file():
                record.update({"ok": False, "error": f"缺少渲染输入：{source}"})
                failed += 1
                results.append(record)
                continue
            renderer = SKILLS_ROOT / step["skill"] / step["renderer"]
            if not renderer.is_file():
                record.update({"ok": False, "error": f"渲染器不存在：{renderer}"})
                failed += 1
                results.append(record)
                continue
            cmd = [PYTHON, str(renderer), "--output", str(target)]
            if kind == "json":
                cmd += ["--input", str(source)]
            else:
                cmd += ["--markdown", str(source)]
            code, out = run(cmd)
            if code != 0:
                record.update({"ok": False, "error": out[-800:]})
                failed += 1
            elif not target.is_file():
                record.update({"ok": False, "error": f"渲染器未产出文件：{target}"})
                failed += 1
            else:
                record.update({"ok": True, "output": str(target), "sha256": sha256(target)})
        results.append(record)

    report = {
        "schema_version": "1.0",
        "task_id": plan.get("task_id"),
        "total": len(results),
        "failed": failed,
        "results": results,
    }
    report_path = case_root / "render-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": failed == 0, "total": len(results), "failed": failed, "report": str(report_path)}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
