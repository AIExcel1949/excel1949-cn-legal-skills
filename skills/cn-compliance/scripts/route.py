#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,tempfile
from pathlib import Path
from jsonschema import Draft202012Validator,FormatChecker
ROOT=Path(__file__).resolve().parent.parent
ROUTES={"employment":("cn-employment","labor"),"data_privacy":("cn-data-privacy","data-cyber"),"company":("cn-company","company"),"consumer_advertising":("cn-compliance-review","consumer-advertising"),"competition":("cn-compliance-review","competition"),"general_review":("cn-compliance-review",None)}
def schema(name): return json.loads((ROOT/"schemas"/name).read_text(encoding="utf-8"))
def load(path):
    value=json.loads(path.read_text(encoding="utf-8")); Draft202012Validator(schema("route-input.schema.json"),format_checker=FormatChecker()).validate(value); return value
def build(value):
    blockers=[]
    if value["topic_status"]!="user_confirmed" or value["topic"]=="unknown": blockers.append("topic_not_confirmed")
    skills=[]; packs=[]
    if not blockers:
        skill,pack=ROUTES[value["topic"]]; skills=["cn-intake","cn-legal-core","cn-research",skill,"cn-verify"]; packs=[pack] if pack else []
    result={"schema_version":"1.0","task_id":value["task_id"],"skills":skills,"domain_packs":packs,"blockers":blockers,"blocked":bool(blockers),"artifact_state":"lawyer_review_required"}; Draft202012Validator(schema("route-output.schema.json")).validate(result); return result
def write_new(path,value):
    if path.exists(): raise FileExistsError(f"拒绝覆盖：{path}")
    path.parent.mkdir(parents=True,exist_ok=True); fd,temp=tempfile.mkstemp(prefix=f".{path.name}.",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream: json.dump(value,stream,ensure_ascii=False,indent=2); stream.write("\n")
        os.replace(temp,path)
    except Exception: Path(temp).unlink(missing_ok=True); raise
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("input",type=Path); parser.add_argument("--output",type=Path,required=True); args=parser.parse_args(); write_new(args.output,build(load(args.input))); return 0
if __name__=="__main__": raise SystemExit(main())
