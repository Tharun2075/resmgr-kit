"""Load and check a resmgr-kit YAML spec."""

from __future__ import annotations

import copy
import json
from importlib import resources
from pathlib import Path

import jsonschema
import yaml

INT32_MIN, INT32_MAX = -(2**31), 2**31 - 1
UINT32_MAX = 2**32 - 1
TYPE_LIMITS = {"int32": (INT32_MIN, INT32_MAX), "uint32": (0, UINT32_MAX)}
CTYPES = {"int32": "int32_t", "uint32": "uint32_t"}


class SpecError(Exception):
    """A spec problem; the message names the field at fault."""


def load_schema() -> dict:
    text = resources.files("resmgr_kit").joinpath("schema.json").read_text()
    return json.loads(text)


def _where(path) -> str:
    out = ""
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out or "(top level)"


def _check_impl(item: dict, where: str) -> None:
    item.setdefault("impl", "template")
    if item["impl"] == "ai" and not item.get("behaviour", "").strip():
        raise SpecError(f"{where}.behaviour: impl 'ai' needs a plain-English behaviour line")


def ai_regions(spec: dict) -> list[str]:
    """Names of the stub regions that `resmgr-kit ai` fills, in file order."""
    names = ["io_write"] if spec.get("write", {}).get("impl") == "ai" else []
    return names + [d["name"] for d in spec["devctls"] if d["impl"] == "ai"]


def validate(data) -> dict:
    """Check data against the schema and the cross-field rules.

    Returns a normalised copy with defaults filled in, or raises SpecError.
    """
    if not isinstance(data, dict):
        raise SpecError("spec: the top level must be a mapping")
    validator = jsonschema.Draft202012Validator(load_schema())
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"{_where(e.absolute_path)}: {e.message}" for e in errors[:10]]
        raise SpecError("spec does not match the schema:\n  " + "\n  ".join(lines))

    spec = copy.deepcopy(data)
    spec.setdefault("buffer_size", 256)
    spec.setdefault("devctls", [])
    spec.setdefault("description", "")

    fields = {}
    for i, f in enumerate(spec["state"]):
        where = f"state[{i}] ({f['name']})"
        if f["name"] in fields:
            raise SpecError(f"{where}: duplicate field name")
        lo, hi = TYPE_LIMITS[f["type"]]
        f.setdefault("min", lo)
        f.setdefault("max", hi)
        f.setdefault("init", max(f["min"], 0) if f["min"] <= 0 <= f["max"] else f["min"])
        f.setdefault("unit", "")
        if not lo <= f["min"] <= hi:
            raise SpecError(f"{where}.min: {f['min']} is outside {f['type']}")
        if not lo <= f["max"] <= hi:
            raise SpecError(f"{where}.max: {f['max']} is outside {f['type']}")
        if f["max"] < f["min"]:
            raise SpecError(f"{where}.max: max ({f['max']}) is below min ({f['min']})")
        if not f["min"] <= f["init"] <= f["max"]:
            raise SpecError(f"{where}.init: {f['init']} is outside {f['min']}..{f['max']}")
        f["ctype"] = CTYPES[f["type"]]
        f["fmt"] = "%d" if f["type"] == "int32" else "%u"
        fields[f["name"]] = f

    def need(name, where):
        if name not in fields:
            raise SpecError(f"{where}: unknown state field '{name}'")
        return fields[name]

    for name in spec["read"]["fields"]:
        need(name, "read.fields")
    if "write" in spec:
        spec["write"].setdefault("out_of_range", "reject")
        _check_impl(spec["write"], "write")
        need(spec["write"]["field"], "write.field")

    codes, names = set(), set()
    for i, d in enumerate(spec["devctls"]):
        where = f"devctls[{i}] ({d['name']})"
        if d["name"] in names:
            raise SpecError(f"{where}.name: duplicate devctl name")
        if d["code"] in codes:
            raise SpecError(f"{where}.code: code {d['code']} is used twice")
        names.add(d["name"])
        codes.add(d["code"])
        d.setdefault("out_of_range", "reject")
        _check_impl(d, where)
        if d["impl"] == "ai" and d["op"] == "notify":
            raise SpecError(f"{where}.impl: impl 'ai' is for set and get devctls only")
        if d["op"] in ("set", "get"):
            if "field" not in d:
                raise SpecError(f"{where}.field: op '{d['op']}' needs a field")
            need(d["field"], f"{where}.field")
        elif "notify" not in spec:
            raise SpecError(f"{where}.op: op 'notify' needs a top-level notify section")

    if "threads" in spec:
        t = spec["threads"]
        for key, val in (("lo_water", 2), ("hi_water", 4), ("increment", 1), ("maximum", 8)):
            t.setdefault(key, val)
        if not t["lo_water"] <= t["hi_water"] <= t["maximum"]:
            raise SpecError("threads: need lo_water <= hi_water <= maximum")

    if "timer" in spec:
        t = spec["timer"]
        if "rate_field" in t:
            rf = need(t["rate_field"], "timer.rate_field")
            if rf["min"] < 1:
                raise SpecError(f"timer.rate_field: field '{rf['name']}' needs min >= 1 (Hz)")
        for i, a in enumerate(t["actions"]):
            need(a["field"], f"timer.actions[{i}].field")
            a.setdefault("step", 1)
            a.setdefault("amplitude", 1000)
            if a["op"] == "triangle":
                f = fields[a["field"]]
                if f["type"] != "int32" or f["min"] > -a["amplitude"] or f["max"] < a["amplitude"]:
                    raise SpecError(
                        f"timer.actions[{i}].amplitude: field '{a['field']}' must be int32 "
                        f"and hold -{a['amplitude']}..{a['amplitude']}")

    if "notify" in spec:
        n = spec["notify"]
        f = need(n["field"], "notify.field")
        if not f["min"] <= n["equals"] <= f["max"]:
            raise SpecError(f"notify.equals: {n['equals']} is outside {f['min']}..{f['max']}")
        if "count_field" in n:
            need(n["count_field"], "notify.count_field")
        if not any(d["op"] == "notify" for d in spec["devctls"]):
            raise SpecError("notify: add a devctl with op 'notify' so clients can register")

    spec["fields"] = fields
    return spec


def load(path: str | Path) -> dict:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text())
    except OSError as e:
        raise SpecError(f"{path}: {e.strerror}") from None
    except yaml.YAMLError as e:
        raise SpecError(f"{path}: not valid YAML: {e}") from None
    return validate(data)
