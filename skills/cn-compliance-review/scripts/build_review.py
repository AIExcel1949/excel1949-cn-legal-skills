#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,tempfile
from pathlib import Path
from jsonschema import Draft202012Validator,FormatChecker
ROOT=Path(__file__).resolve().parent.parent
def schema(name): return json.loads((ROOT/"schemas"/name).read_text(encoding="utf-8"))
def load(path):
    value=json.loads(path.read_text(encoding="utf-8")); Draft202012Validator(schema("review-input.schema.json"),format_checker=FormatChecker()).validate(value); return value
def build(value):
    blockers=[]; source_ids={x["source_id"] for x in value["sources"]}; authority_ids={x["authority_id"] for x in value["authorities"]}; test_ids={x["test_id"] for x in value["control_tests"]}
    for item in value["authorities"]:
        if not item["full_text_checked"] or item["effect_status"]!="effective": blockers.append(f"authority_not_current_verified:{item['authority_id']}")
    for item in value["control_tests"]:
        if item["result"]!="not_tested" and not item["source_spans"]: blockers.append(f"tested_without_source:{item['test_id']}")
        if any(span["source_id"] not in source_ids for span in item["source_spans"]): blockers.append(f"unknown_source_in_test:{item['test_id']}")
    for item in value["findings"]:
        if not item["source_spans"] or set(item["test_ids"])-test_ids or set(item["authority_ids"])-authority_ids: blockers.append(f"finding_not_traceable:{item['finding_id']}")
        if any(span["source_id"] not in source_ids for span in item["source_spans"]): blockers.append(f"unknown_source_in_finding:{item['finding_id']}")
    if value["external_action_requested"]: blockers.append("external_action_forbidden")
    result={"schema_version":"1.0","review_id":value["review_id"],"summary":{"scope_count":len(value["scope"]),"test_count":len(value["control_tests"]),"finding_count":len(value["findings"]),"not_tested_count":sum(x["result"]=="not_tested" for x in value["control_tests"])},"findings":value["findings"],"blockers":sorted(set(blockers)),"violation_determined":False,"remediation_implemented":False,"external_action_performed":False,"artifact_state":"lawyer_review_required"}; Draft202012Validator(schema("review-output.schema.json")).validate(result); return result
def render(value):
    lines=["# 企业合规差距审查底稿","",f"- 审查编号：{value['review_id']}",f"- 差距候选：{value['summary']['finding_count']}",f"- 未测试项目：{value['summary']['not_tested_count']}","","本报告仅列示待人工确认的差距候选，不自动认定违法，不表示整改已经实施。"]
    return "\n".join(lines)+"\n"
def write_dir(path,value):
    if path.exists(): raise FileExistsError(f"拒绝覆盖：{path}")
    path.parent.mkdir(parents=True,exist_ok=True); temp=Path(tempfile.mkdtemp(prefix=f".{path.name}.",dir=path.parent))
    try:
        (temp/"compliance-review.json").write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); (temp/"企业合规差距审查底稿.md").write_text(render(value),encoding="utf-8"); os.replace(temp,path)
    except Exception:
        for item in temp.iterdir(): item.unlink()
        temp.rmdir(); raise
def main():
    p=argparse.ArgumentParser(); p.add_argument("input",type=Path); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); write_dir(a.output,build(load(a.input))); return 0
if __name__=="__main__": raise SystemExit(main())
