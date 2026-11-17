# Your first QNX 8.0 resource manager, tested on QEMU, in 15 minutes

| | |
|---|---|
| What you will learn | How a QNX 8.0 resource manager is put together (`dispatch_create`, `resmgr_attach`, iofunc handlers, a devctl, a pulse timer), how to build it with `qcc`, run it on a QNX target and test the live `/dev` path from your host, and what its security-policy and image build-file pieces look like |
| Prerequisites | QNX SDP 8.0 with `qcc` (free non-commercial licence), a QNX 8.0 x86_64 QEMU target reachable by ssh, Python 3.11+, git |
| Time | 15 minutes with a ready host; about 60 minutes if you still have to set up the host and target ([HOST-SETUP.md](HOST-SETUP.md)) |

You will write a new device, `/dev/counter0`, from a 15-line YAML spec. A read
returns how many 100 ms ticks have passed; a devctl called `RESET` sets the
count back. `resmgr-kit` turns the spec into C, builds it with `qcc`, copies it
to a QNX 8.0 target running in QEMU, starts it and runs a generated test suite
against it from your machine. You finish with a green test run on the target.

Every command below was run in this order on a macOS host against the QNX 8.0
x86_64 QEMU target. The outputs are real; only local paths are shortened, and
the pytest header and path lines are trimmed. Times vary from run to run.

## Before you start (prerequisites)

Time: 0 minutes if your host is set up, about 60 minutes if not.

- A QNX SDP 8.0 install with `qcc` (free non-commercial licence from myQNX).
- A QNX 8.0 x86_64 target in QEMU that answers ssh. [HOST-SETUP.md](HOST-SETUP.md)
  walks through both, for Linux x86_64 and macOS hosts.
- Python 3.11 or newer and git.
- A settings file at `~/.config/resmgr-kit/config.toml` that says how to build
  and how to reach the target. Step 2 shows one.

All commands run in bash or zsh from the folder named in each step.

## Step 1: Install resmgr-kit (2 min)

```bash
git clone https://github.com/Tharun2075/resmgr-kit.git
cd resmgr-kit
python3 -m venv .venv && .venv/bin/pip install -q -e .
.venv/bin/resmgr-kit --version
```

pip may print a "new release of pip is available" notice; it is harmless.

```text
Cloning into 'resmgr-kit'...
resmgr-kit 0.1.0
```

## Step 2: Check you can reach the target (1 min)

The settings file is yours, not part of the repo, so create it first. Change
the values to match your host (this sample uses generic placeholders):

```bash
mkdir -p ~/.config/resmgr-kit
cat > ~/.config/resmgr-kit/config.toml <<'EOF'
# Local settings for resmgr-kit test (not part of the repo).
build_command = "source ~/qnx800/qnxsdp-env.sh && make -C {dir}"
target = "root@127.0.0.1"
port = 2222
ssh_key = "~/.ssh/qnx_week1"
target_start = "<path to your QEMU start script> start"
EOF
```

`build_command` is any shell command that runs `make` in `{dir}` with the QNX
environment sourced. `ssh_key` is the key HOST-SETUP.md created; replace it with
yours. `target_start` must boot the QEMU target and exit 0 once ssh answers; it
is optional if QEMU is already running (leave the line out). `resmgr-kit sh` runs
one command on the target with these settings.

Check it (the sample output below is from a setup whose `build_command` runs
inside a Linux VM that holds the SDP, so your `build_command` line will differ):

```bash
cat ~/.config/resmgr-kit/config.toml
.venv/bin/resmgr-kit sh 'uname -a'
```

```text
# Local settings for resmgr-kit test (not part of the repo).
build_command = "orb run -m qnx-host bash -lc \"source ~/qnx800/qnxsdp-env.sh >/dev/null && cd '{dir}' && make\""
target = "root@127.0.0.1"
port = 2222
ssh_key = "~/.ssh/qnx_week1"
target_start = "<path to your QEMU start script> start"
QNX noname 8.0.0 2026/10/30-09:10:05EDT x86pc x86_64
```

On a Linux host with the SDP installed locally, `build_command` can be just
`source ~/qnx800/qnxsdp-env.sh && make -C {dir}`. If `uname` does not answer,
see "ssh to the target does not answer" in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Step 3: Look at what the generator writes (1 min)

Start with the example that ships with the repo, a virtual sensor.

```bash
.venv/bin/resmgr-kit gen examples/vsensor/vsensor.yaml -o build/vsensor
```

```text
build/vsensor/vsensor.c
build/vsensor/vsensor.h
build/vsensor/vsensor_client.c
build/vsensor/Makefile
build/vsensor/vsensor.build
build/vsensor/vsensor.secpol
build/vsensor/tests/test_vsensor.py
```

One spec gives you the server, a small client for devctls, a `qcc` Makefile, an
image fragment, a security policy snippet and a pytest suite.

## Step 4: Write the spec for your device (2 min)

Your device keeps one number, `count`. A timer adds 1 every 100 ms, and a read
prints it.

Stay in the `resmgr-kit` folder (`mydev` is created inside the repo).

```bash
mkdir -p mydev
cat > mydev/counter.yaml <<'EOF'
# Tick counter: a read returns how many 100 ms ticks have passed since start
# or since the last RESET; RESET sets the count (send 0 to start over).
name: counter
path: /dev/counter0
description: Tick counter with a RESET devctl
state:
  - {name: count, type: uint32, init: 0}
read:
  fields: [count]
timer:
  period_ms: 100
  actions:
    - {op: inc, field: count}
EOF
```

No output means the file is written. `type: uint32` gives `count` the range
0 to 4294967295; `resmgr-kit` checks every value against it.

## Step 5: Generate the C and find the QNX calls (1 min)

```bash
.venv/bin/resmgr-kit gen mydev/counter.yaml
grep -n 'resmgr_attach(\|pulse_attach(\|timer_create(\|SIGEV_PULSE_INIT' build/counter/counter.c
```

```text
build/counter/counter.c
build/counter/counter.h
build/counter/counter_client.c
build/counter/Makefile
build/counter/counter.build
build/counter/counter.secpol
build/counter/tests/test_counter.py
186:    id = resmgr_attach(dpp, &rattr, COUNTER_PATH, _FTYPE_ANY, 0,
197:        code = pulse_attach(dpp, MSG_FLAG_ALLOC_PULSE, 0, on_tick, NULL);
203:        SIGEV_PULSE_INIT(&ev, coid, SIGEV_PULSE_PRIO_INHERIT, code, 0);
204:        if (timer_create(CLOCK_MONOTONIC, &ev, &tick_timer) == -1) {
```

`resmgr_attach` puts `/dev/counter0` in the path space. The timer does not use a
thread or a signal handler: `timer_create` sends a pulse, the dispatch loop
receives it like any other message and calls `on_tick`, so the tick and the
reads never run at the same time and need no lock. Open `counter.c` and read
`io_read` and `on_tick`; they are short.

## Step 6: Build, deploy and test on the target (2 min)

```bash
.venv/bin/resmgr-kit test mydev/counter.yaml
```

```text
== gen mydev/counter.yaml -> .../build/counter
== build
qcc -Vgcc_ntox86_64 -Wall -O2 -o counter counter.c
qcc -Vgcc_ntox86_64 -Wall -O2 -o counter_client counter_client.c
== target
target: reachable
== deploy
== start
/dev/counter0 is up
== pytest
collecting ... collected 7 items

tests/test_counter.py::test_path_exists PASSED                           [ 14%]
tests/test_counter.py::test_read_format PASSED                           [ 28%]
tests/test_counter.py::test_read_values_in_range PASSED                  [ 42%]
tests/test_counter.py::test_read_is_bounded PASSED                       [ 57%]
tests/test_counter.py::test_timer_updates_state PASSED                   [ 71%]
tests/test_counter.py::test_unknown_devctl_is_enotty PASSED              [ 85%]
tests/test_counter.py::test_write_is_refused PASSED                      [100%]

============================== 7 passed in 3.16s ===============================
== target info
QNX noname 8.0.0 2026/10/30-09:10:05EDT x86pc x86_64
junit: .../build/counter/junit.xml
== stop
```

The tests ran on your machine and talked to the real device on QNX over ssh.
They checked the read format and range, that the timer moves the count, that an
unknown devctl gets `ENOTTY` and that a write is refused (the spec has no
`write:` section, so the device is read-only, mode `cr--r--r--`).

## Step 7: Add the RESET devctl and test again (2 min)

```bash
cat >> mydev/counter.yaml <<'EOF'
devctls:
  - {name: RESET, code: 1, op: set, field: count}
  - {name: GET_COUNT, code: 2, op: get, field: count}
EOF
.venv/bin/resmgr-kit test mydev/counter.yaml
```

```text
collecting ... collected 10 items

tests/test_counter.py::test_path_exists PASSED                           [ 10%]
tests/test_counter.py::test_read_format PASSED                           [ 20%]
tests/test_counter.py::test_read_values_in_range PASSED                  [ 30%]
tests/test_counter.py::test_read_is_bounded PASSED                       [ 40%]
tests/test_counter.py::test_timer_updates_state PASSED                   [ 50%]
tests/test_counter.py::test_reset_round_trip PASSED                      [ 60%]
tests/test_counter.py::test_get_count_get PASSED                         [ 70%]
tests/test_counter.py::test_undersized_devctl_is_einval PASSED           [ 80%]
tests/test_counter.py::test_unknown_devctl_is_enotty PASSED              [ 90%]
tests/test_counter.py::test_write_is_refused PASSED                      [100%]

============================== 10 passed in 4.55s ==============================
```

Three new tests came from the two lines you added: a set round trip for
`RESET`, a get for `GET_COUNT`, and a check that a devctl with too small a
payload gets `EINVAL` instead of reading past the buffer.

## Step 8: Use the device by hand (1 min)

`test` stops the server when it is done, but the binaries stay in `/tmp` on the
target. Start it again and talk to it.

```bash
.venv/bin/resmgr-kit sh '/tmp/counter </dev/null >/tmp/counter.log 2>&1 & sleep 2; cat /dev/counter0'
.venv/bin/resmgr-kit sh '/tmp/counter_client RESET 0; cat /dev/counter0; sleep 1; /tmp/counter_client GET_COUNT'
.venv/bin/resmgr-kit sh 'slay -f counter; sleep 1; ls /dev/counter0 || echo counter0 is gone'
```

```text
count=20
ok value=0
count=0
ok value=11
ls: /dev/counter0: No such file or directory
counter0 is gone
```

Two seconds of 100 ms ticks gave about 20 (yours may differ a little). `RESET 0`
set it to 0, and a second later `GET_COUNT` read about 10 (10 to 12 is normal;
the reply includes ssh time). After `slay` the path
is gone, because the path space entry belongs to the process.

## Step 9: Turn the security policy on (2 min to read)

QNX 8.0 can run with a security policy (secpol) that says which process types
may attach which paths. The generator wrote a snippet for your device:

The real file starts with a few generated comment lines, omitted here.

```bash
cat build/counter/counter.secpol
```

```text
type counter_t;

allow counter_t self:ability {
    pathspace
    prot_exec
    map_fixed
    public_channel
};

# Only this path may be attached by counter_t.
allow_attach counter_t { /dev/counter0 };

# Launcher type (e.g. user_root_t) also needs: allow <launcher_t> self:ability { settypeid:counter_t channel_connect:counter_t };
```

To use it, add the snippet to the policy source of a secpol image, compile it
with `secpolcompile`, and start the server with `on -T counter_t /tmp/counter`.
`resmgr-kit test` does not do this for you: the default QEMU image runs without
secpol. Two things trip people up, and both are in
[TROUBLESHOOTING.md](TROUBLESHOOTING.md): "The resource manager will not attach
with the security policy on" (missing `allow_attach` or the launcher rule) and
"Open mode versus secure mode" (secure mode needs a full system policy, so
start from one harvested in open mode and merge this snippet into it).

## Step 10: Compare with the finished example (under 1 min)

```bash
diff mydev/counter.yaml examples/counter/counter.yaml && echo "same as the finished example"
```

```text
same as the finished example
```

[examples/counter/counter.yaml](../examples/counter/counter.yaml) is the spec
you just wrote. `resmgr-kit test examples/counter/counter.yaml` runs the same
10 tests.

## What you learned

- A QNX resource manager is a process that owns a path; `resmgr_attach` claims
  it and `slay` gives it back.
- A periodic job fits in the same dispatch loop as reads and devctls when the
  timer delivers a pulse, so no locks are needed.
- A devctl is a numbered request with a fixed payload; the server must reject
  short payloads and unknown codes.
- Testing on the target from the host with pytest over ssh catches what host
  tests cannot: the real path, mode and errno values on QNX 8.0.
- secpol limits a process to the paths and abilities you name.

## Next steps

- Change `period_ms: 100` to `period_ms: 10`, run `test` again, and repeat
  step 8: the count now climbs ten times faster.
- Read [examples/vsensor/vsensor.yaml](../examples/vsensor/vsensor.yaml) for
  ranged fields, a rate set by devctl and clamping.
- Read [examples/estop/estop.yaml](../examples/estop/estop.yaml) for a devctl
  that waits for an event and gets a pulse back.
- See how steady the pulse timer is on your target:
  [evidence/latency.md](evidence/latency.md).
- [ARCHITECTURE.md](../ARCHITECTURE.md) shows how the generator is built.
