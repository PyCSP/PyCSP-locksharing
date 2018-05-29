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

from common import *
from pycsp import *
from pycsp.plugNplay import *
import os
import time
import pycsp

print("--------------------- Commstime --------------------")
handle_common_args()

@process
def consumer(cin, run_no):
    "Commstime consumer process"
    N = 5000
    ts = time.time
    t1 = ts()
    cin()
    t1 = ts()
    for i in range(N):
        cin()
    t2 = ts()
    dt = t2-t1
    tchan = dt / (4 * N)
    print("Run %d DT = %f.  Time per ch : %f/(4*%d) = %f s = %f us" % \
          (run_no, dt, dt, N, tchan, tchan * 1000000))
    #print("consumer done, posioning channel")
    cin.poison()
    print("consumer done with poison")
    return tchan

def CommsTimeBM(run_no, Delta2=Delta2):
    # Create channels
    a = Channel("a")
    b = Channel("b")
    c = Channel("c")
    d = Channel("d")

    rets = Parallel(Prefix(c.read, a.write, prefixItem = 0),  # initiator
                    Delta2(a.read, b.write, d.write),         # forwarding to two
                    Successor(b.read, c.write),               # feeding back to prefix
                    consumer(d.read, run_no))                 # timing process
    return rets[-1]

def run_bm(Delta2=pycsp.plugNplay.Delta2):
    print(f"Running with Delta2 = {Delta2}")
    N_BM = 10
    tchans = []
    for i in range(N_BM):
        print(f"Iter {i}")
        tchans.append(CommsTimeBM(i, Delta2))
    print("Min {:7.3f}  Avg {:7.3f} Max {:7.3f}".format(1_000_000 * min(tchans),
                                                        1_000_000 * sum(tchans)/len(tchans), 
                                                        1_000_000 * max(tchans)))

run_bm(pycsp.plugNplay.ParDelta2)
run_bm(pycsp.plugNplay.SeqDelta2)
# A bit of a hack, but windows does not have uname()
try:
    os.uname()
except:
    print("Sleeping for a while to allow windows users to read benchmark results")
    time.sleep(15)

def run_cprofile():
    import cProfile
    cProfile.run("commstime_bm()", 'commstime.prof')
    import pstats
    p = pstats.Stats('commstime.prof')
    p.strip_dirs().sort_stats('cumtime').print_stats()
