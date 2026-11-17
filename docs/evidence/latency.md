# Pulse-timer period jitter on the QEMU target

> **Caveat:** QEMU under TCG emulation on a Mac, not hardware; numbers show the
> method, not real-time performance. Each guest instruction is translated on the
> host, and the host OS schedules the whole VM as ordinary processes, so the
> spread below is mostly emulation and host noise.

## What was measured

The time between consecutive pulses of a periodic timer, set up the same way
as the timer code `resmgr-kit gen` writes for a spec with a `timer:` section
(the vsensor and counter examples): `timer_create(CLOCK_MONOTONIC)` with a
`SIGEV_PULSE` event, here at a 10 ms period (100 Hz).

The helper [tools/timerjitter](../../tools/timerjitter/timerjitter.c) copies that
timer setup but receives the pulses with a plain `MsgReceivePulse` loop instead
of the dispatch layer, so it measures the timer and pulse delivery, not the
vsensor binary itself. Each pulse is stamped with
`clock_gettime(CLOCK_MONOTONIC)` right after it arrives; all periods are kept
in memory and printed after the run, so printing does not disturb the timing.

## Method

1. Build the helper with `qcc` (`make` in `tools/timerjitter` with the SDP
   environment sourced).
2. Copy it to the target and run `/tmp/timerjitter 2000 10000` (2000 periods of
   10000 us) at the default priority, with nothing else of ours running.
3. Save the output, one period in nanoseconds per line, as
   [latency-raw.txt](latency-raw.txt).
4. Summarise with `python3 tools/latency_stats.py docs/evidence/latency-raw.txt 10000`
   (nearest-rank percentiles, Python standard library only).

Target: QNX 8.0.0 x86_64 under QEMU (TCG) on an Apple Silicon Mac, run on
2026-11-17.

## Result

| statistic | period |
|---|---|
| n | 2000 |
| min | 7318.4 us |
| mean | 9999.6 us |
| p50 | 10017.0 us |
| p99 | 12341.9 us |
| max | 12917.1 us |
| stdev | 943.2 us |
| max abs deviation from expected | 2917.1 us |

## Reading it

- The mean is 9999.6 us for a 10000 us period: the timer does not drift. A late
  pulse is followed by a short period, because the timer fires on its own
  schedule and only the delivery of each pulse is late.
- Single periods range from 7.3 ms to 12.9 ms, p99 12.3 ms. That spread is what
  the emulated target shows, not what the same code does on a board.
- To get numbers that mean something, run the same two commands on real
  hardware, raise the helper's priority (`on -p 63 /tmp/timerjitter`), and
  compare the raw files.
