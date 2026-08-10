from __future__ import annotations
import importlib.util, json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parent.parent
def mod():
    spec=importlib.util.spec_from_file_location("route",ROOT/"scripts"/"route.py"); assert spec and spec.loader; value=importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value
def sample(): return json.loads((ROOT/"examples"/"route.example.json").read_text(encoding="utf-8"))
def test_respondent_routes_to_defense(): assert "cn-defense" in mod().build(sample())["skills"]
def test_claimant_routes_to_complaint():
    value=sample(); value["role"]="claimant"; assert "cn-complaint" in mod().build(value)["skills"]
def test_neutral_does_not_choose_pleading():
    value=sample(); value["role"]="neutral"; result=mod().build(value); assert "cn-complaint" not in result["skills"] and "cn-defense" not in result["skills"]
def test_unknown_is_blocked():
    value=sample(); value["dispute_type"]="unknown"; assert mod().build(value)["blocked"]
def test_refuses_overwrite(tmp_path: Path):
    path=tmp_path/"x.json"; path.write_text("x",encoding="utf-8")
    with pytest.raises(FileExistsError): mod().write_new(path,mod().build(sample()))
