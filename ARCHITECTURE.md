# Architecture

`resmgr-kit` is a host tool. It never runs on the QNX target; it produces QNX 8.0 software and tests it there.

```mermaid
flowchart LR
    A[spec.yaml] --> B[schema check<br/>schema.json + cross-field rules]
    B --> C[Jinja render<br/>templates/*.j2]
    C --> D[qcc build<br/>Linux x86_64 host, QNX SDP 8.0]
    D --> E[scp over ssh<br/>to QEMU x86_64 QNX 8.0]
    E --> F[start resource manager<br/>on target]
    F --> G[pytest on the host<br/>live tests over ssh]
    G --> H[junit.xml + uname -a]
```

`resmgr-kit ai` adds a loop around the same pipeline for handlers marked `impl: ai` in the spec:

```mermaid
flowchart LR
    R[gen: marked stub region<br/>per impl: ai handler] --> M[model writes the<br/>region body only]
    M --> K[host check: no preprocessor,<br/>balanced braces, text outside<br/>markers byte-identical]
    K --> Q[qcc build]
    Q --> T[deploy + live tests<br/>on the QNX target]
    T -->|all pass| OK[exit 0]
    T -->|compile error or failing tests| M
    K -->|refused| M
```

The live tests on the target decide; the model never edits code outside its region. Up to `--max-iter` rounds. A real fail-then-fix run is in [docs/evidence/ai-real-run-fail-fix.txt](docs/evidence/ai-real-run-fail-fix.txt).

A bad spec stops at the schema check with exit 2 and an error that names the field (for example `state[1] (rate_hz).max`). Only `test` goes past the render step; `gen` stops after it.

## Components

| Part | File | Job |
|---|---|---|
| CLI | [cli.py](src/resmgr_kit/cli.py), [__main__.py](src/resmgr_kit/__main__.py) | `gen`, `test`, `ai` and `sh` sub-commands |
| Spec loader and checks | [spec.py](src/resmgr_kit/spec.py), [schema.json](src/resmgr_kit/schema.json) | YAML safe load, JSON schema, cross-field rules |
| Renderer | [render.py](src/resmgr_kit/render.py) | Fills the templates, writes the output folder |
| AI mode | [ai.py](src/resmgr_kit/ai.py) | Fills `impl: ai` regions with a model, checks the reply, loops on build and live-test feedback |
| Runner | [runner.py](src/resmgr_kit/runner.py) | Build, start or reuse the target, copy over ssh, run pytest, write JUnit |
| Resource manager | [resmgr.c.j2](src/resmgr_kit/templates/resmgr.c.j2) | `dispatch_create`, `resmgr_attach`, iofunc handlers, devctl table, pulse timer, thread pool, `MsgDeliverEvent` notify |
| Shared header | [header.h.j2](src/resmgr_kit/templates/header.h.j2) | devctl codes and structs shared with the client |
| Client | [client.c.j2](src/resmgr_kit/templates/client.c.j2) | Small test client for the generated `/dev` path |
| Build files | [Makefile.j2](src/resmgr_kit/templates/Makefile.j2), [build.j2](src/resmgr_kit/templates/build.j2) | `qcc` Makefile and an image build-file fragment |
| Security policy | [secpol.j2](src/resmgr_kit/templates/secpol.j2) | Type, `allow_attach`, abilities (see [TROUBLESHOOTING](docs/TROUBLESHOOTING.md)) |
| Tests | [test.py.j2](src/resmgr_kit/templates/test.py.j2) | pytest file that drives the live device over ssh |
| Host tests | [tests/host](tests/host) | Tests that need no QNX toolchain |
| Examples | [vsensor](examples/vsensor/vsensor.yaml), [estop](examples/estop/estop.yaml), [counter](examples/counter/counter.yaml), [vsensor_ai](examples/vsensor_ai/vsensor_ai.yaml) | Specs used for the live runs; counter is the codelab spec, vsensor_ai the AI-mode spec |

## Where each step runs

- Spec check, render and pytest run on the developer machine (any OS with Python 3.11+).
- `qcc` runs in a Linux x86_64 host, because the QNX SDP host tools ship for Linux x86_64 and Windows. On macOS that host is a VM or container; see [HOST-SETUP](docs/HOST-SETUP.md).
- The target is QNX 8.0 x86_64 under QEMU, reached by ssh. `make TARGET=aarch64le` cross-builds for 64-bit Arm (built, not yet run there). The runner reuses a target that already answers and runs `target_start` from the config otherwise.
- Config comes only from `~/.config/resmgr-kit/config.toml`, environment variables or an explicit `--config`, never from the current folder, because its commands run in a shell.
