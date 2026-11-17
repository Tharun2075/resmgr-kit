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
