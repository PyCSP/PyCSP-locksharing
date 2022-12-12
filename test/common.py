#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2018 John Markus Bjørndalen, jmb@cs.uit.no.
# See LICENSE.txt for licensing details (MIT License).

import argparse
import sys
sys.path.append("..")   # Trick to import pycsp without setting PYTHONPATH
import common_exp    # noqa E402  -- suppress flake8 warning
import pycsp         # noqa E402

# Common arguments are added and handled here. The general outline for a program is to
# use common.handle_common_args() with a list of argument specs to add.

argparser = argparse.ArgumentParser()
argparser.add_argument("-rw_deco", help='use decorators for read/write ops on channels', action='store_const', const=True, default=False)
argparser.add_argument("-rw_ctxt", help='use context manager for read/write ops on channels', action='store_const', const=True, default=False)
argparser.add_argument("-rw_ctxt2", help='use context manager in the channel for read/write ops on channels', action='store_const', const=True, default=False)
argparser.add_argument("-cfut1", help="use CFuture1 as a replacement for CFuture", action='store_const', const=True, default=False)
# Workaround for pytest and argparse both trying to parse arguments.
argparser.add_argument("-v", help="hiding pytest's -v argument", action='store_const', const=True, default=False)


def handle_common_args(argspecs=None):
    """argspecs is a list of arguments for argparser.add_argument, with
    each item a tuple of (*args, **kwargs).
    Returns the parsed args.
    """
    global args
    if argspecs is None:
        argspecs = []
    for spec in argspecs:
        argparser.add_argument(*spec[0], **spec[1])
    args = argparser.parse_args()
    if args.rw_deco:
        common_exp.set_channel_rw_decorator()
    if args.rw_ctxt:
        common_exp.set_channel_contextmgr()
    if args.rw_ctxt2:
        common_exp.set_channel_contextmgr2()
    if args.cfut1:
        print("Using CFuture = CFuture1")
        pycsp.cfutures.CFuture_new = pycsp.cfutures.CFuture
        pycsp.cfutures.CFuture = pycsp.cfutures.CFuture1
        pycsp.CFuture = pycsp.cfutures.CFuture1
    return args


def avg(vals):
    "Returns the average of values"
    return sum(vals) / len(vals)
