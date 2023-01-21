#!/usr/bin/env python3
"""
Multithreaded implementation of PyCSP using custom Futures that share a global lock for communication, ALT and guards.

/usr/lib/python3.6/concurrent/futures/_base.py has the implementation for thread based futures.
These use an internal (non-shared) lock, and you can't specify a lock you want to use.
This inspired the creation of CFutures (see separate file for implementation).
"""

# flake8:  noqa: F401
# pylint: disable=unused-import
from .cfutures import CFuture
from .core import PoisonException, process, Process, Parallel, Sequence, CSP, Spawn
from .guards import Guard, Skip, Timer
from .channels import Channel, ChannelEnd, PendingChanWriteGuard, ChannelWriteEnd
from .channels import ChannelReadEnd, poison_channel, BufferedChannel
from .alternative import Alternative
