# Troubleshooting

Each entry is something that actually went wrong while building and testing this tool on QNX SDP 8.0. Evidence logs are in [evidence](evidence).

## The resource manager will not attach with the security policy on

Two different errors, two different missing rules (see [secpol-deny.txt](evidence/secpol-deny.txt)):

| Error from `resmgr_attach` | Missing rule |
|---|---|
| `Operation not permitted` (EPERM) | the `pathspace` ability |
| `Permission denied` (EACCES) | `allow_attach` for the `/dev/<name>` path |

You need both. The generated `<name>.secpol` has them; the working case is in [secpol-allow.txt](evidence/secpol-allow.txt). Also:

- The launching type needs `settypeid:<name>_t`, or `on -T` cannot switch type.
- The launching type needs `channel_connect:<name>_t`, or clients cannot open `/dev/<name>`.
- Launch with `on -T <name>_t /path/to/<name> &`.

## Open mode versus secure mode

`--secpol=open` does not enforce anything: every attach works there. Use it only to harvest a policy from `/dev/secpolgenerate`. If that device exists, you are in open mode. Secure mode needs a full system policy passed with `--policy`; a snippet on its own will not boot. Build it from an open-mode harvest plus your types.

## "File not found" for the binary after a reboot

`/tmp` on the QNX target is RAM. Everything copied there is gone after a boot. `resmgr-kit test` copies the binaries every run; if you deploy by hand, do it again after each boot.

## mkqnximage says "Nothing to do" or refuses the folder

`mkqnximage` refuses a non-empty folder and skips work when `output` already exists. Keep its build log outside the folder, and rebuild with `rm -rf output` first.

## ssh to the target does not answer

- Check the port: the config default is 2222. `ssh -p 2222 -i <key> root@127.0.0.1 uname -a` should print a line with `QNX` and `8.0`.
- The public key must have been given to `mkqnximage` with `--ssh-ident` when the image was built. A different key means a refused login.
- Allow about 12 seconds after QEMU starts (TCG emulation, no hardware acceleration).
- Another QEMU may already hold the port. Stop it or change `port` in the config.
- sshd crashed with memory faults when QEMU ran nested inside an x86 emulation layer on Apple Silicon. Run QEMU natively on the Mac instead.

## QEMU will not start the aarch64 image on Apple Silicon

The `startup-qemu-virt` image failed a GICv3 assertion under hvf, and hvf has no GICv2. TCG boots the kernel but the image lacked the virtio disk driver. The x86_64 image under TCG works and is what this tool targets. Newer QEMU also removed the `virt-4.2` machine type; use `-machine virt`.

## `cp` fails with extended attribute errors

On some shared file systems between a VM and the host, `cp` fails on extended attributes. Use `cat src > dst`.

## A shell variable holding the ssh command does not work in zsh

zsh does not split an unquoted string into words. Put the ssh call in a script or function instead of a variable.

## `test` runs but a config file in the project folder is ignored

By design. A config in the current folder is never read, since its `build_command` and `target_start` run in a shell. Use `~/.config/resmgr-kit/config.toml`, environment variables or `--config <file>`.

## Package missing after installing the SDP

Mirror the baseline again after the licence is activated. Mirroring before activation leaves the target package out. See [HOST-SETUP](HOST-SETUP.md).
