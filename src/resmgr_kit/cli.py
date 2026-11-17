"""Command line: resmgr-kit gen | test | ai | sh."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, ai, render, runner, spec as specmod


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
    t.add_argument("-c", "--config", help="extra settings file (TOML) read after the user config")
    t.add_argument("--secpol", action="store_true",
                   help="secure-mode target: push the generated policy and start with on -T <name>_t")

    a = sub.add_parser("ai", help="let a model write the impl: ai regions, tested live on the target")
    a.add_argument("spec")
    a.add_argument("-o", "--outdir", help="output folder (default: build/<name>)")
    a.add_argument("-c", "--config", help="extra settings file (TOML) read after the user config")
    a.add_argument("--max-iter", type=int, default=3, help="model rounds before giving up (default 3)")
    a.add_argument("--dry-run", action="store_true", help="print the prompt and stop; no network")
    s = sub.add_parser("sh", help="run one shell command on the configured target over ssh")
    s.add_argument("command", help="command line, run by the target shell")
    s.add_argument("-c", "--config", help="extra settings file (TOML) read after the user config")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "gen":
            spec = specmod.load(args.spec)
            out = Path(args.outdir or Path("build") / spec["name"])
            for p in render.write(spec, out, Path(args.spec).name):
                print(p)
            return 0
        if args.cmd == "ai":
            return ai.run(args.spec, args.outdir, args.config, args.max_iter, args.dry_run)
        if args.cmd == "sh":
            return runner.shell(args.command, args.config)
        return runner.test(args.spec, args.outdir, args.config, args.secpol)
    except specmod.SpecError as e:
        print(f"resmgr-kit: {args.spec}: {e}", file=sys.stderr)
        return 2
    except ai.AIError as e:
        print(f"resmgr-kit ai: {e}", file=sys.stderr)
        return 2
    except runner.RunError as e:
        print(f"resmgr-kit: {e}", file=sys.stderr)
        return 1
