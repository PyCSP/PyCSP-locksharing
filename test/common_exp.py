#!/usr/bin/env python3

import pycsp
from pycsp import chan_poisoncheck, _ChanOP, ChannelPoisonException, CFuture

# experimental implementation tricks for aPyCSP

# ############################################################
#
# Make sure we can switch back to the original channel implementation
#
Channel_Orig = pycsp.Channel


def set_channel_orig():
    pycsp.Channel = Channel_Orig


# ############################################################
#
# Decorated read and write ops.
#

class Channel_W_DecoratorOps(pycsp.Channel):
    def __init__(self, name=""):
        super().__init__(name)
        # print("decorator chan (poisoncheck)")

    # Note is from aPyCSP
    # TODO: adding this decorator adds about 0.7 microseconds to the op time _and_ it adds memory usage for
    # processes waiting on a channel (call/await/future stack)... (5092 vs 4179 bytes per proc in n_procs.py)
    # Can we improve it?
    @chan_poisoncheck
    def _write(self, obj):
        with CFuture() as c:
            wcmd = _ChanOP('write', obj)
            if len(self.wqueue) > 0 or len(self.rqueue) == 0:
                # a) somebody else is already waiting to write, so we're not going to
                #    change the situation any with this write. simply append ourselves and wait
                #    for somebody to wake us up with the result.
                # b) nobody is waiting for our write. (TODO: buffered channels)
                self._queue_waiting_op(self.wqueue, wcmd, c)
                return c.wait()
            # find matching read cmd.
            rcmd = self.rqueue.popleft()
            return self._rw_nowait(wcmd, rcmd)[0]

    @chan_poisoncheck
    def _read(self):
        with CFuture() as c:
            rcmd = _ChanOP('read', None)
            if len(self.rqueue) > 0 or len(self.wqueue) == 0:
                # readers ahead of us, or no writiers
                self._queue_waiting_op(self.rqueue, rcmd, c)
                return c.wait()
            # find matching write cmd.
            wcmd = self.wqueue.popleft()
            return self._rw_nowait(wcmd, rcmd)[1]


def set_channel_rw_decorator():
    print("** Replacing asyncio.Channel with version with decorated read/writes")
    pycsp.Channel = Channel_W_DecoratorOps


# ############################################################
#
# Context manager.
#
# This appears to have similar execution time to the decorators, but the decorator is easier to spot.
# On the other hand, this can be used inside a method which could be more flexible for ALT poison checking...
# It uses about as much memory as the non-decorated version

class PoisonChecker:
    def __init__(self, chan):
        self.chan = chan

    def __enter__(self):
        if self.chan.poisoned:
            raise ChannelPoisonException()
        return self.chan

    def __exit__(self, *exc_details):
        if self.chan.poisoned:
            raise ChannelPoisonException()


class Channel_W_ContextMgrOps(pycsp.Channel):
    def __init__(self, name=""):
        super().__init__(name)
        self.poisoncheck = PoisonChecker(self)
        # print("decorator chan (ctxt poisoncheck)")

    # using context managers
    def _write(self, obj):
        with CFuture() as c:
            with self.poisoncheck:
                wcmd = _ChanOP('write', obj)
                if len(self.wqueue) > 0 or len(self.rqueue) == 0:
                    self._queue_waiting_op(self.wqueue, wcmd, c)
                    return c.wait()
                # find matching read cmd.
                rcmd = self.rqueue.popleft()
                return self._rw_nowait(wcmd, rcmd)[0]

    def _read(self):
        with CFuture() as c:
            with self.poisoncheck:
                rcmd = _ChanOP('read', None)
                if len(self.rqueue) > 0 or len(self.wqueue) == 0:
                    # readers ahead of us, or no writiers
                    self._queue_waiting_op(self.rqueue, rcmd, c)
                    return c.wait()
                # find matching write cmd.
                wcmd = self.wqueue.popleft()
                return self._rw_nowait(wcmd, rcmd)[1]


def set_channel_contextmgr():
    print("** Replacing asyncio.Channel with version with decorated read/writes")
    pycsp.Channel = Channel_W_ContextMgrOps


# ############################################################
#
# Variaion of context manager using the channel itself.
# Mainly to experiment with overheads
#

class Channel_W_ContextMgrOps2(pycsp.Channel):
    def __init__(self, name=""):
        super().__init__(name)
        # print("decorator chan (ctxt2 poisoncheck)")

    # using context managers
    def _write(self, obj):
        with CFuture() as c:
            with self:
                wcmd = _ChanOP('write', obj)
                if len(self.wqueue) > 0 or len(self.rqueue) == 0:
                    self._queue_waiting_op(self.wqueue, wcmd, c)
                    return c.wait()
                # find matching read cmd.
                rcmd = self.rqueue.popleft()
                return self._rw_nowait(wcmd, rcmd)[0]

    def _read(self):
        with CFuture() as c:
            with self:
                rcmd = _ChanOP('read', None)
                if len(self.rqueue) > 0 or len(self.wqueue) == 0:
                    # readers ahead of us, or no writiers
                    self._queue_waiting_op(self.rqueue, rcmd, c)
                    return c.wait()
                # find matching write cmd.
                wcmd = self.wqueue.popleft()
                return self._rw_nowait(wcmd, rcmd)[1]

    # context manager for the channel checks for poison
    def __enter__(self):
        if self.poisoned:
            raise ChannelPoisonException()
        return self

    def __exit__(self, *exc_details):
        if self.poisoned:
            raise ChannelPoisonException()


def set_channel_contextmgr2():
    print("** Replacing asyncio.Channel with version with decorated read/writes")
    pycsp.Channel = Channel_W_ContextMgrOps2
