"""Spec checks: schema errors and cross-field rules name the field at fault."""
import copy

import pytest
import yaml

from resmgr_kit import cli, spec as specmod

BASE = {
    "name": "demo",
    "path": "/dev/demo0",
    "state": [{"name": "rate", "type": "uint32", "min": 1, "max": 100, "init": 10}],
    "read": {"fields": ["rate"]},
    "devctls": [{"name": "SET_RATE", "code": 1, "op": "set", "field": "rate"}],
}


def bad(**changes):
    data = copy.deepcopy(BASE)
    for key, value in changes.items():
        data[key] = value
    return data


def test_examples_load(example):
    spec = specmod.load(example)
    assert spec["name"] == example.stem


def test_defaults_filled():
    spec = specmod.validate(copy.deepcopy(BASE))
    assert spec["buffer_size"] == 256
    assert spec["devctls"][0]["out_of_range"] == "reject"


def test_max_below_min_names_field():
    data = bad(state=[{"name": "rate", "type": "uint32", "min": 10, "max": 5}])
    with pytest.raises(specmod.SpecError, match=r"state\[0\] \(rate\)\.max"):
        specmod.validate(data)


@pytest.mark.parametrize("data, where", [
    (bad(name="9bad"), "name"),
    (bad(path="/tmp/x"), "path"),
    (bad(extra=1), "(top level)"),
    (bad(state=[{"name": "rate", "type": "float"}]), "state[0].type"),
    (bad(read={"fields": ["nope"]}), "read.fields"),
    (bad(devctls=[{"name": "A", "code": 1, "op": "set", "field": "rate"},
                  {"name": "B", "code": 1, "op": "get", "field": "rate"}]), "devctls[1] (B).code"),
    (bad(devctls=[{"name": "A", "code": 1, "op": "set"}]), "devctls[0] (A).field"),
    (bad(state=[{"name": "rate", "type": "uint32", "min": -1}]), "state[0] (rate).min"),
    (bad(timer={"period_ms": 10, "rate_field": "rate", "actions": [{"op": "inc", "field": "rate"}]}), "timer"),
    (bad(devctls=[{"name": "ARM", "code": 1, "op": "notify"}]), "devctls[0] (ARM).op"),
])
def test_bad_spec_names_field(data, where):
    with pytest.raises(specmod.SpecError) as err:
        specmod.validate(data)
    assert where in str(err.value)


def test_cli_gen_bad_spec_exits_nonzero(tmp_path, capsys):
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(bad(state=[{"name": "rate", "type": "uint32", "min": 10, "max": 5}])))
    assert cli.main(["gen", str(path), "-o", str(tmp_path / "out")]) == 2
    assert "rate" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_yaml_is_loaded_safely(tmp_path):
    path = tmp_path / "evil.yaml"
    path.write_text("!!python/object/apply:os.system ['true']\n")
    with pytest.raises(specmod.SpecError, match="not valid YAML"):
        specmod.load(path)
