# Third-party software

This project is Apache-2.0 ([LICENSE](LICENSE)). It depends on the software below. Licences were read from the installed package metadata.

## Python packages (installed by `pip install -e .`)

Direct dependencies:

| Package | Version checked | Licence |
|---|---|---|
| Jinja2 | 3.1.6 | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT |
| jsonschema | 4.26.0 | MIT |
| pytest | 9.1.1 | MIT |

Pulled in by them:

| Package | Version checked | Licence |
|---|---|---|
| MarkupSafe | 3.0.4 | BSD-3-Clause |
| attrs | 26.1.0 | MIT |
| referencing | 0.37.0 | MIT |
| rpds-py | 2026.6.3 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| iniconfig | 2.3.1 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pluggy | 1.6.0 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |

Compare with your own install: `pip freeze`. Versions differ over time; the licences above are those of the versions checked.

## Tools run but not shipped

- QEMU (`qemu-system-x86_64`): GPL-2.0, used as a separate program to run the target image. Not copied into this repository.
- OpenSSH client (`ssh`, `scp`): BSD-style licence, called through the system install.
- OrbStack: optional, macOS only, used under its own terms for a Linux build machine.

## Optional third-party AI service

`resmgr-kit ai` (optional; `gen` and `test` never use it) sends the spec, the generated C file and the region to fill to a large language model chosen by the user:

- Anthropic API (default provider, default model `claude-sonnet-5-5`), used with the user's own `LLM_API_KEY` under Anthropic's commercial terms.
- Any OpenAI-compatible endpoint the user configures, under that provider's terms.
- The Claude Code CLI (`LLM_PROVIDER=claude-cli`), under its own terms, with the user's own login.

No SDK is shipped or installed for this: the calls use the Python standard library (`urllib`). Model output is not trusted: it is accepted only when it builds and every generated live test passes on the QNX target.

## QNX software

QNX Software Development Platform 8.0 (`qcc`, `mkqnximage`, the target image and its libraries) is **not** part of this repository. You download it yourself from QNX and use it under your own licence; this project was built and tested under the QNX Everywhere Non-Commercial licence. The generated C code links against QNX libraries only on your machine.

"QNX" is used only to describe the platform this tool targets. This project is not affiliated with or endorsed by BlackBerry or QNX.

## C dependencies

The generated C code uses only the QNX C library and the QNX resource manager framework (`<sys/dispatch.h>`, `<sys/iofunc.h>`) from the SDP. No other C library is used.
