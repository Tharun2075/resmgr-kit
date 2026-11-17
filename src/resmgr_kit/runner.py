"""`resmgr-kit test`: build with qcc, deploy over ssh, run the live tests, clean up.

Settings come from, highest first: environment variables, ./resmgr-kit.local.toml,
~/.config/resmgr-kit/config.toml, then the defaults below.

  build_command  RESMGR_KIT_BUILD   shell command, {dir} is the output folder
  target         RESMGR_KIT_TARGET  user@host of the QNX target
  port           RESMGR_KIT_PORT    ssh port
  ssh_key        RESMGR_KIT_SSH_KEY private key file (optional)
  target_start   RESMGR_KIT_TARGET_START  command that boots the target when ssh fails (optional)
  remote_dir     RESMGR_KIT_REMOTE_DIR    where binaries go on the target
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from . import render, spec as specmod

DEFAULTS = {
    "build_command": "make -C {dir}",
    "target": "root@127.0.0.1",
    "port": 2222,
    "ssh_key": "",
    "target_start": "",
    "remote_dir": "/tmp",
}


class RunError(Exception):
    pass


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    for path in (Path.home() / ".config/resmgr-kit/config.toml", Path("resmgr-kit.local.toml")):
        if path.is_file():
            with path.open("rb") as fh:
                cfg.update({k: v for k, v in tomllib.load(fh).items() if k in DEFAULTS})
    for key in DEFAULTS:
        env = "RESMGR_KIT_BUILD" if key == "build_command" else "RESMGR_KIT_" + key.upper()
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    cfg["port"] = int(cfg["port"])
    return cfg


def ssh_args(cfg: dict) -> list[str]:
    args = ["ssh", "-p", str(cfg["port"])]
    if cfg["ssh_key"]:
        args += ["-i", os.path.expanduser(cfg["ssh_key"])]
    for opt in ("StrictHostKeyChecking=no", "UserKnownHostsFile=/dev/null", "LogLevel=ERROR",
                "ConnectTimeout=5", "BatchMode=yes"):
        args += ["-o", opt]
    return args + [cfg["target"]]


def step(msg: str) -> None:
    print(f"== {msg}", flush=True)


def _tail(text: str, n: int = 20) -> str:
    return "\n".join(text.rstrip().splitlines()[-n:])


class Target:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ssh = ssh_args(cfg)

    def run(self, cmd: str, stdin: bytes | None = None, timeout: int = 30, check: bool = True):
        res = subprocess.run(self.ssh + [cmd], input=stdin, capture_output=True, timeout=timeout)
        if check and res.returncode != 0:
            raise RunError(f"target command failed ({res.returncode}): {cmd}\n"
                           + _tail(res.stderr.decode(errors="replace")))
        return res

    def reachable(self) -> bool:
        try:
            return self.run("true", timeout=15, check=False).returncode == 0
        except subprocess.TimeoutExpired:
            return False

    def ensure_up(self) -> None:
        if self.reachable():
            print("target: reachable", flush=True)
            return
        start = self.cfg["target_start"]
        if not start:
            raise RunError("target is not reachable over ssh and no target_start is set")
        print("target: not reachable, starting it", flush=True)
        res = subprocess.run(start, shell=True, capture_output=True, text=True, timeout=300)
        if res.returncode != 0 or not self.reachable():
            raise RunError("target_start did not bring ssh up:\n" + _tail(res.stdout + res.stderr))

    def put(self, local: Path, remote: str) -> None:
        q = shlex.quote(remote)
        self.run(f"cat > {q}.new && chmod 755 {q}.new && mv -f {q}.new {q}",
                 stdin=local.read_bytes(), timeout=60)


def test(spec_path: str, outdir: str | None = None) -> int:
    cfg = load_config()
    spec = specmod.load(spec_path)
    name, path = spec["name"], spec["path"]
    out = Path(outdir or Path("build") / name).resolve()

    step(f"gen {spec_path} -> {out}")
    render.write(spec, out, Path(spec_path).name)

    step("build")
    res = subprocess.run(cfg["build_command"].format(dir=out), shell=True,
                         capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        print(_tail(res.stdout + res.stderr, 40), file=sys.stderr)
        raise RunError("build failed")
    for binary in (name, name + "_client"):
        if not (out / binary).is_file():
            raise RunError(f"build did not produce {binary}")
    print(_tail(res.stdout, 4))

    step("target")
    tgt = Target(cfg)
    tgt.ensure_up()
    rdir = cfg["remote_dir"].rstrip("/") or "/"
    server, client = f"{rdir}/{name}", f"{rdir}/{name}_client"
    log = f"{rdir}/{name}.log"

    step("deploy")
    tgt.run(f"slay -f {shlex.quote(name)} >/dev/null 2>&1; true", check=False)
    tgt.put(out / name, server)
    tgt.put(out / (name + "_client"), client)

    step("start")
    tgt.run(f"{shlex.quote(server)} </dev/null >{shlex.quote(log)} 2>&1 &", timeout=15)
    deadline = time.monotonic() + 5
    while not tgt.run(f"test -e {shlex.quote(path)}", check=False).returncode == 0:
        if time.monotonic() > deadline:
            log_tail = tgt.run(f"tail -n 20 {shlex.quote(log)}", check=False).stdout.decode()
            raise RunError(f"{path} did not appear within 5 s; server log:\n{log_tail}")
        time.sleep(0.25)
    print(f"{path} is up")

    try:
        step("pytest")
        junit = out / "junit.xml"
        env = dict(os.environ, RESMGR_KIT_SSH_ARGS=json.dumps(tgt.ssh),
                   RESMGR_KIT_REMOTE_DIR=rdir)
        rc = subprocess.call(
            [sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider",
             "--rootdir", str(out), f"--junitxml={junit}", str(out / "tests" / f"test_{name}.py")],
            env=env, cwd=out)
        step("target info")
        print(tgt.run("uname -a", check=False).stdout.decode().strip())
        print(f"junit: {junit}")
    finally:
        step("stop")
        tgt.run(f"slay -f {shlex.quote(name)} >/dev/null 2>&1; true", check=False)
    return 0 if rc == 0 else 1
