#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


SKILL_ROOT = Path(__file__).resolve().parent.parent
CORE_SCHEMAS = SKILL_ROOT.parent / "cn-legal-core" / "schemas"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("输入必须是 JSON 对象")
    return value


def validator(schema_path: Path) -> Draft202012Validator:
    schema = load_json(schema_path)
    registry = Registry()
    for path in list(CORE_SCHEMAS.glob("*.schema.json")) + list((SKILL_ROOT / "schemas").glob("*.schema.json")):
        candidate = load_json(path)
        if candidate.get("$id"):
            registry = registry.with_resource(candidate["$id"], Resource.from_contents(candidate))
    return Draft202012Validator(schema, registry=registry)


def ensure_valid(value: dict[str, Any], schema_path: Path) -> None:
    errors = sorted(validator(schema_path).iter_errors(value), key=lambda item: list(item.absolute_path))
    if errors:
        rendered = "；".join(f"{'.'.join(map(str, error.absolute_path)) or '<root>'}：{error.message}" for error in errors)
        raise ValueError(f"Schema 校验失败：{rendered}")


def build_handoff(
    transcript: dict[str, Any],
    *,
    matter_id: str,
    source_id: str,
    evidence_id: str,
    evidence_name: str,
    audio_file: Path | None,
) -> dict[str, Any]:
    ensure_valid(transcript, SKILL_ROOT / "schemas" / "output.schema.json")
    meta = transcript["meta"]
    segments = transcript["segments"]
    review_status = transcript["review"]["status"]
    expected_hash = meta.get("original_sha256")
    blockers: list[str] = []
    if not expected_hash:
        blockers.append("original_sha256_missing")
        source_hash = "0" * 64
    else:
        source_hash = expected_hash
    if audio_file is None:
        blockers.append("original_audio_not_rechecked")
    else:
        actual_hash = sha256_file(audio_file)
        if expected_hash and actual_hash != expected_hash:
            blockers.append("original_audio_hash_mismatch")
        if not expected_hash:
            source_hash = actual_hash
    if review_status != "已完成逐句回听":
        blockers.append("transcript_review_incomplete")
    flagged_count = sum(
        1
        for segment in segments
        if segment.get("confidence_flag") in {"low", "unintelligible"} or segment.get("flags")
    )
    if flagged_count:
        blockers.append("flagged_segments_pending_review")
    file_name = Path(meta["original_file"]).name
    mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    value = {
        "schema_version": "1.0",
        "matter_id": matter_id,
        "source": {
            "source_id": source_id,
            "file_name": file_name,
            "sha256": source_hash,
            "mime_type": mime_type,
            "acquisition": "user_provided",
            "parse_status": "human_verified" if review_status == "已完成逐句回听" and not flagged_count else "parsed",
        },
        "evidence": {
            "evidence_id": evidence_id,
            "name": evidence_name,
            "source_id": source_id,
            "fact_ids": [],
            "authenticity": "unreviewed",
            "legality": "unreviewed",
            "relevance": "unreviewed",
            "verification_status": "pending",
        },
        "transcript": {
            "segment_count": len(segments),
            "review_status": review_status,
            "flagged_segment_count": flagged_count,
            **({"transcribe_model": meta["transcribe_model"]} if meta.get("transcribe_model") else {}),
        },
        "blockers": list(dict.fromkeys(blockers)),
        "artifact_state": "lawyer_review_required",
    }
    ensure_valid(value, SKILL_ROOT / "schemas" / "evidence-handoff.schema.json")
    return value


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖既有文件：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="把录音转写结果安全交接到统一证据数据层")
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--matter-id", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--evidence-name", required=True)
    parser.add_argument("--audio-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = build_handoff(
        load_json(args.transcript),
        matter_id=args.matter_id,
        source_id=args.source_id,
        evidence_id=args.evidence_id,
        evidence_name=args.evidence_name,
        audio_file=args.audio_file,
    )
    atomic_write(args.output, value)
    print(json.dumps({"ok": True, "output": str(args.output), "blockers": value["blockers"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
