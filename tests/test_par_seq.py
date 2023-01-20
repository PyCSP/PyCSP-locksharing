#!/usr/bin/env python3
"""Testing parallel and sequence constructs.
"""

import random
import time
import itertools
from pycsp import process, Parallel, Sequence, CSP


def flatten(seq):
    """Flatten a sequence of type tuple or list by recursively yielding values that are
    not lists or tuples."""
    for val in seq:
        if isinstance(val, (tuple, list)):
            yield from flatten(val)
        else:
            yield val


@process
def printer(msg):
    "Print a message and return it"
    time.sleep(0.05 + random.random() * 0.05)
    print(msg)
    return msg


def test_comp_seq():
    """Test of composing sequences"""
    print("\nTest composing sequence")
    print("----------------------")
    msgs = []

    def mkmsg(lvl):
        num = next(counter)
        msg = f"msg-{num}-{lvl}"
        msgs.append(msg)
        return printer(msg)

    counter = itertools.count(start=1)
    rets = Sequence(
        mkmsg(1),
        Sequence(
            mkmsg(2),
            mkmsg(2),
            mkmsg(2),
            Sequence(
                mkmsg(3),
                mkmsg(3)),
            mkmsg(2),
            Sequence(
                mkmsg(3),
                mkmsg(3))),
        mkmsg(1)).run().retval

    print("Done")
    frets = list(flatten(rets))
    # print(rets)
    # print(frets)
    assert frets == msgs, "The list of created messages should be equal to the list of messages created the composed set of sequences"


def test_comp_par():
    """Test of composing par"""
    print("\nTest composing par. The messages will probably be printed out of order")
    print("\nbut should be returned in-order.")
    print("----------------------")
    msgs = []

    def mkmsg(lvl):
        num = next(counter)
        msg = f"msg-{num}-{lvl}"
        msgs.append(msg)
        return printer(msg)

    counter = itertools.count(start=1)
    rets = Parallel(
        mkmsg(1),
        Parallel(
            mkmsg(2),
            mkmsg(2),
            mkmsg(2),
            Parallel(
                mkmsg(3),
                mkmsg(3)),
            mkmsg(2),
            Parallel(
                mkmsg(3),
                mkmsg(3))),
        mkmsg(1)).run().retval

    print("Done")
    frets = list(flatten(rets))
    # print(rets)
    # print(frets)
    # Parallel and ParallelComp returns the result in the same order as the specified processes, so
    # the results should be in the same order as in msgs (same as with Sequence and SequenceComp).
    assert frets == msgs, "The list of created messages should be equal to the list of messages created the composed set of processes"


def test_CSP():
    """Tests that the CSP function works as expected"""
    print("\nTesting the CSP convenience function.")
    print("--------------------------")
    res1 = CSP(printer("haha"))
    res2 = CSP(Sequence(printer("haha")))
    res3 = CSP(printer(1), printer(2), printer(3))

    assert res1 == "haha"
    assert res2[0] == "haha"
    assert res3 == [1, 2, 3]


if __name__ == "__main__":
    test_comp_seq()
    test_comp_par()
    test_CSP()
