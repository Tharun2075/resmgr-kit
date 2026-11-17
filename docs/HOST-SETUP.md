# Host setup

You need three things: the QNX SDP 8.0 tools on a Linux x86_64 host, QEMU, and a QNX 8.0 x86_64 target image. The SDP is not included in this repository. It is downloaded by you from QNX under its own licence (see [THIRD-PARTY](../THIRD-PARTY.md)); this tool was built and tested under the QNX Everywhere Non-Commercial licence.

## A. Linux x86_64 host

1. Create a free myQNX account, accept the licence terms and download the QNX Software Center installer for Linux.
2. Install the SDP 8.0 baseline into `~/qnx800` with the QNX Software Center command-line tool (about 3.6 GB).
3. Activate your licence key **before** mirroring the baseline for the second time. Mirroring before activation leaves the target package out.
4. Check the toolchain:
   ```sh
   source ~/qnx800/qnxsdp-env.sh && qcc -V    # lists gcc_ntox86_64 and gcc_ntoaarch64le
   ```
5. Install QEMU (`qemu-system-x86_64`) from your package manager and Python 3.11+.

## B. macOS (Apple Silicon) with OrbStack

QNX host tools run only on Linux x86_64 and Windows, so `qcc` runs in an amd64 Linux machine. QEMU runs natively on the Mac.

```sh
orb create --arch amd64 ubuntu:24.04 qnx-host     # runs under Rosetta
brew install qemu
```

Do the Linux steps (A.1 to A.4) inside `qnx-host`, then set `build_command` in the config to run `make` inside it:

```toml
build_command = "orb run -m qnx-host bash -lc 'source ~/qnx800/qnxsdp-env.sh && make -C {dir}'"
```

The build folder must be visible in both places; OrbStack shares the Mac home folder with the machine.

## C. Target image

One command makes the ssh key (if missing), builds the image and copies it to `~/qnx-target`:

```sh
tools/make-target.sh build                                  # Linux host with the SDP
QNX_RUN="orb run -m qnx-host" tools/make-target.sh build    # macOS with OrbStack
```

By hand, the same steps are:

```sh
ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_qnx_target
mkdir -p ~/img-x86 && cd ~/img-x86
source ~/qnx800/qnxsdp-env.sh
mkqnximage --type=qemu --arch=x86_64 --ssh-ident=$HOME/.ssh/id_qnx_target.pub
```

The result is `output/ifs.bin`, `output/disk-qemu` and `output/disk-qemu.vmdk`. To rebuild after an option change, remove `output` first. See [TROUBLESHOOTING](TROUBLESHOOTING.md).

## D. Boot and connect

Start QEMU with TCG on the x86_64 image and forward host port 2222 to the guest ssh port. Booting to ssh takes about 12 seconds; a console log is in [boot-log.txt](evidence/boot-log.txt). `tools/make-target.sh start` does this and waits until ssh answers; `stop`, `status` and `ssh <cmd>` are the other commands, and `PORT=2224` picks another port. Point `target_start` at it:

```toml
target_start = "tools/make-target.sh start"
```

Sample run: [make-target.txt](evidence/make-target.txt).

### aarch64le on QEMU virt

```sh
ARCH=aarch64le PORT=2226 IMG_DIR=~/qnx-target-a64 tools/make-target.sh build
ARCH=aarch64le PORT=2226 IMG_DIR=~/qnx-target-a64 tools/make-target.sh start
```

The SDP has no aarch64 `devb-virtio`, so the script swaps in local `mkqnximage` snippets: QEMU loads `disk-qemu` into guest RAM at 0x80000000, `startup-qemu-virt` reserves that range and `devb-ram` serves it as the disk. Changes on the target are lost at power-off. QEMU `virt` gives virtio slots from the top down, so a 1 MB dummy disk (`slot.img`) goes first to put the network and entropy devices where the image looks for them. Booting to ssh took 13 seconds under TCG. Sample run: [aarch64-run.txt](evidence/aarch64-run.txt).

## E. Config and first run

Write `~/.config/resmgr-kit/config.toml` as shown in the [README](../README.md), then:

```sh
.venv/bin/resmgr-kit test examples/vsensor/vsensor.yaml
```

A good run prints `uname -a` with `QNX` and `8.0`, all tests passed, and writes `junit.xml`. Sample output: [hello-test.txt](evidence/hello-test.txt).

## F. Secure-mode target (optional, for `test --secpol`)

`mkqnximage --secpol=...` compiles the boot policy without `-m`, so it cannot be replaced at run time and `secpolpush` fails with EPERM. Build the image with a mutable policy by putting a small wrapper first in `PATH`:

```sh
mkdir -p ~/secpol-shim
printf '#!/bin/sh\nexec %s -m "$@"\n' "$(command -v secpolcompile)" > ~/secpol-shim/secpolcompile
chmod +x ~/secpol-shim/secpolcompile
PATH=~/secpol-shim:$PATH mkqnximage --type=qemu --arch=x86_64 --ssh-ident=$HOME/.ssh/id_qnx_target.pub \
    --secpol=$PWD/policy.txt
```

`policy.txt` must also contain `allow user_root_t self:ability { mac_policy };` so the ssh login may push; `tools/secpol/qemu-x86_64-base.policy` has it. Then set `secpol_base` to that file, `secpol_compile` to a command that runs `secpolcompile -m -o {out} {src}` with the SDK environment, and run `resmgr-kit test --secpol <spec>`.
