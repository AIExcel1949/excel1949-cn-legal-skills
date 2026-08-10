#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


DISCLAIMERS = (
    "AI 生成的法律文书仅供学习参考，不得直接用于提交法院或对方当事人。",
    "使用 AI 生成文书前，必须由专业执业律师人工核验事实与法律适用。",
    "AI 不能替代律师对案件具体情况进行独立法律判断。",
    "本课程 AI 仅用于辅助写法律文书，最终法律文书须经专业律师逐案审查与确认。",
    "AI 生成文书质量高低，起决定性因素的是使用者自身法律水平的高低。",
)


def load_validator(skill_root: Path) -> object:
    module_path = skill_root / "scripts" / "validate_research.py"
    spec = importlib.util.spec_from_file_location("cn_research_validator", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载检索报告验证器")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def markdown(report: dict[str, Any]) -> str:
    task = report["task"]
    records = {record["record_id"]: record for record in report["records"]}
    lines = [
        "# 中国法律检索核验报告",
        "",
        f"报告编号：{report['report_id']}  ",
        f"检索截止日期：{task['cutoff_date']}  ",
        f"程序：{task.get('procedure', '待确认')}  ",
        f"地域：{task.get('jurisdiction', '待确认')}",
        "",
        "## 一、研究问题",
        "",
    ]
    for question in task["research_questions"]:
        lines.append(f"- {question['question_id']}：{question['question']}")
    lines.extend(["", "## 二、检索日志", ""])
    for item in report["search_log"]:
        lines.append(f"- {item['searched_at']}｜{item['tool']}｜{item['query']}｜{item['status']}")
    lines.extend(["", "## 三、来源记录", ""])
    for record in report["records"]:
        lines.extend(
            [
                f"### {record['record_id']}　{record['title']}",
                "",
                f"- 类型：{record['record_type']}",
                f"- 机关或法院：{record.get('issuing_body_or_court', '待确认')}",
                f"- 文号或案号：{record.get('document_number_or_case_number', '待确认')}",
                f"- 效力状态：{record.get('effect_status', '不适用')}",
                f"- 核验状态：{record['verification_status']}",
                f"- 原文：{record['source_url']}",
                f"- 关联性：{record['relevance']}",
                "",
            ]
        )
        for quote in record.get("exact_quotes", []):
            lines.append(f"- 原文摘录〔{quote['locator']}〕：{quote['quote']}")
        if record.get("differences"):
            lines.append(f"- 主要差异：{'；'.join(record['differences'])}")
        lines.append("")
    lines.extend(["## 四、分问题结论", ""])
    for finding in report["findings"]:
        lines.extend(
            [
                f"### {finding['question_id']}",
                "",
                finding["conclusion"],
                "",
                f"支持来源：{'、'.join(finding['supporting_record_ids'])}",
                f"反方观点或例外：{'；'.join(finding['counterpoints'])}",
                f"可信度：{finding['confidence']}",
                "",
            ]
        )
        for record_id in finding["supporting_record_ids"]:
            if record_id not in records:
                raise ValueError(f"结论引用不存在的来源：{record_id}")
    lines.extend(["## 五、限制与人工复核", ""])
    for item in report["limitations"]:
        lines.append(f"- {item}")
    lines.extend(["", "## 六、对外使用提示", ""])
    for index, item in enumerate(DISCLAIMERS, 1):
        lines.append(f"{index}. {item}")
    return "\n".join(lines) + "\n"


def build_body_docx(text: str, output: Path) -> None:
    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.shared import Pt
    except ImportError as exc:
        raise RuntimeError("缺少 python-docx，请先安装项目依赖") from exc
    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = "Noto Serif CJK SC"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Noto Serif CJK SC")
    normal.font.size = Pt(11)
    for line in text.splitlines():
        if line.startswith("### "):
            document.add_heading(line[4:], level=3)
        elif line.startswith("## "):
            document.add_heading(line[3:], level=2)
        elif line.startswith("# "):
            document.add_heading(line[2:], level=1)
        elif line.startswith("- "):
            document.add_paragraph(line[2:], style="List Bullet")
        elif line:
            document.add_paragraph(line)
        else:
            document.add_paragraph()
    document.save(output)


def build(report_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"输出目录已存在：{output}")
    skill_root = Path(__file__).resolve().parent.parent
    report = json.loads(report_path.read_text(encoding="utf-8"))
    validator = load_validator(skill_root)
    validation = validator.validate(report, skill_root)
    if not validation["ok"]:
        raise ValueError("检索报告未通过验证，不得生成交付稿")
    text = markdown(report)
    core_script = skill_root.parent / "cn-legal-core" / "scripts" / "docx_brand.py"
    if not core_script.is_file():
        raise FileNotFoundError("缺少 cn-legal-core DOCX 品牌组件")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cn-research-", dir=output.parent) as temp_name:
        temp = Path(temp_name)
        markdown_path = temp / "中国法律检索核验报告.md"
        plain_docx = temp / "report-body.docx"
        branded_docx = temp / "中国法律检索核验报告.docx"
        markdown_path.write_text(text, encoding="utf-8")
        build_body_docx(text, plain_docx)
        subprocess.run(
            [
                sys.executable,
                str(core_script),
                str(plain_docx),
                str(branded_docx),
                "--title",
                "中国法律检索核验报告",
                "--subject",
                "中国法规与类案检索核验",
            ],
            check=True,
        )
        plain_docx.unlink()
        (temp / "validation.json").write_text(
            json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temp.rename(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成可回查、带 AIOffice 品牌的中国法律检索报告")
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.report, args.output)
    except (FileExistsError, FileNotFoundError, OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] 已生成检索报告：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
