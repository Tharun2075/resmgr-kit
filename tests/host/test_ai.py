"""`resmgr-kit ai` with a fake model and a fake target; nothing here uses the network."""
import socket
from pathlib import Path

import pytest

from resmgr_kit import ai, cli, render, runner, spec as specmod

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "examples/vsensor_ai/vsensor_ai.yaml"

GOOD = """```c
uint32_t in, out;
if (msg->i.nbytes < sizeof(in) || ctp->info.msglen < sizeof(msg->i) + sizeof(in))
    return EINVAL;
memcpy(&in, data, sizeof(in));
if ((status = check_rate_hz((long long)in, 1, &out)) != EOK)
    return status;
pthread_mutex_lock(&state_lock);
set_rate_hz(out);
pthread_mutex_unlock(&state_lock);
memcpy(data, &out, sizeof(out));
nbytes = sizeof(out);
break;
```"""


@pytest.fixture
def src():
    return render.render(specmod.load(SPEC), SPEC.name)["vsensor_ai.c"]


@pytest.fixture
def no_net(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture
def offline(tmp_path, monkeypatch, no_net):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_gen_emits_a_marked_stub_region(src):
    assert src.count(ai.BEGIN.format(name="SET_RATE")) == 1
    assert "return ENOSYS;" in ai.region_body(src, "SET_RATE")
    assert specmod.ai_regions(specmod.load(SPEC)) == ["SET_RATE"]


def test_region_insertion_changes_only_the_region(src):
    new = ai.replace_region(src, "SET_RATE", ai.extract_code(GOOD))
    start = src.index(ai.BEGIN.format(name="SET_RATE"))
    end = src.index(ai.END.format(name="SET_RATE"))
    tail = len(src) - end
    assert new[:start] == src[:start]
    assert new[-tail:] == src[-tail:]
    body = ai.region_body(new, "SET_RATE")
    assert "set_rate_hz(out);" in body and "ENOSYS" not in body
    assert all(ln.startswith("        ") for ln in body.splitlines())


@pytest.mark.parametrize("bad", [
    "}\nint evil(void) {\n",
    "#include <stdlib.h>\nbreak;\n",
    "/* resmgr-kit:ai-end SET_RATE */\nbreak;\n",
    "break; /* open comment\n",
    'x = "/*"; } int evil(void) { /* */\n',
    "// hide \\\n}\n",
    "x = '??/'; }\n",
    'x = "open;\n',
])
def test_body_that_reaches_outside_is_refused(src, bad):
    with pytest.raises(ValueError):
        ai.replace_region(src, "SET_RATE", bad)


def test_loop_feeds_back_and_stops_on_green(offline):
    replies = iter(["```c\nreturn ENOSYS;\n```", GOOD, "never asked"])
    prompts, checks = [], []

    def provider(system, prompt):
        prompts.append(prompt)
        return next(replies)

    def checker(spec, out, cfg):
        checks.append((out / "vsensor_ai.c").read_text())
        if "set_rate_hz(out)" not in checks[-1]:
            return 1, "test_vsensor_ai.py::test_set_rate_mid FAILED\nE   OSError: ENOSYS\n"
        return 0, "8 passed"

    rc = ai.run(str(SPEC), str(offline / "out"), max_iter=3, provider=provider, checker=checker)
    assert rc == 0
    assert len(prompts) == 2 and len(checks) == 2
    assert "Your last body failed" in prompts[1] and "test_set_rate_mid FAILED" in prompts[1]
    kept = (offline / "out/ai_regions/SET_RATE.c").read_text()
    assert "set_rate_hz(out);" in kept


def test_loop_gives_up_after_max_iter(offline, capsys):
    rc = ai.run(str(SPEC), str(offline / "out"), max_iter=2,
                provider=lambda s, p: "```c\nreturn ENOSYS;\n```",
                checker=lambda s, o, c: (1, "1 failed"))
    assert rc == 1
    assert "not green after 2" in capsys.readouterr().out


def test_build_error_is_fed_back(offline):
    prompts = []

    def provider(system, prompt):
        prompts.append(prompt)
        return GOOD

    def checker(spec, out, cfg):
        if len(prompts) == 1:
            raise runner.RunError("build failed:\nvsensor_ai.c:270: error: 'x' undeclared")
        return 0, "passed"

    assert ai.run(str(SPEC), str(offline / "out"), provider=provider, checker=checker) == 0
    assert "'x' undeclared" in prompts[1]


def test_no_key_exits_2(offline, monkeypatch, capsys):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert cli.main(["ai", str(SPEC)]) == 2
    assert "LLM_API_KEY" in capsys.readouterr().err


def test_dry_run_prints_prompt_without_network(offline, monkeypatch, capsys):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert cli.main(["ai", str(SPEC), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "clamps to 1..1000 Hz, EINVAL on short payload" in out
    assert "resmgr-kit:ai-begin SET_RATE" in out
    assert not (offline / "build").exists()


def test_spec_without_ai_region_exits_2(offline, capsys):
    assert cli.main(["ai", str(ROOT / "examples/vsensor/vsensor.yaml"), "--dry-run"]) == 2


def test_openai_compatible_needs_model_and_base():
    with pytest.raises(ai.AIError):
        ai.make_provider({"LLM_API_KEY": "x", "LLM_PROVIDER": "openai-compatible"})
    call, desc = ai.make_provider({"LLM_API_KEY": "x"})
    assert desc == "anthropic model claude-sonnet-5-5"


def test_impl_ai_needs_behaviour(tmp_path):
    text = SPEC.read_text().replace(
        ',\n     behaviour: "clamps to 1..1000 Hz, EINVAL on short payload"}', "}")
    assert "behaviour:" not in text
    p = tmp_path / "s.yaml"
    p.write_text(text)
    with pytest.raises(specmod.SpecError, match="behaviour"):
        specmod.load(p)


FAKE_CLAUDE = """#!/bin/sh
# stand-in for the Claude Code CLI: record argv and stdin, reply with a fixed body
printf '%s\\n' "$@" > "$(dirname "$0")/argv.txt"
cat > "$(dirname "$0")/stdin.txt"
printf '```c\\nreturn EOK;\\n```\\n'
"""


def _fake_claude(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "claude"
    exe.write_text(FAKE_CLAUDE)
    exe.chmod(0o755)
    return bindir


def test_claude_cli_pipes_prompt_on_stdin(tmp_path):
    bindir = _fake_claude(tmp_path)
    env = {"LLM_PROVIDER": "claude-cli", "LLM_MODEL": "sonnet", "PATH": f"{bindir}:/bin:/usr/bin"}
    call, desc = ai.make_provider(env)
    assert desc == "claude-cli model sonnet"
    reply = call("SYSTEM TEXT", "PROMPT TEXT")
    assert ai.extract_code(reply).strip() == "return EOK;"
    argv = (bindir / "argv.txt").read_text().splitlines()
    assert argv[:3] == ["-p", "--output-format", "text"]
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert argv[argv.index("--system-prompt") + 1] == "SYSTEM TEXT"
    assert (bindir / "stdin.txt").read_text() == "PROMPT TEXT"


def test_claude_cli_needs_no_key_and_no_model(tmp_path):
    bindir = _fake_claude(tmp_path)
    call, desc = ai.make_provider({"LLM_PROVIDER": "claude-cli", "PATH": f"{bindir}:/bin:/usr/bin"})
    call("s", "p")
    assert "--model" not in (bindir / "argv.txt").read_text().splitlines()


def test_claude_cli_missing_binary_exits_2(offline, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "claude-cli")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert cli.main(["ai", str(SPEC)]) == 2
    assert "claude" in capsys.readouterr().err


def test_claude_cli_failure_is_reported(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "claude").write_text("#!/bin/sh\necho 'not logged in' >&2\nexit 1\n")
    (bindir / "claude").chmod(0o755)
    call, _ = ai.make_provider({"LLM_PROVIDER": "claude-cli", "PATH": f"{bindir}:/bin:/usr/bin"})
    with pytest.raises(runner.RunError, match="not logged in"):
        call("s", "p")


def test_claude_cli_loop_runs_with_fake_cli(offline, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(_fake_claude(tmp_path)) + ":/bin:/usr/bin")
    monkeypatch.setenv("LLM_PROVIDER", "claude-cli")
    seen = []

    def checker(spec, out, cfg):
        seen.append(ai.region_body((out / "vsensor_ai.c").read_text(), "SET_RATE"))
        return 0, "passed"

    assert ai.run(str(SPEC), str(tmp_path / "out"), checker=checker) == 0
    assert "return EOK;" in seen[0]
