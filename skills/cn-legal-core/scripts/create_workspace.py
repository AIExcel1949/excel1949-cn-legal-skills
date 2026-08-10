#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


MATTER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
LEDGERS = (
    "facts",
    "parties",
    "claims",
    "issues",
    "evidence",
    "authorities",
    "deadlines",
    "calculations",
)


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_workspace(output: Path, matter_id: str) -> None:
    if output.exists():
        raise FileExistsError(f"输出目录已存在：{output}")
    if not MATTER_ID.fullmatch(matter_id):
        raise ValueError("matter-id 只能使用字母、数字、点、下划线和连字符，长度为 3—64")

    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    matter = {
        "schema_version": "1.0",
        "matter_id": matter_id,
        "procedure_type": "unknown",
        "stage": "intake",
        "artifact_state": "draft",
        "created_at": created_at,
        "updated_at": created_at,
    }

    parent = output.resolve().parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cn-legal-workspace-", dir=parent) as temp_name:
        temp = Path(temp_name)
        for name in ("sources", "ledgers", "drafts", "outputs", "audit"):
            (temp / name).mkdir()
        (temp / "matter.json").write_text(
            json.dumps(matter, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        for ledger in LEDGERS:
            value = {"schema_version": "1.0", "matter_id": matter_id, "items": []}
            (temp / "ledgers" / f"{ledger}.json").write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        manifest = {
            "matter_id": matter_id,
            "created_at": created_at,
            "matter_sha256": canonical_hash(matter),
            "artifact_state": "draft",
        }
        (temp / "audit" / "workspace-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temp.rename(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="创建中国法律 Skill 统一案件工作区")
    parser.add_argument("--matter-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        build_workspace(args.output, args.matter_id)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] 已创建案件工作区：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

