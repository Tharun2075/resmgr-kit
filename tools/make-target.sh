#!/bin/bash
# Build a QNX 8.0 QEMU target image that trusts an ssh key, boot it with a host port
# forwarded to the guest ssh port, and wait until ssh answers.
#
# Usage: tools/make-target.sh build|start|stop|status|ssh <cmd...>
#   build   ssh key (made if missing) + mkqnximage + copy ifs.bin and disks into IMG_DIR
#   start   boot QEMU (TCG) from IMG_DIR, wait for ssh; reuses a running target
# Env (defaults in brackets):
#   ARCH       x86_64 or aarch64le (QEMU virt board, see docs/HOST-SETUP.md) [x86_64]
#   PORT       host port forwarded to guest port 22 [2222]
#   IMG_DIR    host folder for the image and the QEMU pid/console files [~/qnx-target]
#   KEY        ssh private key; KEY.pub goes into the image [~/.ssh/id_qnx_target]
#   QNX_RUN    prefix that runs a command where the QNX SDP is installed, empty for this
#              machine, e.g. "orb run -m qnx-host" on macOS with OrbStack []
#   QNX_ENV    qnxsdp-env.sh on that side ['~/qnx800/qnxsdp-env.sh']
#   BUILD_DIR  mkqnximage work folder on that side ['~/resmgr-kit-img']
# Point resmgr-kit at it with: target_start = "PORT=2222 /path/to/tools/make-target.sh start"
set -u
ARCH=${ARCH:-x86_64}
PORT=${PORT:-2222}
IMG_DIR=${IMG_DIR:-$HOME/qnx-target}
KEY=${KEY:-$HOME/.ssh/id_qnx_target}
QNX_RUN=${QNX_RUN:-}
QNX_ENV=${QNX_ENV:-'~/qnx800/qnxsdp-env.sh'}
BUILD_DIR=${BUILD_DIR:-'~/resmgr-kit-img'}
PIDF=$IMG_DIR/qemu.pid
CONSOLE=$IMG_DIR/console.log
SSH=(ssh -i "$KEY" -p "$PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
     -o LogLevel=ERROR -o ConnectTimeout=5 -o BatchMode=yes root@127.0.0.1)

# aarch64le: the SDP ships no aarch64 devb-virtio and no PCI hardware module for the
# QEMU virt board, so the stock image finds no disk. QEMU loads disk-qemu into guest
# RAM at 0x80000000 instead, startup reserves that range without clearing it (-r ...,1)
# and devb-ram serves it; devb-ram has no disk-sync command, so qnx6 mounts with
# sync=optional. Changes are lost at power-off. The fixed partition sizes make the
# disk size known before the build: A64_BLOCKS 512-byte blocks.
A64_SIZES="--sys-size=200 --data-size=40"
A64_BLOCKS=634273
A64_SNIPPETS="d=\$QNX_HOST/../../common/mkqnximage/qemu/snippets && mkdir -p local/snippets &&
  sed -e 's/^#define __DEVB_NAME__ devb-virtio.*/#define __DEVB_NAME__ devb-ram/' \
      -e 's/^#define __DEVB_OPTS__ virtio.*/#define __DEVB_OPTS__ ram address=0x80000000,capacity=$A64_BLOCKS qnx6 sync=optional/' \
      \$d/definitions.type_qemu > local/snippets/definitions.type_qemu &&
  grep -q 'devb-ram' local/snippets/definitions.type_qemu &&
  echo 'STARTUP_OPTIONS=\"-r 0x80000000,0x13600000,1\"' > local/snippets/options.resmgr_kit_ramdisk"

alive() { [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; }
ssh_ok() { "${SSH[@]}" true 2>/dev/null; }
qnx() { $QNX_RUN bash -c "source $QNX_ENV >/dev/null && $1"; }

case "${1:-}" in
build)
    [ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N '' -f "$KEY" || exit 1
    mkdir -p "$IMG_DIR"
    echo "make-target: mkqnximage in $BUILD_DIR (a few minutes)"
    # mkqnximage wants an empty or own folder, so the log goes next to it
    case $ARCH in
    x86_64) prep=true; opts=; files="ifs.bin disk-qemu disk-qemu.vmdk" ;;
    aarch64le) prep=$A64_SNIPPETS; opts=$A64_SIZES; files="ifs.bin disk-qemu" ;;
    *) echo "make-target: ARCH must be x86_64 or aarch64le" >&2; exit 2 ;;
    esac
    qnx "mkdir -p $BUILD_DIR && cd $BUILD_DIR && rm -rf output local && { $prep; } &&
         mkqnximage --type=qemu --arch=$ARCH $opts --ssh-ident=$KEY.pub >$BUILD_DIR.log 2>&1 ||
         { tail -n 20 $BUILD_DIR.log; exit 1; }" || exit 1
    # cat, not cp: works the same when the build side is a VM with its own file system
    for f in $files; do
        qnx "cat $BUILD_DIR/output/$f" > "$IMG_DIR/$f" || exit 1
    done
    # the vmdk descriptor names disk-qemu by relative path, so the copy boots from IMG_DIR
    if [ "$ARCH" = aarch64le ]; then
        size=$(wc -c < "$IMG_DIR/disk-qemu" | tr -d ' ')
        [ "$size" = $((A64_BLOCKS * 512)) ] || { echo "make-target: disk-qemu is $size bytes," \
            "devb-ram expects $((A64_BLOCKS * 512)). Fix: set A64_BLOCKS=$((size / 512))" >&2; exit 1; }
    fi
    echo "make-target: image in $IMG_DIR" ;;
start)
    if alive && ssh_ok; then echo "target: reused (pid $(cat "$PIDF"), port $PORT)"; exit 0; fi
    [ -f "$IMG_DIR/ifs.bin" ] || { echo "make-target: no image in $IMG_DIR; run build first" >&2; exit 1; }
    alive && kill "$(cat "$PIDF")" && sleep 1
    t0=$(date +%s)
    net=(-netdev user,id=net0,hostfwd=tcp:127.0.0.1:$PORT-:22
         -object rng-random,filename=/dev/urandom,id=rng0)
    out=(-display none -serial file:"$CONSOLE" -pidfile "$PIDF" -daemonize)
    if [ "$ARCH" = aarch64le ]; then
        # QEMU gives virtio-mmio slots from the top down in device order, and the image
        # expects disk 0xa003e00, net 0xa003c00, rng 0xa003a00 (devr-virtio mem=). A small
        # unused disk keeps the top slot so net and rng land where the image looks.
        [ -f "$IMG_DIR/slot.img" ] || dd if=/dev/zero of="$IMG_DIR/slot.img" bs=1024 count=1024 2>/dev/null
        qemu-system-aarch64 -M virt,gic-version=2 -accel tcg -cpu cortex-a57 -smp 2 -m 2G \
            -kernel "$IMG_DIR/ifs.bin" \
            -device loader,file="$IMG_DIR/disk-qemu",addr=0x80000000,force-raw=on \
            -drive file="$IMG_DIR/slot.img",format=raw,if=none,id=drv0 -device virtio-blk-device,drive=drv0 \
            "${net[@]}" -device virtio-net-device,netdev=net0 -device virtio-rng-device,rng=rng0 \
            "${out[@]}" || exit 1
    else
        qemu-system-x86_64 -accel tcg -smp 2 -cpu max -m 1G \
            -kernel "$IMG_DIR/ifs.bin" \
            -drive file="$IMG_DIR/disk-qemu.vmdk",if=ide,id=drv0 \
            "${net[@]}" -device virtio-net-pci,netdev=net0 -device virtio-rng-pci,rng=rng0 \
            "${out[@]}" || exit 1
    fi
    for _ in $(seq 1 300); do
        ssh_ok && { echo "target: booted, ssh up on port $PORT after $(( $(date +%s) - t0 ))s"; exit 0; }
        sleep 1
    done
    echo "target: ssh not up after 300s; see $CONSOLE" >&2; exit 1 ;;
stop)
    alive && kill "$(cat "$PIDF")"; rm -f "$PIDF"; echo "target: stopped" ;;
status)
    alive && echo running || echo stopped ;;
ssh)
    shift; exec "${SSH[@]}" "$@" ;;
*)
    sed -n '2,18p' "$0" >&2; exit 2 ;;
esac
