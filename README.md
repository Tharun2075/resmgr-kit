# resmgr-kit

A host tool that turns a short YAML spec into a QNX 8.0 resource manager in C, then builds it with `qcc`, boots QNX 8.0 in QEMU, deploys it and runs a generated test suite against the live `/dev` path.

Status: work in progress for the QNX Global Hackathon 2026 (project started November 2026).

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

`test` needs the QNX SDP 8.0 toolchain and a QNX 8.0 target reachable over ssh. Set them in `~/.config/resmgr-kit/config.toml` or `./resmgr-kit.local.toml`:

```toml
build_command = "make -C '{dir}'"        # how to run make with qcc on PATH
target = "root@127.0.0.1"
port = 2222
ssh_key = "~/.ssh/id_qnx_target"
target_start = "./start-target.sh start" # run when ssh does not answer
```

Each key can also come from the environment: `RESMGR_KIT_BUILD`, `RESMGR_KIT_TARGET`, `RESMGR_KIT_PORT`, `RESMGR_KIT_SSH_KEY`, `RESMGR_KIT_TARGET_START`, `RESMGR_KIT_REMOTE_DIR`.

## Examples

- `examples/vsensor`: `/dev/vsensor0`. A read gives the latest simulated sample; `SET_RATE` clamps to 1..1000 Hz; a pulse timer drives the samples from a thread pool.
- `examples/estop`: `/dev/estop0`. Writing `1` trips it; a read gives the state; a client arms a pulse with `ARM_NOTIFY` and gets it on the trip.

This is a research and demo prototype, not a production product. It is built and tested under the QNX Everywhere Non-Commercial licence. No personal data is collected or stored.

"QNX" is used here only to describe the platform this tool targets. This project is not affiliated with or endorsed by BlackBerry or QNX.
