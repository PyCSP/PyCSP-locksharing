#!/usr/bin/env python3

# ############################################################

from pycsp.utils import handle_common_args
import pycsp
from pycsp import process, Alternative, Sequence
handle_common_args()
Channel = pycsp.Channel    # in case channel was replaced by command line options


def test_timer():
    """Testing the timer guard"""
    print("\nChecking if Timer() guards can wake up")
    print("------------------")

    @process
    def timeout_reader(pn, ch):
        t1 = pycsp.Timer(0.25)
        t2 = pycsp.Timer(1)
        alt = Alternative(ch.read, t1, t2)
        for i in range(5):
            print(" - about to wait with a timeout", i)
            g, ret = alt.select()
            assert g in (t1, t2), "There is no writer on the channel, so should only get timeouts"
            assert g == t1, "Timer t1 is faster than t2, so it should always be picked"
            print("    - done", g)

    ch = Channel()
    Sequence(timeout_reader(1, ch)).run()


def test_skip():
    """Testing the skip guard"""
    print("\nChecking if skip is always selected in an alt where nobody else is ready")
    print("------------------")

    @process
    def timeout_reader(pn, ch):
        skip = pycsp.Skip()
        # Put skip last to make sure it is the last option
        alt = Alternative(ch.read, skip)
        for i in range(50):
            g, ret = alt.select()
            assert g == skip, "Should always pick skip"

    ch = Channel()
    Sequence(timeout_reader(1, ch)).run()


# TODO:
# - no way of checking for deadlocks (like in go).
# - alternative is to use some kind of timeout (just use an alt with timeout to wayt for a test?)
# - the above doesn't work. Old timers will be disabled?  I get disable on 0.25 and 1.0 sec timers.
# - pytest and argparser don't work well together.

if __name__ == "__main__":
    test_timer()
    test_skip()
