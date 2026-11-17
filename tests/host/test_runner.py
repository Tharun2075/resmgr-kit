"""Settings loading for `resmgr-kit test`; nothing here touches a target."""
from pathlib import Path

import pytest

from resmgr_kit import runner


@pytest.fixture
def no_user_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for key in list(runner.DEFAULTS) + ["build"]:
        monkeypatch.delenv("RESMGR_KIT_" + key.upper(), raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_config_in_current_folder_is_ignored(no_user_config):
    (no_user_config / "resmgr-kit.local.toml").write_text('build_command = "touch pwned"\n')
    assert runner.load_config()["build_command"] == runner.DEFAULTS["build_command"]


def test_explicit_config_is_read(no_user_config):
    extra = no_user_config / "target.toml"
    extra.write_text('port = 2300\n')
    assert runner.load_config(str(extra))["port"] == 2300


def test_missing_explicit_config_fails(no_user_config):
    with pytest.raises(runner.RunError):
        runner.load_config(str(no_user_config / "nope.toml"))


def test_build_command_with_literal_braces_runs(no_user_config, monkeypatch):
    monkeypatch.setenv("RESMGR_KIT_BUILD", 'echo "${HOME} {x}" > /dev/null; true # {dir}')
    example = next((Path(__file__).parents[2] / "examples").glob("*/*.yaml"))
    with pytest.raises(runner.RunError, match="did not produce"):
        runner.test(str(example), str(no_user_config / "out"))


def test_ssh_skips_host_key_check_by_default(no_user_config):
    args = runner.ssh_args(runner.load_config())
    assert "StrictHostKeyChecking=no" in args


def test_ssh_checks_host_key_when_insecure_local_is_off(no_user_config, monkeypatch):
    monkeypatch.setenv("RESMGR_KIT_SSH_INSECURE_LOCAL", "false")
    args = runner.ssh_args(runner.load_config())
    assert "StrictHostKeyChecking=no" not in args
    assert "UserKnownHostsFile=/dev/null" not in args
    assert "BatchMode=yes" in args


def test_target_secpol_is_off_by_default_and_parsed_as_bool(no_user_config, monkeypatch):
    assert runner.load_config()["target_secpol"] is False
    monkeypatch.setenv("RESMGR_KIT_TARGET_SECPOL", "off")
    assert runner.load_config()["target_secpol"] is False
    monkeypatch.setenv("RESMGR_KIT_TARGET_SECPOL", "yes")
    assert runner.load_config()["target_secpol"] is True


def test_merge_policy_adds_snippet_and_launcher_grant(no_user_config):
    base = no_user_config / "base.policy"
    base.write_text("type user_root_t;\n")
    out = no_user_config / "out"
    out.mkdir()
    (out / "estop.secpol").write_text("type estop_t;\n")
    cfg = dict(runner.DEFAULTS, secpol_base=str(base))
    text = runner.merge_policy({"name": "estop"}, out, cfg).read_text()
    assert text.index("type user_root_t;") < text.index("type estop_t;")
    assert "allow user_root_t self:ability { settypeid:estop_t channel_connect:estop_t };" in text


def test_merge_policy_needs_a_base_file(no_user_config):
    with pytest.raises(runner.RunError, match="secpol_base"):
        runner.merge_policy({"name": "estop"}, no_user_config, dict(runner.DEFAULTS))
