import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from docx import Document


SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT_PATH = SKILL_DIR / "scripts/fill_templates.py"
SPEC = importlib.util.spec_from_file_location("fill_templates", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
AUDIT_PATH = SKILL_DIR / "scripts/audit_templates.py"
AUDIT_SPEC = importlib.util.spec_from_file_location("audit_templates", AUDIT_PATH)
AUDIT_MODULE = importlib.util.module_from_spec(AUDIT_SPEC)
assert AUDIT_SPEC and AUDIT_SPEC.loader
AUDIT_SPEC.loader.exec_module(AUDIT_MODULE)


class FillTemplatesTest(unittest.TestCase):
    def test_replaces_placeholder_split_across_runs_and_sets_author(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.docx"
            output = Path(temp_dir) / "output.docx"
            doc = Document()
            paragraph = doc.add_paragraph()
            paragraph.add_run("律师：{{law")
            paragraph.add_run("yer_name}}")
            doc.save(source)

            result = MODULE.fill_docx(source, output, {"lawyer_name": "张某某"})
            self.assertEqual(result["replacements"], 1)
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")
                core_xml = archive.read("docProps/core.xml").decode("utf-8")
            self.assertIn("张某某", document_xml)
            self.assertNotIn("{{", document_xml)
            self.assertIn(MODULE.AUTHOR, core_xml)

    def test_missing_required_field_is_rejected(self):
        data = json.loads((SKILL_DIR / "examples/case-data.example.json").read_text(encoding="utf-8"))
        data["authorization_scope_text"] = ""
        manifest = MODULE.load_json(SKILL_DIR / "schemas/template-manifest.json")
        selected = MODULE.select_templates(manifest, None, ["civil-power-attorney"])
        errors = MODULE.validate_selected(data, selected)
        self.assertTrue(any("authorization_scope_text" in error for error in errors))

    def test_amount_uppercase_must_match(self):
        self.assertEqual(MODULE.rmb_upper("20000.00"), "贰万元整")  # BUG-001：模板固定前缀"人民币"，校验值不含前缀
        data = MODULE.load_json(SKILL_DIR / "examples/case-data.example.json")
        data["fee_amount_cn"] = "壹万元整"
        schema = MODULE.load_json(SKILL_DIR / "schemas/case-data.schema.json")
        errors = MODULE.validate_schema(data, schema)
        self.assertTrue(any("fee_amount_cn" in error for error in errors))

    def test_procedure_mismatch_is_rejected(self):
        data = MODULE.load_json(SKILL_DIR / "examples/case-data.example.json")
        data["procedure_type"] = "criminal"
        manifest = MODULE.load_json(SKILL_DIR / "schemas/template-manifest.json")
        selected = MODULE.select_templates(manifest, None, ["civil-power-attorney"])
        errors = MODULE.validate_selected(data, selected)
        self.assertTrue(any("不适用于程序" in error for error in errors))

    def test_invalid_calendar_date_is_rejected(self):
        data = MODULE.load_json(SKILL_DIR / "examples/case-data.example.json")
        data["sign_date"] = "2026 年 2 月 30 日"
        schema = MODULE.load_json(SKILL_DIR / "schemas/case-data.schema.json")
        errors = MODULE.validate_schema(data, schema)
        self.assertTrue(any("不是有效日期" in error for error in errors))

    def test_relative_output_path_is_rejected(self):
        with self.assertRaises(MODULE.ValidationError):
            MODULE.validate_output_path(Path("output/cases/MATTER-001/cn-procedure"))

    def test_skill_directory_output_is_rejected(self):
        with self.assertRaises(MODULE.ValidationError):
            MODULE.validate_output_path(SKILL_DIR / "runtime-output")

    def test_end_to_end_output_uses_registered_template_and_passes_audit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "cn-procedure"
            result = MODULE.main(
                [
                    "--data",
                    str(SKILL_DIR / "examples/case-data.example.json"),
                    "--template",
                    "civil-power-attorney",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(result, 0)
            docx_files = sorted(output.glob("*.docx"))
            self.assertEqual(len(docx_files), 1)
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {docx_files[0].name, "generation-manifest.json"},
            )

            manifest = json.loads(
                (output / "generation-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["generator_version"], "2.2.0")
            self.assertEqual(
                {item["path"] for item in manifest["guidance_sources"]},
                AUDIT_MODULE.REQUIRED_GUIDANCE,
            )
            self.assertEqual(AUDIT_MODULE.audit_manifest(output, docx_files), [])
            core_audit = AUDIT_MODULE.load_core_audit()
            self.assertTrue(core_audit.audit(docx_files[0], [])["ok"])

    def test_organization_employee_and_preservation_templates_generate(self):
        cases = (
            (
                "organization-employee-case-data.example.json",
                [
                    "civil-organization-employee-power-attorney",
                    "legal-representative-certificate",
                    "organization-employee-certificate",
                ],
            ),
            (
                "property-preservation-case-data.example.json",
                ["property-preservation-application"],
            ),
        )
        for example_name, template_ids in cases:
            with self.subTest(example=example_name), tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "cn-procedure"
                arguments = [
                    "--data",
                    str(SKILL_DIR / "examples" / example_name),
                    "--output",
                    str(output),
                ]
                for template_id in template_ids:
                    arguments.extend(["--template", template_id])
                self.assertEqual(MODULE.main(arguments), 0)
                docx_files = sorted(output.glob("*.docx"))
                self.assertEqual(len(docx_files), len(template_ids))
                self.assertEqual(AUDIT_MODULE.audit_manifest(output, docx_files), [])
                core_audit = AUDIT_MODULE.load_core_audit()
                self.assertTrue(all(core_audit.audit(path, [])["ok"] for path in docx_files))


if __name__ == "__main__":
    unittest.main()
