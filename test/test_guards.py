#!/usr/bin/env python3

# ############################################################

import time
import random
import itertools
from common import handle_common_args
import pycsp
from pycsp import process, Alternative, Sequence

import sys
print(sys.argv)
handle_common_args()
Channel = pycsp.Channel    # in case channel was replaced by command line options


def test_timer():
    print("Checking if Timer() guards can wake up")

    @process
    def timeout_reader(pn, ch):
        t1 = pycsp.Timer(0.25)
        t2 = pycsp.Timer(1)
        alt = Alternative(ch.read, t1, t2)
        for i in range(5):
            print(" - about to wait with a timeout", i)
            g, ret = alt.select()
            if isinstance(g, pycsp.Timer):
                print("    - done", g, g.seconds)
            else:
                print("    - done", g, g.seconds)

    ch = Channel()
    Sequence(timeout_reader(1, ch))

# TODO:
# - no way of checking for deadlocks (like in go).
# - alternative is to use some kind of timeout (just use an alt with timeout to wayt for a test?) 
# - the above doesn't work. Old timers will be disabled?  I get disable on 0.25 and 1.0 sec timers.
# - pytest and argparser don't work well together.

if __name__ == "__main__":
    test_timer()
