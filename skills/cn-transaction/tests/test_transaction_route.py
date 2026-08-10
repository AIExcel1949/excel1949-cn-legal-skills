from __future__ import annotations
import importlib.util,json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parent.parent
def mod():
    spec=importlib.util.spec_from_file_location("route",ROOT/"scripts"/"route.py"); assert spec and spec.loader; value=importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value
def sample(): return json.loads((ROOT/"examples"/"route.example.json").read_text(encoding="utf-8"))
def test_review_route(): assert "cn-contract-review" in mod().build(sample())["skills"]
def test_ma_route():
    value=sample(); value["task_type"]="ma"; assert "cn-ma" in mod().build(value)["skills"]
def test_unknown_blocks():
    value=sample(); value["task_type"]="unknown"; assert mod().build(value)["blocked"]
def test_unconfirmed_representation_blocks():
    value=sample(); value["representation_status"]="unconfirmed"; assert mod().build(value)["skills"]==[]
def test_refuses_overwrite(tmp_path:Path):
    path=tmp_path/"x"; path.write_text("x",encoding="utf-8")
    with pytest.raises(FileExistsError): mod().write_new(path,mod().build(sample()))
