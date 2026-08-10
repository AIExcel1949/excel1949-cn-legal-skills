"""v3.2 格式化、模板与 FunASR 参数回归测试。"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import format_transcript  # noqa: E402
import verify_transcript  # noqa: E402
from _common.funasr_runner import run_funasr_family  # noqa: E402


def _sample_transcript() -> dict:
    return {
        "text": "测试内容",
        "segments": [
            {
                "start": 1.2,
                "end": 2.5,
                "text": "测试内容",
                "speaker": "SPEAKER_0",
                "avg_logprob": -1.2,
                "no_speech_prob": 0.9,
                "compression_ratio": 2.5,
            }
        ],
    }


def test_minimal_markdown_preserves_low_confidence_text():
    markdown = format_transcript.format_transcript(
        _sample_transcript(),
        {
            "recording_time": "2026 年 7 月 17 日 10:00",
            "recording_method": "手机通话录音",
            "recording_duration": "1 分 00 秒",
            "original_file": "demo.mp3",
            "original_sha256": "a" * 64,
            "case": {"cause": "不应出现", "evidentiary_purpose": "不应出现"},
        },
        "unused.md",
    )
    assert "测试内容" in markdown
    assert "低置信度，须回听" in markdown
    assert "疑似非语音，须回听" in markdown
    assert "三、校核说明" in markdown
    assert "未完成逐句回听" in markdown
    assert "关联案件" not in markdown
    assert "证明目的" not in markdown
    assert "附件说明" not in markdown


def test_speaker_map_accepts_string_value():
    markdown = format_transcript.format_transcript(
        _sample_transcript(),
        {},
        "unused.md",
        speaker_map={"SPEAKER_0": "甲某某"},
    )
    assert "甲某某：测试内容" in markdown


def test_verify_format_accepts_three_sections_and_long_minutes():
    markdown = format_transcript.format_transcript(
        {"segments": [{"start": 6000, "end": 6001, "text": "测试"}]},
        {},
        "unused.md",
    )
    result = verify_transcript.verify_format(markdown)
    messages = [finding["message"] for finding in result["findings"]]
    assert "三段式结构完整" in messages
    assert not any("时间戳格式异常" in message for message in messages)


def test_template_has_brand_header_and_simplified_body():
    from docx import Document

    template = SKILL_DIR / "assets" / "录音文字稿-模板.docx"
    doc = Document(template)
    assert doc.core_properties.author == "AIOffice职场通关-excel1949"
    body_text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    body_text += "\n" + "\n".join(cell.text for table in doc.tables for row in table.rows for cell in row.cells)
    header_xml = doc.sections[0].header._element.xml
    assert "w:drawing" in header_xml
    assert "录音基本信息" in body_text
    assert "校核说明" in body_text
    assert "关联案件" not in body_text
    assert "证明目的" not in body_text
    assert "附件说明" not in body_text
    assert "模板结束" not in body_text


def test_generate_docx_clears_template_placeholders(tmp_path):
    from docx import Document

    output = tmp_path / "output.docx"
    markdown = format_transcript.format_transcript(
        _sample_transcript(),
        {"original_file": "demo.mp3", "original_sha256": "b" * 64},
        "unused.md",
    )
    assert format_transcript.generate_docx(markdown, str(output)) is True
    doc = Document(output)
    assert doc.core_properties.author == "AIOffice职场通关-excel1949"
    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    text += "\n" + "\n".join(cell.text for table in doc.tables for row in table.rows for cell in row.cells)
    assert text.count("录音文字稿") == 1
    assert "【转写内容】" not in text
    assert "demo.mp3" in text
    assert "w:drawing" in doc.sections[0].header._element.xml


def test_funasr_no_diarize_omits_speaker_and_passes_hotword_at_generate(monkeypatch, tmp_path):
    captured: dict = {}

    class FakeModel:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def generate(self, **kwargs):
            captured["generate"] = kwargs
            return [{"sentence_info": [{"start": 0, "end": 1000, "text": "借款", "spk": 0}]}]

    monkeypatch.setitem(sys.modules, "funasr", types.SimpleNamespace(AutoModel=FakeModel))
    result = run_funasr_family(
        input_path="demo.wav",
        output_dir=tmp_path,
        backend_name="paraformer-zh",
        settings={"repo_id": "demo/model", "vad_model": "vad", "punc_model": "punc", "spk_model": "cam++"},
        language="zh",
        initial_prompt="借款，还款",
        diarization_cfg={"enabled": False},
    )
    assert result["exit_code"] == 0
    assert "spk_model" not in captured["init"]
    assert captured["generate"]["hotword"] == "借款，还款"
    data = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))
    assert "speaker" not in data["segments"][0]
    assert not (tmp_path / "transcript_diarized.json").exists()
