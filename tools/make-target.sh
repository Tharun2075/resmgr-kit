#!/bin/bash
# Build a QNX 8.0 QEMU target image that trusts an ssh key, boot it with a host port
# forwarded to the guest ssh port, and wait until ssh answers.
#
# Usage: tools/make-target.sh build|start|stop|status|ssh <cmd...>
#   build   ssh key (made if missing) + mkqnximage + copy ifs.bin and disks into IMG_DIR
#   start   boot QEMU (TCG) from IMG_DIR, wait for ssh; reuses a running target
# Env (defaults in brackets):
#   PORT       host port forwarded to guest port 22 [2222]
#   IMG_DIR    host folder for the image and the QEMU pid/console files [~/qnx-target]
#   KEY        ssh private key; KEY.pub goes into the image [~/.ssh/id_qnx_target]
#   QNX_RUN    prefix that runs a command where the QNX SDP is installed, empty for this
#              machine, e.g. "orb run -m qnx-host" on macOS with OrbStack []
#   QNX_ENV    qnxsdp-env.sh on that side ['~/qnx800/qnxsdp-env.sh']
#   BUILD_DIR  mkqnximage work folder on that side ['~/resmgr-kit-img']
# Point resmgr-kit at it with: target_start = "PORT=2222 /path/to/tools/make-target.sh start"
set -u
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

alive() { [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; }
ssh_ok() { "${SSH[@]}" true 2>/dev/null; }
qnx() { $QNX_RUN bash -c "source $QNX_ENV >/dev/null && $1"; }

case "${1:-}" in
build)
    [ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N '' -f "$KEY" || exit 1
    mkdir -p "$IMG_DIR"
    echo "make-target: mkqnximage in $BUILD_DIR (a few minutes)"
    # mkqnximage wants an empty or own folder, so the log goes next to it
    qnx "mkdir -p $BUILD_DIR && cd $BUILD_DIR && rm -rf output &&
         mkqnximage --type=qemu --arch=x86_64 --ssh-ident=$KEY.pub >$BUILD_DIR.log 2>&1 ||
         { tail -n 20 $BUILD_DIR.log; exit 1; }" || exit 1
    # cat, not cp: works the same when the build side is a VM with its own file system
    for f in ifs.bin disk-qemu disk-qemu.vmdk; do
        qnx "cat $BUILD_DIR/output/$f" > "$IMG_DIR/$f" || exit 1
    done
    # the vmdk descriptor names disk-qemu by relative path, so the copy boots from IMG_DIR
    echo "make-target: image in $IMG_DIR" ;;
start)
    if alive && ssh_ok; then echo "target: reused (pid $(cat "$PIDF"), port $PORT)"; exit 0; fi
    [ -f "$IMG_DIR/ifs.bin" ] || { echo "make-target: no image in $IMG_DIR; run build first" >&2; exit 1; }
    alive && kill "$(cat "$PIDF")" && sleep 1
    t0=$(date +%s)
    qemu-system-x86_64 -accel tcg -smp 2 -cpu max -m 1G \
        -kernel "$IMG_DIR/ifs.bin" \
        -drive file="$IMG_DIR/disk-qemu.vmdk",if=ide,id=drv0 \
        -netdev user,id=net0,hostfwd=tcp:127.0.0.1:$PORT-:22 \
        -device virtio-net-pci,netdev=net0 \
        -object rng-random,filename=/dev/urandom,id=rng0 -device virtio-rng-pci,rng=rng0 \
        -display none -serial file:"$CONSOLE" -pidfile "$PIDF" -daemonize || exit 1
    for _ in $(seq 1 180); do
        ssh_ok && { echo "target: booted, ssh up on port $PORT after $(( $(date +%s) - t0 ))s"; exit 0; }
        sleep 1
    done
    echo "target: ssh not up after 180s; see $CONSOLE" >&2; exit 1 ;;
stop)
    alive && kill "$(cat "$PIDF")"; rm -f "$PIDF"; echo "target: stopped" ;;
status)
    alive && echo running || echo stopped ;;
ssh)
    shift; exec "${SSH[@]}" "$@" ;;
*)
    sed -n '2,17p' "$0" >&2; exit 2 ;;
esac
