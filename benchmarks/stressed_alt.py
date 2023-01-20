#!/usr/bin/env python3

# Based on the version from
# https://github.com/kevin-chalmers/cpp-csp/blob/master/demos/stressedalt.cpp
# https://www.researchgate.net/publication/315053019_Development_and_Evaluation_of_a_Modern_CCSP_Library

import time
from pycsp import process, Alternative, Parallel, PoisonException, Channel

N_RUNS    = 10
N_SELECTS = 10000
N_CHANNELS = 10
N_PROCS_PER_CHAN = 1000


@process
def stressed_writer(cout, ready, done, writer_id):
    "Stressed alt writer"
    try:
        ready(writer_id)
        while True:
            cout(writer_id)
    except PoisonException:
        done(writer_id)


@process
def stressed_reader(channels, ready, done, n_writers, writers_per_chan):
    """Measure the time to run either 'async with alt' or 'alt.select.
    """
    print("Waiting for all writers to send going")
    for _ in range(n_writers):
        ready()
    print("- writers ready, reader almost ready")

    print("Setting up alt with")
    print(f"- procs/writers per channel     : {writers_per_chan}")
    print(f"- number of channels            : {len(channels)}")
    print(f"- total number of procs/writers : {writers_per_chan * len(channels)}")
    alt = Alternative(*[ch.read for ch in channels])

    print("Select using 'with alt': ")
    for run in range(N_RUNS):
        t1 = time.time()
        for _ in range(N_SELECTS):
            with alt as (_, _):
                # The selected read operation is already executed. No need to do more.
                pass
        t2 = time.time()
        dt = t2 - t1
        us_per_select = 1_000_000 * dt / N_SELECTS
        print(f"Run {run:2}, {N_SELECTS} iters, {us_per_select} us per select/iter")

    print("Select using alt.select() : ")
    for run in range(N_RUNS):
        t1 = time.time()
        for _ in range(N_SELECTS):
            alt.select()
        t2 = time.time()
        dt = t2 - t1
        us_per_select = 1_000_000 * dt / N_SELECTS
        print(f"Run {run:2}, {N_SELECTS} iters, {us_per_select} us per select/iter")

    print("Poison channels")
    for ch in channels:
        ch.poison()
    print("Done, witing for writers to terminate")
    for _ in range(n_writers):
        done()
        # print(f"Got termination from {i} {res}")
    print("- writers terminated")


def run_bm():
    """Sets up and runs the benchmark"""
    print("--------------------- Stressed Alt --------------------")
    ready = Channel("ready")
    chans = [Channel(f'ch {i}') for i in range(N_CHANNELS)]
    done = Channel("done")
    procs = []
    for cno, ch in enumerate(chans):
        for c_pid in range(N_PROCS_PER_CHAN):
            writer_id = (cno, c_pid)
            procs.append(stressed_writer(ch.write, ready.write, done.write, writer_id))
    procs.append(stressed_reader(chans, ready.read, done.read, N_CHANNELS * N_PROCS_PER_CHAN,  N_PROCS_PER_CHAN))
    Parallel(*procs).run()


run_bm()
