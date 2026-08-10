#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = ROOT.parent
REGISTRY_PATH = ROOT / "references" / "deliverable-registry.json"
EXPERT_REGISTRY_PATH = ROOT / "references" / "expert-registry.json"
QUALITY_GATES_PATH = ROOT / "references" / "quality-gates.json"
PROCEDURE_MANIFEST_PATH = SKILLS_ROOT / "cn-procedure" / "schemas" / "template-manifest.json"
ROUTES = {"dispute": "cn-dispute", "transaction": "cn-transaction", "compliance": "cn-compliance"}
MANDATORY_SKILLS = ["cn-intake", "cn-legal-core", "cn-research", "cn-verify"]
NORMALIZE_RE = re.compile(r"[\s._·—\-+（）()《》【】\[\]：:]+")


class RouteError(ValueError):
    pass


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RouteError(f"JSON 顶层必须是对象：{path}")
    return value


def load(path: Path) -> dict:
    value = load_json(path)
    Draft202012Validator(load_json(ROOT / "schemas" / "route-input.schema.json")).validate(value)
    return value


def normalize_label(value: str) -> str:
    text = value.strip().lower()
    for suffix in (".docx", "docx", "word文档", "word"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return NORMALIZE_RE.sub("", text)


def load_registry() -> tuple[dict[str, dict], str, str]:
    registry = load_json(REGISTRY_PATH)
    procedure_templates = load_json(PROCEDURE_MANIFEST_PATH).get("templates", {})
    aliases: dict[str, dict] = {}
    for item in registry.get("deliverables", []):
        if not isinstance(item, dict):
            raise RouteError("交付物登记表中存在无效项目")
        skill_name = str(item.get("skill", ""))
        generator = str(item.get("generator", ""))
        if not item.get("variant_required"):
            if not skill_name or not generator:
                raise RouteError(f"交付物缺少 Skill 或生成器：{item.get('id', '未知')}")
            generator_path = SKILLS_ROOT / skill_name / generator
            if not generator_path.is_file():
                raise RouteError(f"登记生成器不存在：{skill_name}/{generator}")
        template_id = item.get("template_id")
        if skill_name == "cn-procedure":
            if not template_id or template_id not in procedure_templates:
                raise RouteError(f"cn-procedure 模板未登记：{template_id or item.get('id', '未知')}")
            template_path = (
                SKILLS_ROOT
                / "cn-procedure"
                / "references"
                / procedure_templates[template_id]["path"]
            )
            if not template_path.is_file():
                raise RouteError(f"cn-procedure 模板文件不存在：{template_id}")
        for alias in item.get("aliases", []):
            key = normalize_label(str(alias))
            if key in aliases:
                raise RouteError(f"交付物别名重复：{alias}")
            aliases[key] = item
    digest = hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest()
    procedure_digest = hashlib.sha256(PROCEDURE_MANIFEST_PATH.read_bytes()).hexdigest()
    return aliases, digest, procedure_digest


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_project_root(path: Path) -> Path:
    if not path.is_absolute():
        raise RouteError("项目根目录必须使用绝对路径")
    resolved = path.resolve(strict=False)
    skills_root = SKILLS_ROOT.resolve()
    if resolved == skills_root or is_relative_to(resolved, skills_root):
        raise RouteError(f"项目根目录不得位于 Skill 安装目录：{resolved}")
    return resolved


def resolve_deliverables(
    value: dict,
    case_root: Path,
) -> tuple[list[dict], list[str], str, str]:
    aliases, registry_sha256, procedure_manifest_sha256 = load_registry()
    delivery_format = value.get("delivery_format", "source_native")
    resolved: list[dict] = []
    blockers: list[str] = []
    seen: set[str] = set()

    for requested in value["requested_outputs"]:
        item = aliases.get(normalize_label(requested))
        if item is None:
            blockers.append(f"unsupported_requested_output:{requested}")
            resolved.append(
                {
                    "requested_output": requested,
                    "deliverable_id": "unregistered",
                    "skill": "",
                    "generator": "",
                    "artifact_kind": "unknown",
                    "delivery_format": delivery_format,
                    "expected_artifacts": [],
                    "output_dir": "",
                    "status": "blocked",
                }
            )
            continue
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        if item.get("variant_required"):
            blockers.append(f"deliverable_variant_required:{item['id']}")
            resolved.append(
                {
                    "requested_output": requested,
                    "deliverable_id": item["id"],
                    "skill": "",
                    "generator": "",
                    "artifact_kind": item["artifact_kind"],
                    "delivery_format": delivery_format,
                    "expected_artifacts": [],
                    "output_dir": "",
                    "status": "blocked",
                    "variant_options": item.get("variant_options", []),
                }
            )
            continue
        status = "ready"
        if delivery_format == "docx" and not item.get("docx_supported", False):
            blockers.append(f"docx_not_supported:{item['id']}")
            status = "blocked"
        output_dir = case_root / item["skill"]
        record = {
            "requested_output": requested,
            "deliverable_id": item["id"],
            "skill": item["skill"],
            "generator": item["generator"],
            "artifact_kind": item["artifact_kind"],
            "delivery_format": "docx" if item.get("docx_supported") else delivery_format,
            "expected_artifacts": item["native_artifacts"],
            "output_dir": str(output_dir),
            "status": status,
        }
        if item.get("template_id"):
            record["template_id"] = item["template_id"]
        # BUG-A/C 修复：透传 DOCX 渲染与交付分类登记字段（渲染步骤/打包步骤依赖）
        for key in ("docx_supported", "render_skill", "renderer", "docx_artifact", "docx_artifacts", "delivery_dir"):
            if item.get(key) is not None:
                record[key] = item[key]
        resolved.append(record)
    return resolved, blockers, registry_sha256, procedure_manifest_sha256


def executor_for(runtime_profile: str, delegated: bool) -> str:
    if not delegated:
        return "main_router"
    return {
        "codex_app": "dynamic_subagent",
        "claude_code": "declared_subagent",
        "openclaw": "runtime_subagent",
        "portable_serial": "main_router",
    }[runtime_profile]


def load_expert_registry() -> tuple[dict, str, str]:
    registry = load_json(EXPERT_REGISTRY_PATH)
    quality_gates = load_json(QUALITY_GATES_PATH)
    digest = hashlib.sha256(EXPERT_REGISTRY_PATH.read_bytes()).hexdigest()
    gates_digest = hashlib.sha256(QUALITY_GATES_PATH.read_bytes()).hexdigest()
    return registry, digest, gates_digest


def expert_fields(
    skill_name: str,
    *,
    required_gates_before: list[str],
    produced_gates: list[str],
) -> dict:
    registry, _, _ = load_expert_registry()
    role_id = registry["skill_role_map"].get(skill_name)
    roles = {item["role_id"]: item for item in registry["roles"]}
    if role_id not in roles:
        raise RouteError(f"Skill 未登记专家角色：{skill_name}")
    role = roles[role_id]
    prompt_path = ROOT / "references" / role["prompt_file"]
    if not prompt_path.is_file():
        raise RouteError(f"专家提示文件不存在：{role['prompt_file']}")
    return {
        "role_id": role_id,
        "role_mode": registry["skill_mode_map"][skill_name],
        "spawn_policy": role["spawn_policy"],
        "selected_skills": [skill_name],
        "required_gates_before": required_gates_before,
        "produced_gates": produced_gates,
        "independence_group": role["independence_group"],
        "role_prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
    }


def execution_steps(
    routes: list[str],
    deliverables: list[dict],
    case_root: Path,
    runtime_profile: str,
) -> list[dict]:
    intake_step = {
            "step_id": "01-intake",
            "skill": "cn-intake",
            "kind": "gate",
            "depends_on": [],
            "output_dir": str(case_root / "cn-intake"),
            "executor": "main_router",
            "allowed_write_root": str(case_root / "cn-intake"),
        }
    intake_step.update(
        expert_fields(
            "cn-intake",
            required_gates_before=[],
            produced_gates=["G0-scope-authority"],
        )
    )
    core_step = {
            "step_id": "02-shared-core",
            "skill": "cn-legal-core",
            "kind": "gate",
            "depends_on": ["01-intake"],
            "output_dir": str(case_root / "cn-legal-core"),
            "executor": "main_router",
            "allowed_write_root": str(case_root / "cn-legal-core"),
        }
    core_step.update(
        expert_fields(
            "cn-legal-core",
            required_gates_before=["G0-scope-authority"],
            produced_gates=[],
        )
    )
    research_step = {
        "step_id": "03-authority-research",
        "skill": "cn-research",
        "kind": "analysis",
        "depends_on": ["01-intake", "02-shared-core"],
        "output_dir": str(case_root / "cn-research"),
        "executor": executor_for(runtime_profile, True),
        "allowed_write_root": str(case_root / "cn-research"),
    }
    research_step.update(
        expert_fields(
            "cn-research",
            required_gates_before=["G0-scope-authority"],
            produced_gates=["G2-authority-applicability"],
        )
    )
    steps: list[dict] = [intake_step, core_step, research_step]
    shared_dependencies = ["01-intake", "02-shared-core", "03-authority-research"]
    if "cn-dispute" in routes:
        facts_step = {
            "step_id": "04-fact-evidence-analysis",
            "skill": "cn-case-analysis",
            "kind": "analysis",
            "depends_on": ["01-intake", "02-shared-core"],
            "output_dir": str(case_root / "cn-case-analysis"),
            "executor": executor_for(runtime_profile, True),
            "allowed_write_root": str(case_root / "cn-case-analysis"),
        }
        facts_step.update(
            expert_fields(
                "cn-case-analysis",
                required_gates_before=["G0-scope-authority"],
                produced_gates=["G1-fact-provenance"],
            )
        )
        steps.append(facts_step)
        shared_dependencies.append("04-fact-evidence-analysis")
    route_step_ids: list[str] = []
    for index, route in enumerate(routes, 1):
        step_id = f"10-route-{index:02d}"
        route_step_ids.append(step_id)
        route_step = {
                "step_id": step_id,
                "skill": route,
                "kind": "child_router",
                "depends_on": shared_dependencies,
                "output_dir": str(case_root / route),
                "executor": executor_for(runtime_profile, True),
                "allowed_write_root": str(case_root / route),
            }
        route_step.update(
            expert_fields(
                route,
                required_gates_before=[
                    "G0-scope-authority",
                    "G2-authority-applicability",
                ] + (["G1-fact-provenance"] if route == "cn-dispute" else []),
                produced_gates=[],
            )
        )
        steps.append(route_step)

    generator_step_ids: list[str] = []
    seen_skills: set[str] = set()
    for index, item in enumerate(deliverables, 1):
        if item["status"] != "ready" or not item["skill"] or item["skill"] in seen_skills:
            continue
        seen_skills.add(item["skill"])
        step_id = f"30-generate-{index:02d}"
        generator_step_ids.append(step_id)
        generator_step = {
                "step_id": step_id,
                "skill": item["skill"],
                "kind": "generator",
                "depends_on": route_step_ids or shared_dependencies,
                "output_dir": item["output_dir"],
                "executor": executor_for(runtime_profile, True),
                "allowed_write_root": item["output_dir"],
                "authorized_deliverable_ids": [
                    record["deliverable_id"]
                    for record in deliverables
                    if record["status"] == "ready" and record["skill"] == item["skill"]
                ],
                "authorized_template_ids": [
                    record["template_id"]
                    for record in deliverables
                    if record["status"] == "ready"
                    and record["skill"] == item["skill"]
                    and record.get("template_id")
                ],
            }
        generator_step.update(
            expert_fields(
                item["skill"],
                required_gates_before=[
                    "G0-scope-authority",
                    "G2-authority-applicability",
                    "G3-lawyer-decision",
                ],
                produced_gates=["G4-deterministic-generation"],
            )
        )
        steps.append(generator_step)

    # BUG-A/B 修复：对 docx_supported 且有登记渲染器的交付物追加渲染步骤（生成 DOCX 成品）
    render_step_ids: list[str] = []
    seen_render: set[str] = set()
    for index, item in enumerate(deliverables, 1):
        if (
            item["status"] != "ready"
            or not item.get("renderer")
            or item["deliverable_id"] in seen_render
        ):
            continue
        seen_render.add(item["deliverable_id"])
        step_id = f"40-render-{index:02d}"
        render_step_ids.append(step_id)
        render_step = {
            "step_id": step_id,
            "skill": item.get("render_skill") or item["skill"],
            "kind": "render",
            "depends_on": generator_step_ids or route_step_ids or shared_dependencies,
            "output_dir": item["output_dir"],
            "executor": "main_router",
            "allowed_write_root": item["output_dir"],
            "authorized_deliverable_ids": [item["deliverable_id"]],
            "renderer": item["renderer"],
            "docx_artifact": item.get("docx_artifact", ""),
        }
        render_step.update(
            expert_fields(
                item.get("render_skill") or item["skill"],
                required_gates_before=["G4-deterministic-generation"],
                produced_gates=[],
            )
        )
        steps.append(render_step)

    # BUG-C 修复：交付打包步骤（收集 DOCX 到 delivery/<中文分类目录>/，剔除中间产物）
    package_step = {
        "step_id": "50-package-delivery",
        "skill": "cn-legal",
        "kind": "package",
        "depends_on": render_step_ids + generator_step_ids or route_step_ids or shared_dependencies,
        "output_dir": str(case_root / "delivery"),
        "executor": "main_router",
        "allowed_write_root": str(case_root / "delivery"),
        "delivery_dirs": {
            item["deliverable_id"]: item.get("delivery_dir", "交付文书")
            for item in deliverables
            if item["status"] == "ready" and item.get("docx_supported")
        },
    }
    package_step.update(
        expert_fields(
            "cn-legal",
            required_gates_before=["G4-deterministic-generation"],
            produced_gates=[],
        )
    )
    steps.append(package_step)

    verify_dependencies = ["50-package-delivery"]
    verify_step = {
            "step_id": "90-verify",
            "skill": "cn-verify",
            "kind": "final_gate",
            "depends_on": verify_dependencies,
            "output_dir": str(case_root / "cn-verify"),
            "executor": executor_for(runtime_profile, True),
            "allowed_write_root": str(case_root / "cn-verify"),
        }
    verify_step.update(
        expert_fields(
            "cn-verify",
            required_gates_before=["G4-deterministic-generation"],
            produced_gates=["G6-independent-review"],
        )
    )
    steps.append(verify_step)
    audit_step = {
            "step_id": "99-delivery-audit",
            "skill": "cn-legal",
            "kind": "orchestrator_audit",
            "depends_on": ["90-verify"],
            "output_dir": str(case_root / "delivery-audit"),
            "executor": "main_router",
            "allowed_write_root": str(case_root / "delivery-audit"),
        }
    audit_step.update(
        expert_fields(
            "cn-legal",
            required_gates_before=["G6-independent-review"],
            produced_gates=[],
        )
    )
    steps.append(audit_step)
    return steps


def build(value: dict, project_root: Path | None = None) -> dict:
    blockers: list[str] = []
    if value["track_status"] != "user_confirmed":
        blockers.append("track_not_user_confirmed")
    tracks = value.get("mixed_tracks", []) if value["track"] == "mixed" else [value["track"]]
    if value["track"] == "unknown":
        blockers.append("track_unknown")
        tracks = []
    if value["track"] == "mixed" and not tracks:
        blockers.append("mixed_tracks_missing")
    routes = [] if blockers else [ROUTES[item] for item in tracks]

    resolved_project_root = (
        validate_project_root(project_root)
        if project_root is not None
        else Path("<PROJECT_ROOT>")
    )
    case_root = resolved_project_root / "output" / "cases" / value["task_id"]
    (
        deliverables,
        deliverable_blockers,
        registry_sha256,
        procedure_manifest_sha256,
    ) = resolve_deliverables(value, case_root)
    blockers.extend(deliverable_blockers)
    escalations = [
        f"urgent_human_escalation:{item}" for item in value["urgent_flags"] if item != "none"
    ]
    runtime_profile = value.get("runtime_profile", "codex_app")
    _, expert_registry_sha256, quality_gates_sha256 = load_expert_registry()
    orchestration_modes = {
        "codex_app": "codex_app_dynamic_experts",
        "claude_code": "claude_code_declared_experts",
        "openclaw": "openclaw_runtime_experts",
        "portable_serial": "main_router_serial",
    }
    result = {
        "schema_version": "2.0",
        "task_id": value["task_id"],
        "project_root": str(resolved_project_root),
        "case_root": str(case_root),
        "routes": routes,
        "domain_pack": load_domain_pack(value.get("case_cause")),
        "domain_guidance": load_domain_guidance(load_domain_pack(value.get("case_cause"))),
        "mandatory_skills": MANDATORY_SKILLS,
        "requested_deliverables": deliverables,
        "execution_steps": execution_steps(routes, deliverables, case_root, runtime_profile),
        "runtime_profile": runtime_profile,
        "orchestration_mode": orchestration_modes[runtime_profile],
        "fallback_mode": "serial_same_plan",
        "control_owner": "cn-legal",
        "deliverable_registry_sha256": registry_sha256,
        "procedure_template_manifest_sha256": procedure_manifest_sha256,
        "expert_registry_sha256": expert_registry_sha256,
        "quality_gates_sha256": quality_gates_sha256,
        "blockers": blockers,
        "escalations": escalations,
        "blocked": bool(blockers),
        "artifact_state": "lawyer_review_required",
    }
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result["plan_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    Draft202012Validator(load_json(ROOT / "schemas" / "route-output.schema.json")).validate(result)
    return result




def load_domain_guidance(pack_name: str | None) -> str | None:
    """读取外置领域知识库包 PACK.md 全文，注入执行计划（知识库外置架构核心链路）。"""
    if not pack_name:
        return None
    candidates = [
        SKILLS_ROOT.parent / "domain-packs" / pack_name / "PACK.md",
        ROOT / "references" / "domain-packs" / pack_name / "PACK.md",
    ]
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return None


def load_domain_pack(case_cause: str | None) -> str | None:
    """按案由关键词匹配领域业务包；未匹配返回 None（非阻断）。"""
    if not case_cause:
        return None
    routing_path = ROOT / "references" / "domain-pack-routing.json"
    if not routing_path.is_file():
        return None
    routing = json.loads(routing_path.read_text(encoding="utf-8"))
    for route in routing.get("routes", []):
        if any(keyword in case_cause for keyword in route.get("keywords", [])):
            return route["pack"]
    return None


def validate_output_path(path: Path) -> Path:
    if not path.is_absolute():
        raise RouteError("路由计划输出路径必须使用绝对路径")
    resolved = path.resolve(strict=False)
    skills_root = SKILLS_ROOT.resolve()
    if resolved == skills_root or is_relative_to(resolved, skills_root):
        raise RouteError(f"禁止把路由计划写入 Skill 目录：{resolved}")
    return resolved


def write_new(path: Path, value: dict) -> None:
    path = validate_output_path(path)
    if path.exists():
        raise FileExistsError(f"拒绝覆盖：{path}")
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
    parser = argparse.ArgumentParser(description="生成可审计的中国律师 Skill 执行计划")
    parser.add_argument("input", type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        write_new(args.output, build(load(args.input), args.project_root))
    except (RouteError, FileExistsError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
