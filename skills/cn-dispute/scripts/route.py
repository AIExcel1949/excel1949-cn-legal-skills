#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, os, tempfile
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
BASE = ["cn-intake", "cn-timeline", "cn-deadline", "cn-case-analysis", "cn-evidence-map", "cn-research"]
SPECIAL = {"arbitration": "cn-arbitration", "mediation": "cn-mediation", "enforcement": "cn-enforcement", "criminal_defense": "cn-criminal-defense", "administrative_litigation": "cn-admin-litigation"}

def schema(name: str) -> dict: return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8")); Draft202012Validator(schema("route-input.schema.json")).validate(value); return value
def build(value: dict) -> dict:
    blockers = []
    if value["dispute_type_status"] != "user_confirmed" or value["dispute_type"] == "unknown": blockers.append("dispute_type_not_confirmed")
    if value["role_status"] != "user_confirmed" or value["role"] == "unknown": blockers.append("role_not_confirmed")
    skills = []
    if not blockers:
        skills = list(BASE)
        kind = value["dispute_type"]
        if kind == "civil_litigation" and value["role"] == "claimant": skills.append("cn-complaint")
        elif kind == "civil_litigation" and value["role"] == "respondent": skills.append("cn-defense")
        elif kind in SPECIAL: skills.append(SPECIAL[kind])
        skills.append("cn-verify")
    result = {"schema_version": "1.0", "task_id": value["task_id"], "skills": skills, "blockers": blockers, "escalations": [f"urgent_human_escalation:{x}" for x in value["urgent_flags"] if x != "none"], "blocked": bool(blockers), "artifact_state": "lawyer_review_required"}
    Draft202012Validator(schema("route-output.schema.json")).validate(result); return result
def write_new(path: Path, value: dict) -> None:
    if path.exists(): raise FileExistsError(f"拒绝覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True); fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream: json.dump(value, stream, ensure_ascii=False, indent=2); stream.write("\n")
        os.replace(temp, path)
    except Exception: Path(temp).unlink(missing_ok=True); raise
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("input", type=Path); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args(); write_new(args.output, build(load(args.input))); return 0
if __name__ == "__main__": raise SystemExit(main())
