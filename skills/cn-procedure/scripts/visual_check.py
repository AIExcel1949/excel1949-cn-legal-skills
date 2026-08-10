#!/usr/bin/env python3
"""可视化验证脚本：批量转 PDF + PNG，给出页数统计"""
import subprocess
import os
import sys
from pathlib import Path
import zipfile

SKILL_DIR = Path(__file__).resolve().parent.parent
REF_DIR = SKILL_DIR / "references"
PREVIEW_DIR = Path("/tmp/visual_check")
PREVIEW_DIR.mkdir(exist_ok=True)


def get_page_count(pdf_path):
    """从 PDF 提取页数"""
    try:
        result = subprocess.run(
            ['pdfinfo', str(pdf_path)],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split('\n'):
            if 'Pages:' in line:
                return int(line.split(':')[1].strip())
        return -1
    except:
        return -1


def convert_docx(docx_path, output_dir):
    """转 PDF，返回 PDF 路径"""
    cmd = ['soffice', '--headless', '--convert-to', 'pdf',
           str(docx_path), '--outdir', str(output_dir)]
    subprocess.run(cmd, capture_output=True, timeout=30)

    pdf_name = docx_path.stem + ".pdf"
    pdf_path = output_dir / pdf_name
    if not pdf_path.exists():
        return None
    return pdf_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="DOCX 可视化检查：批量转 PDF + 页数统计")
    parser.add_argument("targets", nargs="*", help="相对 references/ 的模板路径，或文件绝对路径")
    parser.add_argument("--path", action="append", default=[], help="目录路径：检查该目录下全部 DOCX（BUG-002 修复）")
    parser.add_argument("--out", default=str(PREVIEW_DIR), help="PDF 输出目录")
    args = parser.parse_args()

    targets = list(args.targets)
    if args.path:
        for directory in args.path:
            root = Path(directory)
            if not root.is_dir():
                print(f"  ❌ 目录不存在: {directory}")
                continue
            targets.extend(str(p) for p in sorted(root.glob("*.docx")))
    if not targets:
        # 默认看 4 个关键文件
        targets = [
            "01-所函/所函（民事）.docx",
            "02-授权委托书/授权委托书（民事-特别授权）.docx",
            "03-委托代理合同/委托代理合同（民事-一般代理）.docx",
            "05-审批表/审批表-收案.docx",
        ]

    preview_dir = Path(args.out)
    preview_dir.mkdir(parents=True, exist_ok=True)
    for target in targets:
        docx_path = Path(target)
        if not docx_path.is_absolute():
            docx_path = REF_DIR / target
        if not docx_path.exists():
            print(f"  ❌ 不存在: {target}")
            continue

        pdf = convert_docx(docx_path, preview_dir)
        if pdf:
            pages = get_page_count(pdf)
            print(f"  📄 {docx_path.name} ({pages} 页)")


if __name__ == '__main__':
    main()
