"""`resmgr-kit sh` passes the command to ssh with the configured settings."""

from resmgr_kit import cli, runner


def test_sh_uses_config(monkeypatch, tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('target = "root@10.0.0.9"\nport = 2299\n')
    monkeypatch.setattr(runner.Path, "home", lambda: tmp_path)
    for var in ("RESMGR_KIT_TARGET", "RESMGR_KIT_PORT", "RESMGR_KIT_SSH_KEY"):
        monkeypatch.delenv(var, raising=False)
    seen = {}
    monkeypatch.setattr(runner.subprocess, "call", lambda args: seen.setdefault("args", args) and 7)
    assert cli.main(["sh", "--config", str(cfg), "cat /dev/x0"]) == 7
    args = seen["args"]
    assert args[:3] == ["ssh", "-p", "2299"]
    assert args[-2:] == ["root@10.0.0.9", "cat /dev/x0"]
