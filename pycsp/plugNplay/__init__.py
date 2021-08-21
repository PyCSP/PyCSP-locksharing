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
    """Sequential version of Delta2"""
    for t in cin:
        cout1(t)
        cout2(t)


@process
def ParDelta2(cin, cout1, cout2):
    """Parallel version of Delta2"""
    @process
    def writer(ch, val):
        ch(val)

    for t in cin:
        # NB: cout1(t) generates a coroutine, which is equivalent with a CSP process.
        # This is therefore safe to do.
        Parallel(
            writer(cout1, t),
            writer(cout2, t),
            check_poison=True
        )


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
        ch, val = alt.priSelect()
        cout(val)
