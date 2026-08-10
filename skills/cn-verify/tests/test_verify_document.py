from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_ROOT / "scripts" / "verify_document.py"
EXAMPLE = SKILL_ROOT / "examples" / "verify-input.example.json"


class VerifyDocumentTests(unittest.TestCase):
    def run_script(self, input_path: Path, output_dir: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(input_path), "--output-dir", str(output_dir)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_example_reports_blockers_and_masks_sensitive_data(self) -> None:
        original = EXAMPLE.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "review"
            result = self.run_script(EXAMPLE, output)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads((output / "review-report.json").read_text(encoding="utf-8"))
            markdown = (output / "review-report.md").read_text(encoding="utf-8")
            self.assertEqual(report["state"], "blocked")
            self.assertGreater(report["summary"]["blocker"], 0)
            self.assertGreater(report["summary"]["warning"], 0)
            self.assertEqual(len(report["disclaimers"]), 5)
            codes = {item["code"] for item in report["findings"]}
            self.assertIn("PRIVACY.SENSITIVE_DATA", codes)
            self.assertIn("NUMBER.RECALC_MISMATCH", codes)
            self.assertIn("EVIDENCE.FACT_GAP", codes)
            self.assertIn("CONFIRMATION.PENDING", codes)
            serialized = json.dumps(report, ensure_ascii=False) + markdown
            self.assertNotIn("110101199001010010", serialized)
            self.assertNotIn("13800138000", serialized)
            self.assertNotIn("case@example.invalid", serialized)
            self.assertEqual(EXAMPLE.read_bytes(), original)

    def test_clean_input_is_deterministic_and_machine_checked(self) -> None:
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        text = "民事起诉状\n原告：张某某。\n诉讼请求：判令被告支付借款本金人民币100000元。\n事实与理由：2025年1月2日，原告向被告交付借款。\n借款人应当按照约定的期限返还借款。\n"
        data["artifact"]["text"] = text
        data["artifact"]["text_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        data["review_context"]["privacy_mode"] = "external_public"
        data["facts"][0]["evidence_required"] = False
        data["authorities"][0]["record"]["verified_at"] = "2026-07-01T09:00:00+08:00"
        data["calculations"][0]["recalculated_value"] = 100000
        data["consistency_checks"][0]["right_value"] = 100000
        data["human_confirmations"][0].update(
            {
                "status": "confirmed",
                "confirmed_by": "承办律师甲",
                "confirmed_at": "2026-07-18T08:50:00+08:00",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            input_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            first = root / "first"
            second = root / "second"
            first_result = self.run_script(input_path, first)
            second_result = self.run_script(input_path, second)
            self.assertEqual(first_result.returncode, 0, first_result.stderr)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            first_json = (first / "review-report.json").read_bytes()
            second_json = (second / "review-report.json").read_bytes()
            self.assertEqual(first_json, second_json)
            report = json.loads(first_json)
            self.assertEqual(report["state"], "machine_checked")
            self.assertEqual(report["summary"]["blocker"], 0)
            self.assertEqual(report["summary"]["warning"], 0)

    def test_existing_output_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "review"
            first = self.run_script(EXAMPLE, output)
            self.assertEqual(first.returncode, 1, first.stderr)
            before = (output / "review-report.json").read_bytes()
            second = self.run_script(EXAMPLE, output)
            self.assertEqual(second.returncode, 2)
            self.assertEqual((output / "review-report.json").read_bytes(), before)

    def test_schema_error_is_auditable_blocker(self) -> None:
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        del data["artifact"]["input_sha256"]
        data["matter_id"] = "*"
        data["review_context"]["review_id"] = "?"
        data["review_context"]["as_of"] = "未知时间"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "invalid.json"
            input_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            output = root / "review"
            result = self.run_script(input_path, output)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads((output / "review-report.json").read_text(encoding="utf-8"))
            self.assertIn("SCHEMA.INVALID", {item["code"] for item in report["findings"]})
            self.assertEqual(report["matter_id"], "MATTER-UNKNOWN")
            self.assertEqual(report["report_id"], "REVIEW-UNKNOWN")


if __name__ == "__main__":
    unittest.main()
