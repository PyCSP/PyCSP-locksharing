#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contains common CSP processes such as Id, Delta, Prefix etc.

Copyright (c) 2018 John Markus Bjørndalen, jmb@cs.uit.no.
See LICENSE.txt for licensing details (MIT License).
"""

from pycsp import process, Alternative, Parallel


@process
def Identity(cin, cout):
    """Copies its input stream to its output stream, adding a one-place buffer
    to the stream."""
    for t in cin:
        cout(t)


@process
def Prefix(cin, cout, prefixItem=None):
    t = prefixItem
    cout(t)
    for t in cin:
        cout(t)


@process
def SeqDelta2(cin, cout1, cout2):
    """Sequential version of Delta2.
    This version is much faster than ParDelta2 in smaller benchmarks since it has less overhead,
    but there is one major drawback of it: a slow process attached to cout1 would make the process
    attached to cout2 wait for cout1 to complete."""
    for t in cin:
        cout1(t)
        cout2(t)


# ParDelta2 issues.
#
# JCSP reuses threads for which, which may reduce some of the overhead.
# Python threads are not as easy to restart.
#
# One option is to set up a reader process that passes the message to two
# writer processes. Essentially composing a Par(reader, Par(writer, writer)).
#
# The question is how to send data from the reader to the writers:
# - Using a channel would essentially just create SeqDelta2 with more overhead, apart from one thing:
#   The writer processes effectively become length 1 buffers, so the reader is able to start getting
#   the new message before both writers complete. This would change the semantics.
#   To remedy this, the writers would have to send a message back to reader (using an additional channel)
#   after then have passed on the message on the output channel.
# - using barriers:
#   - writers join barrier (a)
#   - read from cin, set value on shared state (single writer, multiple readers)
#   - join barrier (a) with the writers
#   - everyone released:
#     - read end joins the (b) barrier
#     - writers copy the value and write it to their output channels, then join the (b) barrier.
#   This complicates termination and poison handling.
# The better solution is probably to use AltDelta2. It is simpler to reason about and has
# less overhead.
@process
def ParDelta2(cin, cout1, cout2):
    """Parallel version of Delta2.
    Warning: there is some significant overhead here as 2 internal writer processes + a
    Parallel process are created for every message read on 'cin'.
    This means starting, ending and joining with 3 threads per iteration.
    See comments for more information.
    """
    @process
    def writer(ch, val):
        ch(val)

    for t in cin:
        Parallel(
            writer(cout1, t),
            writer(cout2, t),
            check_poison=True
        )


@process
def AltDelta2(cin, cout1, cout2):
    """Delta2 that emulates a parallel write by using an alt to write to the outputs
    in the order they are ready.
    """
    for t in cin:
        # Pick which to write to first by using the alt
        g1 = cout1.alt_pending_write(t)
        g2 = cout2.alt_pending_write(t)
        alt = Alternative(g1, g2)
        g, ret = alt.select()
        # One write done. Copy to the other channel.
        if g == g1:
            cout2(t)
        else:
            cout1(t)


# JCSP version uses the parallel version, so we do the same.
Delta2 = ParDelta2


@process
def Successor(cin, cout):
    """Adds 1 to the value read on the input channel and outputs it on the output channel.
    Infinite loop.
    """
    for t in cin:
        cout(t + 1)


@process
def SkipProcess():
    pass


@process
def Mux2(cin1, cin2, cout):
    alt = Alternative(cin1, cin2)
    while True:
        _, val = alt.priSelect()
        cout(val)
