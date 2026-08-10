from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def load_module():
    path = ROOT / "scripts" / "export_evidence_record.py"
    spec = importlib.util.spec_from_file_location("evidence_handoff", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def transcript(audio: Path, *, reviewed: bool = False) -> dict:
    return {
        "meta": {
            "recording_time": "2026-07-18 09:00",
            "recording_method": "手机录音",
            "recording_duration": "00:12",
            "original_file": audio.name,
            "original_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
            "transcribe_model": "training-fixture",
        },
        "segments": [{"start": 0, "end": 3, "speaker": "SPEAKER_0", "text": "测试文字。", "confidence_flag": "normal"}],
        "review": {"status": "已完成逐句回听" if reviewed else "未完成逐句回听"},
    }


def test_handoff_keeps_three_characteristics_unreviewed(tmp_path: Path):
    module = load_module()
    audio = tmp_path / "training.mp3"
    audio.write_bytes(b"training-audio")
    value = module.build_handoff(
        transcript(audio, reviewed=True), matter_id="MAT-001", source_id="SRC-001",
        evidence_id="EVD-001", evidence_name="训练录音", audio_file=audio,
    )
    assert value["blockers"] == []
    assert value["source"]["parse_status"] == "human_verified"
    assert value["evidence"]["fact_ids"] == []
    assert value["evidence"]["authenticity"] == "unreviewed"
    assert value["evidence"]["verification_status"] == "pending"


def test_handoff_blocks_without_original_recheck_and_refuses_overwrite(tmp_path: Path):
    module = load_module()
    audio = tmp_path / "training.mp3"
    audio.write_bytes(b"training-audio")
    value = module.build_handoff(
        transcript(audio), matter_id="MAT-001", source_id="SRC-001",
        evidence_id="EVD-001", evidence_name="训练录音", audio_file=None,
    )
    assert "original_audio_not_rechecked" in value["blockers"]
    assert "transcript_review_incomplete" in value["blockers"]
    output = tmp_path / "handoff.json"
    module.atomic_write(output, value)
    with pytest.raises(FileExistsError):
        module.atomic_write(output, value)
