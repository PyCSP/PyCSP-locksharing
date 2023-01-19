#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

  Prefix ---- a ---->  Delta2 -- d --> consume
   ^                      |
   |                      |
   b                      |
   |                      |
  Succ <------- c --------|

"""

import os
import time
from pycsp.utils import handle_common_args
import pycsp
from pycsp import process, Parallel, Sequence
from pycsp.plugNplay import Prefix, Delta2, Successor, poison_chans

print("--------------------- Commstime --------------------")
handle_common_args()
Channel = pycsp.Channel    # in case command line arguments replaced the Channel def


@process
def consumer(cin, run_no):
    "Commstime consumer process"
    N = 5000
    ts = time.time
    t1 = ts()
    cin()
    t1 = ts()
    for _ in range(N):
        cin()
    t2 = ts()
    dt = t2 - t1
    tchan = dt / (4 * N)
    tchan_us = tchan * 1_000_000
    print(f"Run {run_no} DT = {dt:.4f}. Time per ch : {dt:.4f}/(4*{N}) = {tchan:.8f} s = {tchan_us:.4f} us")
    # print("consumer done, posioning channel")
    return tchan


def CommsTimeBM(run_no, Delta2=Delta2):
    # Create channels
    a = Channel("a")
    b = Channel("b")
    c = Channel("c")
    d = Channel("d")

    rets = Parallel(
        Prefix(c.read, a.write, prefixItem=0),  # initiator
        Delta2(a.read, b.write, d.write),       # forwarding to two
        Successor(b.read, c.write),             # feeding back to prefix
        Sequence(
            consumer(d.read, run_no),           # timing process
            poison_chans(a, b, c, d)),
    ).run().retval
    return rets[-1][0]  # return the results from consumer


def run_bm(Delta2=pycsp.plugNplay.Delta2):
    print(f"Running with Delta2 = {Delta2}")
    N_BM = 10
    tchans = []
    for i in range(N_BM):
        tchans.append(CommsTimeBM(i, Delta2))
    print("Min {:7.3f}  Avg {:7.3f} Max {:7.3f}".format(1_000_000 * min(tchans),
                                                        1_000_000 * sum(tchans) / len(tchans),
                                                        1_000_000 * max(tchans)))


run_bm(pycsp.plugNplay.ParDelta2)
run_bm(pycsp.plugNplay.SeqDelta2)
run_bm(pycsp.plugNplay.AltDelta2)
# A bit of a hack, but windows does not have uname()
try:
    os.uname()
except AttributeError:
    print("Sleeping for a while to allow MS Windows users to read benchmark results")
    time.sleep(15)


def run_cprofile():
    import cProfile
    cProfile.run("commstime_bm()", 'commstime.prof')
    import pstats
    p = pstats.Stats('commstime.prof')
    p.strip_dirs().sort_stats('cumtime').print_stats()
