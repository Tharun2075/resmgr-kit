"""Render a checked spec into C sources, build files and a live pytest file."""

from __future__ import annotations

import re
from pathlib import Path

import jinja2

from .spec import TYPE_LIMITS

_ENV = jinja2.Environment(
    loader=jinja2.PackageLoader("resmgr_kit", "templates"),
    undefined=jinja2.StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    autoescape=False,
)

# Output file name -> template, with {name} filled in.
OUTPUTS = {
    "{name}.c": "resmgr.c.j2",
    "{name}.h": "header.h.j2",
    "{name}_client.c": "client.c.j2",
    "Makefile": "Makefile.j2",
    "{name}.build": "build.j2",
    "{name}.secpol": "secpol.j2",
    "tests/test_{name}.py": "test.py.j2",
}


def _probe(f: dict) -> dict:
    """Values that exercise a field's range checks: one inside, one above, one below."""
    lo, hi = TYPE_LIMITS[f["type"]]
    mid = (f["min"] + f["max"]) // 2
    if mid == f["init"] and f["max"] > f["min"]:
        mid = f["max"] if mid != f["max"] else f["min"]
    return {
        "mid": mid,
        "above": f["max"] + 1 if f["max"] < hi else None,
        "below": f["min"] - 1 if f["min"] > lo else None,
    }


def _notify_steps(spec: dict) -> tuple[str, str]:
    """Python expressions for the notify test: one that moves the field away from
    the trigger value, and one shell command string that sets the trigger value."""
    n = spec["notify"]
    f = spec["fields"][n["field"]]
    away = f["min"] if f["min"] != n["equals"] else f["max"]
    write = spec.get("write")
    if write and write["field"] == n["field"]:
        return (f'sh("echo {away} > " + PATH)', f'"echo {n["equals"]} > " + PATH')
    for d in spec["devctls"]:
        if d["op"] == "set" and d["field"] == n["field"]:
            return (f'sh(CLIENT + " {d["name"]} {away}")', f'CLIENT + " {d["name"]} {n["equals"]}"')
    raise ValueError("notify field has no write or set devctl to trigger it")


def context(spec: dict, spec_file: str) -> dict:
    ctx = {
        "name": spec["name"],
        "NAME": spec["name"].upper(),
        "path": spec["path"],
        "description": spec["description"],
        "buffer_size": spec["buffer_size"],
        # Only safe characters reach the comments in C, make and Python files.
        "spec_file": re.sub(r"[^A-Za-z0-9._-]", "_", spec_file),
        "state": spec["state"],
        "fields": spec["fields"],
        "read": spec["read"],
        "write": spec.get("write"),
        "devctls": spec["devctls"],
        "timer": spec.get("timer"),
        "threads": spec.get("threads"),
        "notify": spec.get("notify"),
        "write_probe": None,
        "notify_reset": "",
        "notify_trigger": "",
    }
    for d in spec["devctls"]:
        if d["op"] == "set":
            d["probe"] = _probe(spec["fields"][d["field"]])
    if ctx["write"]:
        ctx["write_probe"] = _probe(spec["fields"][ctx["write"]["field"]])
    if ctx["notify"]:
        ctx["notify_reset"], ctx["notify_trigger"] = _notify_steps(spec)
    # A command code no devctl uses, sent with no data: the server must say ENOTTY.
    used = {d["code"] for d in spec["devctls"]}
    free = next(c for c in range(255, 0, -1) if c not in used)
    ctx["unknown_dcmd"] = hex((0x05 << 8) | free)
    return ctx


def render(spec: dict, spec_file: str = "spec.yaml") -> dict[str, str]:
    """Return {relative output path: file text}."""
    ctx = context(spec, spec_file)
    return {
        out.format(name=spec["name"]): _ENV.get_template(tpl).render(ctx)
        for out, tpl in OUTPUTS.items()
    }


def write(spec: dict, outdir: str | Path, spec_file: str = "spec.yaml") -> list[Path]:
    outdir = Path(outdir)
    written = []
    for rel, text in render(spec, spec_file).items():
        path = outdir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        written.append(path)
    return written
