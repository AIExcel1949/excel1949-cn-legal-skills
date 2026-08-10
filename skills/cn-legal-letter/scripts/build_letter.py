#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,tempfile
from pathlib import Path
from jsonschema import Draft202012Validator,FormatChecker
ROOT=Path(__file__).resolve().parent.parent
def schema(name): return json.loads((ROOT/"schemas"/name).read_text(encoding="utf-8"))
def load(path):
    value=json.loads(path.read_text(encoding="utf-8")); Draft202012Validator(schema("letter-input.schema.json"),format_checker=FormatChecker()).validate(value); return value
def sourced(item): return bool(item.get("source_spans")) or (item.get("user_confirmed") is True and bool(item.get("confirmation_note","").strip()))
def build(value):
    blockers=[]; fact_ids={x["fact_id"] for x in value["facts"]}; authority_ids={x["authority_id"] for x in value["authorities"]}; calc_ids={x["calculation_id"] for x in value["calculations"]}
    for item in value["facts"]:
        if not sourced(item): blockers.append(f"fact_without_provenance:{item['fact_id']}")
    for item in value["authorities"]:
        if not item["full_text_checked"] or item["effect_status"]!="effective": blockers.append(f"authority_not_current_verified:{item['authority_id']}")
    for item in value["calculations"]:
        if not item["lawyer_confirmed"]: blockers.append(f"calculation_not_lawyer_confirmed:{item['calculation_id']}")
    for item in value["demands"]:
        if not sourced(item): blockers.append(f"demand_without_provenance:{item['demand_id']}")
        if set(item["fact_ids"])-fact_ids or set(item["authority_ids"])-authority_ids or set(item["calculation_ids"])-calc_ids: blockers.append(f"demand_dangling_reference:{item['demand_id']}")
    if value["prohibited_content_declared"]: blockers.append("prohibited_content_declared")
    if value["external_action_requested"]: blockers.append("external_action_forbidden")
    result={"schema_version":"1.0","matter_id":value["matter_id"],"draft":{"sender":value["sender"]["text"],"recipient":value["recipient"]["text"],"facts":[x["text"] for x in value["facts"]],"demands":[x["text"] for x in value["demands"]],"delivery_channels":value["delivery_channels"]},"blockers":sorted(set(blockers)),"sent":False,"signed":False,"artifact_state":"lawyer_review_required"}; Draft202012Validator(schema("letter-output.schema.json")).validate(result); return result
def render(value):
    lines=["# 律师函审查底稿","",f"致：{value['draft']['recipient']}","",*value["draft"]["facts"],"","## 要求事项",""]+ [f"{i}. {x}" for i,x in enumerate(value["draft"]["demands"],1)]+["","本底稿未经执业律师逐案核验、签署和用章，不得对外发送。"]
    return "\n".join(lines)+"\n"
def write_dir(path,value):
    if path.exists(): raise FileExistsError(f"拒绝覆盖：{path}")
    path.parent.mkdir(parents=True,exist_ok=True); temp=Path(tempfile.mkdtemp(prefix=f".{path.name}.",dir=path.parent))
    try:
        (temp/"legal-letter.json").write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); (temp/"律师函审查底稿.md").write_text(render(value),encoding="utf-8"); os.replace(temp,path)
    except Exception:
        for item in temp.iterdir(): item.unlink()
        temp.rmdir(); raise
def main():
    p=argparse.ArgumentParser(); p.add_argument("input",type=Path); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); write_dir(a.output,build(load(a.input))); return 0
if __name__=="__main__": raise SystemExit(main())
