#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import pycsp                                      # noqa : E402
from pycsp import process, Parallel               # noqa : E402
from pycsp.utils import handle_common_args, avg

print("--------------------- Producer/consumer --------------------")
args = handle_common_args([
    (("-profile",), dict(help="profile", action="store_const", const=True, default=False)),
])
Channel = pycsp.Channel    # in case command line arguments replaced the Channel def


@process
def producer(cout, n_warm, n_runs):
    for i in range(n_warm):
        cout(i)
    for i in range(n_runs):
        cout(i)


@process
def consumer(cin, n_warm, n_runs, run_no):
    for _ in range(n_warm):
        cin()
    ts = time.time
    t1 = ts()
    for _ in range(n_runs):
        cin()
    t2 = ts()
    dt = (t2 - t1) * 1_000_000  # in microseconds
    per_rw = dt / n_runs
    print(f"Run {run_no} DT = {dt:f} us. Time per rw {per_rw:7.3f} us")
    return per_rw


def run_bm():
    N_BM = 10
    N_WARM = 100
    N_RUN   = 10_000
    chan = Channel('prod/cons')

    res = []
    for i in range(N_BM):
        rets = Parallel(
            producer(chan.write, N_WARM, N_RUN),
            consumer(chan.read, N_WARM, N_RUN, i)).run().retval
        # print(rets)
        res.append(rets[-1])
    print("Res with min, avg, max")
    print(f"| producer-consumer | {min(res):7.3f} | {avg(res):7.3f} |{max(res):7.3f} |")
    return rets


if __name__ == "__main__":
    run_bm()
    if args.profile:
        import cProfile
        cProfile.run("run_bm()", sort='tottime')
        # cProfile.run("run_bm()", sort='cumtime')
