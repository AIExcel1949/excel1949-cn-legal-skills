from __future__ import annotations
import importlib.util,json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parent.parent
def mod():
    spec=importlib.util.spec_from_file_location("route",ROOT/"scripts"/"route.py"); assert spec and spec.loader; value=importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value
def sample(): return json.loads((ROOT/"examples"/"route.example.json").read_text(encoding="utf-8"))
def test_data_route():
    result=mod().build(sample()); assert "cn-data-privacy" in result["skills"] and result["domain_packs"]==["data-cyber"]
def test_employment_route():
    value=sample(); value["topic"]="employment"; assert mod().build(value)["domain_packs"]==["labor"]
def test_general_has_no_pack():
    value=sample(); value["topic"]="general_review"; assert mod().build(value)["domain_packs"]==[]
def test_unknown_blocks():
    value=sample(); value["topic"]="unknown"; assert mod().build(value)["blocked"]
def test_refuses_overwrite(tmp_path:Path):
    path=tmp_path/"x"; path.write_text("x",encoding="utf-8")
    with pytest.raises(FileExistsError): mod().write_new(path,mod().build(sample()))
