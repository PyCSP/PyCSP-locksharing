#!/usr/bin/env python3

# ############################################################

import time
import random
from pycsp.utils import handle_common_args
import pycsp
from pycsp import process, Alternative, Parallel

handle_common_args()
Channel = pycsp.Channel    # in case channel was replaced by command line options


def gen_id_vals(pid, num):
    return [(pid, v) for v in range(num)]


def test_2_readers_and_writers():
    print("************************************************************")
    print("Simple channel test with 2 readers and writers")

    N_VALS = 10

    @process
    def writer(p, ch):
        pref = " " * p * 2
        for val in gen_id_vals(p, N_VALS):
            print(f"{pref} W {p} -> {val}")
            ch.write(val)
            print(f"{pref} W {p} done")
            time.sleep(random.random() * 0.5 + 0.5)

    @process
    def reader(p, ch):
        pref = "                     " + " " * p * 2
        time.sleep(0.1)
        rvals = []
        for _ in range(N_VALS):
            print(f"{pref} R {p} waiting")
            val = ch.read()
            rvals.append(val)
            print(f"{pref} R {p} got {val}")
            time.sleep(random.random() * 0.5 + 0.5)
        return rvals

    ch = Channel()
    rets = Parallel(
        writer(1, ch),
        reader(1, ch),
        writer(2, ch),
        reader(2, ch)).run().retval
    print("All done")
    # return vals from reader 1 and 2
    rvals1, rvals2 = rets[1], rets[3]
    print(rvals1)
    print(rvals2)
    expected = sorted(gen_id_vals(1, N_VALS) + gen_id_vals(2, N_VALS))
    received = sorted(rvals1 + rvals2)
    assert received == expected, "Expected output to match input {expected} {received}"


def test_guarded_channel_ops():
    """This should be equivalent with test_2_readers_and_writers, except
    one of the readers and one of the readers use an alt (with only read
    end and a tentative write to the write end_time as parameters.
    """
    print("************************************************************")
    print("Simple guarded channel test")

    N_VALS = 10
    # Instead of poisoning and counting, use a termination token.
    TERMINATE = "terminate"

    @process
    def writer(p, cout):
        pref = " " * p * 2
        for val in gen_id_vals(p, N_VALS):
            print(f"{pref} W {p} -> {val}")
            cout(val)
            print(f"{pref} W {p} write done")
            time.sleep(random.random() * 0.5 + 0.5)
        print(f"{pref} W {p} finishing")
        cout(TERMINATE)

    @process
    def reader(p, cin):
        pref = " " * p * 2
        rvals = []
        for i, m in enumerate(cin):
            print(f"{pref} R  {p} got {m} {i}")
            if m == TERMINATE:
                break
            rvals.append(m)
        return rvals

    @process
    def gwrite(p, cout):
        pref = " " * p * 2
        for val in gen_id_vals(p, N_VALS):
            print(f"{pref} AW {p} -> {val}")
            g = cout.alt_pending_write(val)
            alt = Alternative(g)
            alt.select()
            print(f"{pref} AW {p} done")
            time.sleep(random.random() * 0.5 + 0.5)
        print(f"{pref} AW {p} finishing")
        cout(TERMINATE)

    @process
    def gread(p, cin):
        pref = " " * p * 2
        alt = Alternative(cin)
        rvals = []
        while True:
            print(f"{pref} AR  {p} waiting")
            with alt as (g, val):
                print(f"{pref} AR  {p} got {val} from {g}")
                if val == TERMINATE:
                    break
                rvals.append(val)
        return rvals

    ch = Channel()
    rets = Parallel(
        writer(1, ch.write),
        gwrite(2, ch.write),
        reader(3, ch.read),
        gread(4, ch.read)
    ).run().retval
    print("All done")
    # return vals from reader 1 and 2
    rvals1, rvals2 = rets[2], rets[3]
    print(rvals1)
    print(rvals2)
    expected = sorted(gen_id_vals(1, N_VALS) + gen_id_vals(2, N_VALS))
    received = sorted(rvals1 + rvals2)
    assert received == expected, "Expected output to match input {expected} {received}"


if __name__ == '__main__':
    test_2_readers_and_writers()
    test_guarded_channel_ops()
