# resmgr-kit

A host tool that turns a short YAML spec into a QNX 8.0 resource manager in C, then builds it with `qcc`, boots QNX 8.0 in QEMU, deploys it and runs a generated test suite against the live `/dev` path.

Status: work in progress. Project created in November 2026 for the QNX Global Hackathon 2026.

- Target: QNX 8.0 on QEMU x86_64
- Toolchain: `qcc` from QNX SDP 8.0
- Licence: Apache-2.0 (see `LICENSE`)

## Quick start

```sh
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/resmgr-kit gen examples/vsensor/vsensor.yaml -o build/vsensor
.venv/bin/resmgr-kit test examples/vsensor/vsensor.yaml
.venv/bin/pytest tests/host -q
```

`gen` checks the spec and writes `<name>.c`, `<name>.h`, a small client, a `qcc` Makefile, a `<name>.build` image fragment, a `<name>.secpol` snippet and `tests/test_<name>.py`. `test` runs gen, builds with `qcc`, starts or reuses the QEMU target, copies the binaries over ssh, starts the resource manager, runs the generated tests from the host, prints `uname -a`, writes `junit.xml` and stops the server. It exits 0 only when every test passes. The host tests in `tests/host` need no QNX toolchain.

`test` needs the QNX SDP 8.0 toolchain and a QNX 8.0 target reachable over ssh. Set them in `~/.config/resmgr-kit/config.toml`, or pass another file with `test --config <file>`. A config file in the current folder is never read on its own, because its commands run in a shell:

```toml
build_command = "make -C {dir}"          # how to run make with qcc on PATH; {dir} is quoted for you
target = "root@127.0.0.1"
port = 2222
ssh_key = "~/.ssh/id_qnx_target"
target_start = "./start-target.sh start" # run when ssh does not answer
```

Each key can also come from the environment: `RESMGR_KIT_BUILD`, `RESMGR_KIT_TARGET`, `RESMGR_KIT_PORT`, `RESMGR_KIT_SSH_KEY`, `RESMGR_KIT_TARGET_START`, `RESMGR_KIT_REMOTE_DIR`.

## Documentation

- [docs/CODELAB.md](docs/CODELAB.md): your first resource manager, tested on QEMU, in 15 minutes
- [ARCHITECTURE.md](ARCHITECTURE.md): pipeline diagram and component list
- [docs/HOST-SETUP.md](docs/HOST-SETUP.md): Linux x86_64 and macOS host, QEMU, target image
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): known problems and fixes
- [docs/SUBMISSION-CHECKLIST.md](docs/SUBMISSION-CHECKLIST.md): contest checklist
- [THIRD-PARTY.md](THIRD-PARTY.md): dependencies and licences
- [docs/evidence](docs/evidence): logs from live runs on QNX 8.0

## Examples

- `examples/vsensor`: `/dev/vsensor0`. A read gives the latest simulated sample; `SET_RATE` clamps to 1..1000 Hz; a pulse timer drives the samples from a thread pool.
- `examples/estop`: `/dev/estop0`. Writing `1` trips it; a read gives the state; a client arms a pulse with `ARM_NOTIFY` and gets it on the trip.
- `examples/vsensor_ai`: the same sensor, but `SET_RATE` is `impl: ai` and is written in AI mode (below).

## AI mode

A set or get devctl, or the write handler, can be marked `impl: ai` with a plain-English `behaviour:` line:

```yaml
devctls:
  - {name: SET_RATE, code: 1, op: set, field: rate_hz, out_of_range: clamp, impl: ai,
     behaviour: "clamps to 1..1000 Hz, EINVAL on short payload"}
```

`resmgr-kit gen` and `resmgr-kit test` then emit a stub (`return ENOSYS;`) between `/* resmgr-kit:ai-begin SET_RATE */` and `/* resmgr-kit:ai-end SET_RATE */`, so the generated tests fail until the region is filled. `resmgr-kit ai <spec.yaml>` fills it:

1. gen, then ask the model for the body of that region only. The prompt holds the spec, the whole generated C file and the QNX 8.0 resource manager rules the body must keep (devctl data sizes, reply iov, locking, errno returns).
2. Put the body in. A reply with a marker, a preprocessor line or unbalanced braces is refused, and the text outside the markers is checked to be byte-identical.
3. Build, deploy and run the generated live tests on the target, as `resmgr-kit test` does.
4. On a compiler error or a failing test, send the output back and try again, up to `--max-iter` rounds (default 3). Each round prints its diff and result.

On green the result is in `build/<name>/` (bodies also in `build/<name>/ai_regions/`); review it before you copy it anywhere. `resmgr-kit test` regenerates the stub, so it does not keep an AI body.

```sh
export LLM_API_KEY=...                 # never commit it
resmgr-kit ai examples/vsensor_ai/vsensor_ai.yaml --max-iter 3
resmgr-kit ai examples/vsensor_ai/vsensor_ai.yaml --dry-run   # print the prompt, no network

# no API key: use the Claude Code CLI you are already logged in to
LLM_PROVIDER=claude-cli resmgr-kit ai examples/vsensor_ai/vsensor_ai.yaml
```

| Variable | Meaning |
| --- | --- |
| `LLM_PROVIDER` | `anthropic` (default), `openai-compatible` or `claude-cli` |
| `LLM_API_KEY` | required for `anthropic` and `openai-compatible`; without it `resmgr-kit ai` says so and exits 2 (gen and test do not need it) |
| `LLM_MODEL` | default `claude-sonnet-5-5` for anthropic; required for openai-compatible |
| `LLM_BASE_URL` | default `https://api.anthropic.com`; required for openai-compatible (for example a local server's `/v1`) |

`claude-cli` sends the same prompt on stdin to `claude -p --output-format text` with its tools turned off, from an empty folder with project settings and MCP servers ignored, so it uses the Claude Code CLI's own login and needs no key; resmgr-kit adds no network code for it. `LLM_MODEL`, if set, is passed as `--model` (for example `sonnet`); otherwise the CLI's default model is used. Without a `claude` binary on `PATH` it says so and exits 2. Full transcripts of real runs on the QNX target: [docs/evidence/ai-real-run.txt](docs/evidence/ai-real-run.txt) (green on the first round) and [docs/evidence/ai-real-run-fail-fix.txt](docs/evidence/ai-real-run-fail-fix.txt) (a behaviour line that disagrees with the spec fails 2 live tests, the model fixes it on round 2).

AI output is reviewed and tested; no AI code runs without passing on target. No AI part is a safety component: AI mode writes demo handlers for a prototype, and the generated live tests are the only bar it has to clear.

This is a research and demo prototype, not a production product. It is built and tested under the QNX Everywhere Non-Commercial licence. In this project no personal data is collected or stored.

"QNX" is used here only to describe the platform this tool targets. This project is not affiliated with or endorsed by BlackBerry or QNX.
