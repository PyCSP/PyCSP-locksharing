#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (c) 2018 John Markus Bjørndalen, jmb@cs.uit.no.
See LICENSE.txt for licensing details (MIT License).
"""
import time
import pycsp
from pycsp.utils import avg, handle_common_args
from pycsp import process, Parallel

# pylint: disable=invalid-name

handle_common_args()


@process
def writer(N, cout):
    "Write N messages to cout"
    for i in range(N):
        cout(i)


@process
def reader(N, cin):
    "Read N messages from cin"
    for _ in range(N):
        cin()


@process
def reader_verb(N, cin):
    "Read N messages from cin. Prints every message received."
    for _ in range(N):
        v = cin()
        print(v, end=" ")


# We're doing the timing inside the reader and writer procs to time the
# channel overhead without the process start/stop overhead.
# We add 10 write+reads as a warmup time and to make sure both are ready.
@process
def writer_timed(N, cout):
    """Writes N messages to cout.
    Returns a timestamp taken after 10 warmup messages."""
    for i in range(10):
        cout(i)
    t1 = time.time()
    for i in range(N):
        cout(i)
    return t1


@process
def reader_timed(N, cin):
    """Reades 10 + N messages from cin.
    Returns a timestamp taken after the last received mssages."""
    for _ in range(N + 10):
        cin()
    t2 = time.time()
    return t2


def run_timing(read_end, write_end):
    """Run benchmark with the provided ends of the channel"""
    dts = []
    for i in range(20):
        N = 1000
        print(f"  Run {i}:", end="")
        # t1 = time.time()
        t1, t2 = Parallel(
            writer_timed(N, write_end),
            reader_timed(N, read_end)).run().retval
        # t2 = time.time()
        dt_ms    = (t2 - t1) * 1000
        dt_op_us = (dt_ms / N) * 1000
        print(f"  DT    = {dt_ms:8.3f} ms  per op: {dt_op_us:8.3f} us")
        dts.append(dt_op_us)
    print(f" -- min {min(dts):.3f} avg {avg(dts):.3f} max {max(dts):.3f}")


print("Warming up")
NWARM = 10
chan = pycsp.Channel('a')
Parallel(writer(NWARM, chan.write),
         reader_verb(NWARM, chan.read)).run().retval
print("timing with channel ends")
run_timing(chan.read, chan.write)

print("timing with _read and _write directly")
run_timing(chan._read, chan._write)    # pylint: disable=protected-access
