#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,tempfile
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parent.parent
ALLOWED={"intake":{"intake","active"},"active":{"active","on_hold","closing"},"on_hold":{"on_hold","active","closing"},"closing":{"closing","active","closed"},"closed":{"closed"}}

def schema(name): return json.loads((ROOT/"schemas"/name).read_text(encoding="utf-8"))
def load(path):
    value=json.loads(path.read_text(encoding="utf-8")); Draft202012Validator(schema("matter-input.schema.json")).validate(value); return value
def control_ok(item): return item["status"]=="confirmed" or (item["status"]=="not_applicable" and bool(item["confirmation_note"].strip()))
def build(value):
    blockers=[]; current=value["current_state"]; requested=value["requested_state"]
    if requested not in ALLOWED[current]: blockers.append("state_transition_not_allowed")
    if current!=requested and not value["transition_confirmed"]: blockers.append("transition_not_human_confirmed")
    if current!=requested and not value["transition_reason"].strip(): blockers.append("transition_reason_missing")
    if current=="intake" and requested=="active":
        for name in ("conflict_check","engagement","fee_arrangement"):
            if not control_ok(value["controls"][name]): blockers.append(f"control_pending:{name}")
    pending=[item["task_id"] for item in value["tasks"] if item["status"]=="pending"]
    if requested=="closed":
        for name in ("final_review","billing_review","archive_checklist","retention_classification"):
            if not control_ok(value["controls"][name]): blockers.append(f"control_pending:{name}")
        if pending: blockers.append("pending_tasks_before_close")
    result={"schema_version":"1.0","matter_id":value["matter_id"],"current_state":current,"requested_state":requested,"proposed_state":requested if not blockers else current,"transition_allowed":not blockers,"blockers":blockers,"pending_tasks":pending,"deadline_ids":value["deadline_ids"],"artifact_ids":value["artifact_ids"],"external_system_updated":False,"materials_deleted":False,"artifact_state":"lawyer_review_required"}
    Draft202012Validator(schema("matter-output.schema.json")).validate(result); return result
def render(value):
    lines=["# 案件生命周期审查", "",f"- 案件编号：{value['matter_id']}",f"- 当前状态：{value['current_state']}",f"- 请求状态：{value['requested_state']}",f"- 可流转：{'是' if value['transition_allowed'] else '否'}","","## 阻断项",""]
    lines.extend(f"- {item}" for item in value["blockers"] or ["无机器阻断；仍须负责人审批。"]); return "\n".join(lines)+"\n"
def write_dir(path,value):
    if path.exists(): raise FileExistsError(f"拒绝覆盖：{path}")
    path.parent.mkdir(parents=True,exist_ok=True); temp=Path(tempfile.mkdtemp(prefix=f".{path.name}.",dir=path.parent))
    try:
        (temp/"matter-snapshot.json").write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); (temp/"案件生命周期审查.md").write_text(render(value),encoding="utf-8"); os.replace(temp,path)
    except Exception:
        for item in temp.iterdir(): item.unlink()
        temp.rmdir(); raise
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("input",type=Path); parser.add_argument("--output",type=Path,required=True); args=parser.parse_args(); write_dir(args.output,build(load(args.input))); return 0
if __name__=="__main__": raise SystemExit(main())
