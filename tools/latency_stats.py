#!/usr/bin/env python3
"""Summarise timer periods: one period in nanoseconds per line -> markdown table.

usage: python3 tools/latency_stats.py docs/evidence/latency-raw.txt [expected_us]
"""
import math
import statistics
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    with open(sys.argv[1]) as fh:
        us = sorted(int(line) / 1000 for line in fh if line.strip().isdigit())
    if not us:
        print("no periods found", file=sys.stderr)
        return 1
    expected = float(sys.argv[2]) if len(sys.argv) > 2 else None
    p = lambda q: us[min(len(us) - 1, math.ceil(q * len(us)) - 1)]  # nearest-rank
    rows = [("n", f"{len(us)}"), ("min", f"{us[0]:.1f} us"),
            ("mean", f"{statistics.fmean(us):.1f} us"), ("p50", f"{p(0.50):.1f} us"),
            ("p99", f"{p(0.99):.1f} us"), ("max", f"{us[-1]:.1f} us"),
            ("stdev", f"{statistics.stdev(us) if len(us) > 1 else 0:.1f} us")]
    if expected:
        rows.append(("max abs deviation from expected",
                     f"{max(abs(v - expected) for v in us):.1f} us"))
    print("| statistic | period |\n|---|---|")
    for k, v in rows:
        print(f"| {k} | {v} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
