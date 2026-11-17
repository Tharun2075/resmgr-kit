# resmgr-kit

A host tool that turns a short YAML spec into a QNX 8.0 resource manager in C, then builds it with `qcc`, boots QNX 8.0 in QEMU, deploys it and runs a generated test suite against the live `/dev` path.

Status: work in progress for the QNX Global Hackathon 2026 (project started November 2026).

- Target: QNX 8.0 on QEMU x86_64
- Toolchain: `qcc` from QNX SDP 8.0
- Licence: Apache-2.0 (see `LICENSE`)

This is a research and demo prototype, not a certified product. It is built and tested under the QNX Everywhere Non-Commercial licence. No personal data is collected or stored.

"QNX" is used here only to describe the platform this tool targets. This project is not affiliated with or endorsed by BlackBerry or QNX.
