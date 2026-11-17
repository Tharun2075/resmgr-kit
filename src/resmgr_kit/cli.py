"""Command line: resmgr-kit gen | test."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, render, runner, spec as specmod


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="resmgr-kit", description=__doc__)
    ap.add_argument("--version", action="version", version=f"resmgr-kit {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="check a spec and write the C sources, build files and tests")
    g.add_argument("spec")
    g.add_argument("-o", "--outdir", help="output folder (default: build/<name>)")

    t = sub.add_parser("test", help="gen, build with qcc, deploy to the target and run the live tests")
    t.add_argument("spec")
    t.add_argument("-o", "--outdir", help="output folder (default: build/<name>)")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "gen":
            spec = specmod.load(args.spec)
            out = Path(args.outdir or Path("build") / spec["name"])
            for p in render.write(spec, out, Path(args.spec).name):
                print(p)
            return 0
        return runner.test(args.spec, args.outdir)
    except specmod.SpecError as e:
        print(f"resmgr-kit: {args.spec}: {e}", file=sys.stderr)
        return 2
    except runner.RunError as e:
        print(f"resmgr-kit: {e}", file=sys.stderr)
        return 1
