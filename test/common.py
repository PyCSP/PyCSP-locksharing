#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2018 John Markus Bjørndalen, jmb@cs.uit.no.
# See LICENSE.txt for licensing details (MIT License).

import argparse
import pycsp         # noqa E402

# Common arguments are added and handled here. The general outline for a program is to
# use common.handle_common_args() with a list of argument specs to add.

argparser = argparse.ArgumentParser()
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
    return args


def avg(vals):
    "Returns the average of values"
    return sum(vals) / len(vals)
