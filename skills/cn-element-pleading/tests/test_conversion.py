from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from docx import Document


SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from build_docx import build_output  # noqa: E402
from common import AUTHOR, load_json  # noqa: E402
from ingest import build_mapping_skeleton, build_snapshot  # noqa: E402
from validate_mapping import validate_mapping  # noqa: E402


EXAMPLE = SKILL_DIR / "examples" / "民间借贷-传统起诉状-脱敏.txt"


def fill_from_quote(mapping: dict, snapshot: dict, field_id: str, quote: str) -> None:
    start = snapshot["normalized_text"].find(quote)
    if start < 0:
        raise AssertionError(f"示例原文中没有摘录：{quote}")
    item = next(value for value in mapping["elements"] if value["field_id"] == field_id)
    item.update(
        {
            "status": "provided",
            "value": quote,
            "source_quote": quote,
            "source_start": start,
            "source_end": start + len(quote),
        }
    )


def complete_example_mapping(snapshot: dict) -> dict:
    mapping = build_mapping_skeleton(snapshot)
    fill_from_quote(mapping, snapshot, "party.plaintiff", "原告：甲某某，男，1988年6月12日出生，住甲省甲市甲区甲路1号，联系电话13800000001。")
    fill_from_quote(mapping, snapshot, "party.defendant", "被告：乙某某，女，1990年3月8日出生，住乙省乙市乙区乙路2号，联系电话13900000002。")
    fill_from_quote(mapping, snapshot, "loan.claim.principal", "判令被告向原告偿还借款本金人民币100000元；")
    fill_from_quote(mapping, snapshot, "loan.claim.interest", "判令被告支付以人民币100000元为基数，自2025年7月1日起至实际清偿之日止的利息；")
    fill_from_quote(mapping, snapshot, "loan.claim.litigation_cost", "本案诉讼费用由被告承担。")
    fill_from_quote(mapping, snapshot, "loan.fact.amount_delivery", "2024年6月1日，被告因资金周转向原告借款人民币100000元，并向原告出具《借条》。")
    fill_from_quote(mapping, snapshot, "loan.fact.delivery_date", "同日，原告通过银行转账向被告交付全部借款。")
    fill_from_quote(mapping, snapshot, "loan.fact.term", "双方约定借款期限至2025年6月30日，未约定借款期内利息。")
    fill_from_quote(mapping, snapshot, "loan.fact.overdue", "借款到期后，被告未归还本金。")
    for item in mapping["unmapped_segments"]:
        item["reviewed"] = True
    return mapping


class ConversionTest(unittest.TestCase):
    def test_prepare_preserves_claims_and_confirms_case(self):
        snapshot = build_snapshot(EXAMPLE, "private_lending")
        mapping = build_mapping_skeleton(snapshot)
        self.assertEqual(snapshot["classification"]["selected"], "private_lending")
        self.assertTrue(mapping["case_type_human_confirmed"])
        self.assertEqual(len(mapping["claims"]), 3)
        self.assertIn("人民币100000元", mapping["claims"][0]["text_verbatim"])

    def test_modified_claim_is_blocked(self):
        snapshot = build_snapshot(EXAMPLE, "private_lending")
        mapping = build_mapping_skeleton(snapshot)
        mapping["claims"][0]["text_verbatim"] = "判令被告偿还人民币200000元；"
        report = validate_mapping(snapshot, mapping)
        self.assertFalse(report["valid"])
        self.assertTrue(any("诉讼请求发生" in item for item in report["errors"]))

    def test_value_without_exact_source_is_blocked(self):
        snapshot = build_snapshot(EXAMPLE, "private_lending")
        mapping = build_mapping_skeleton(snapshot)
        item = next(value for value in mapping["elements"] if value["field_id"] == "loan.fact.rate")
        item.update(status="provided", value="年利率6％", source_quote="年利率6％")
        report = validate_mapping(snapshot, mapping)
        self.assertFalse(report["valid"])
        self.assertTrue(any("无法唯一或准确定位" in error for error in report["errors"]))

    def test_unconfirmed_case_blocks_final_build(self):
        snapshot = build_snapshot(EXAMPLE, "private_lending")
        mapping = complete_example_mapping(snapshot)
        mapping["case_type_human_confirmed"] = False
        report = validate_mapping(snapshot, mapping, require_final=True)
        self.assertFalse(report["valid"])
        self.assertTrue(any("案由尚未" in item for item in report["errors"]))

    def test_end_to_end_build_sets_author_and_roundtrips(self):
        snapshot = build_snapshot(EXAMPLE, "private_lending")
        mapping = complete_example_mapping(snapshot)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            manifest = build_output(snapshot, mapping, output)
            document = Document(output / "要素式民事起诉状-转换核验稿.docx")
            self.assertEqual(document.core_properties.author, AUTHOR)
            self.assertEqual(document.core_properties.last_modified_by, AUTHOR)
            self.assertEqual(manifest["validation_status"], "machine-check-passed-human-review-required")
            report = load_json(output / "转换核验报告.json")
            self.assertTrue(report["valid"])
            self.assertEqual(report["case_type"], "private_lending")


if __name__ == "__main__":
    unittest.main()
