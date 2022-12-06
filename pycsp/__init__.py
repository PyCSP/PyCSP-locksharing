#!/usr/bin/env python3
"""
Multithreaded implementation of PyCSP using custom Futures that share a global lock for communication, ALT and guards.

/usr/lib/python3.6/concurrent/futures/_base.py has the implementation for thread based futures.
These use an internal (non-shared) lock, and you can't specify a lock you want to use.
This inspired the creation of CFutures (see separate file for implementation).
"""

import threading
import collections
from .cfutures import CFuture


# ******************** Core code ********************

class ChannelPoisonException(Exception):
    pass


def chan_poisoncheck(func):
    "Decorator for making sure that poisoned channels raise exceptions"
    def _call(self, *args, **kwargs):
        if self.poisoned:
            raise ChannelPoisonException()
        try:
            return func(self, *args, **kwargs)
        finally:
            if self.poisoned:
                raise ChannelPoisonException()
    return _call


# ## Copied from thread version (classic)
def process(func):
    "Decorator for creating process functions"
    def _call(*args, **kwargs):
        return Process(func, *args, **kwargs)
    return _call


class Process(threading.Thread):
    """PyCSP process container. Arguments are: <function>, *args, **kwargs.
    Checks for and propagates channel poison (see Channels.py)."""
    def __init__(self, fn, *args, **kwargs):
        threading.Thread.__init__(self)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.poisoned = False

    def run(self):
        self.retval = None
        try:
            # Store the returned value from the process
            self.retval = self.fn(*self.args, **self.kwargs)
        except ChannelPoisonException:
            # print(f"Process {self.fn}({self.args}, {self.kwargs}) caught poison")
            self.poisoned = True
            # look for channels and channel ends
            for ch in [x for x in self.args if isinstance(x, ChannelEnd) or isinstance(x, Channel)]:
                ch.poison()


def Parallel(*processes, check_poison=False):
    """Parallel construct. Takes a list of processes (Python threads) which are started.
    The Parallel construct returns when all given processes exit.
    If check_poison is true, it will raise a ChannelPoison exception if any of the processes have been poisoned.
    """
    # run, then sync with them.
    for p in processes:
        p.start()
    for p in processes:
        p.join()
    # return a list of the return values from the processes
    if check_poison:
        if any(p.poisoned for p in processes):
            raise ChannelPoisonException()
    return [p.retval for p in processes]


def Sequence(*processes):
    """Sequence construct. Takes a list of processes (Python threads) which are started.
    The Sequence construct returns when all given processes exit."""
    for p in processes:
        # Call Run directly instead of start() and join()
        p.run()
    # return a list of the return values from the processes
    return [p.retval for p in processes]


def Spawn(process):
    """Spawns off and starts a PyCSP process in the background, for
    independent execution. Returns the started process."""
    process.start()
    return process


# ******************** Base and simple guards (channel ends should inherit from a Guard) ********************
#

# NB: guards should always be executed within an Alt or similar context to provide the proper locking
# TODO: look into this.

class Guard:
    """Base Guard class."""
    # Based on JCSPSRC/src/com/quickstone/jcsp/lang/Guard.java
    def enable(self, alt):
        return (False, None)

    def disable(self, alt):
        return False


class Skip(Guard):
    # Based on JCSPSRC/src/com/quickstone/jcsp/lang/Skip.java
    def enable(self, alt):
        return (True, None)  # Thread.yield() in java version

    def disable(self, alt):
        return True


# TODO: this is based on the classic version, should be checked for correctness
class Timer(Guard):
    def __init__(self, seconds):
        self.expired = False
        self.seconds = seconds
        self.alt = None

    def enable(self, alt):
        self.alt = alt
        # Need to create a new thread/timer here since a threading.Timer cannot be reused.
        self.timer = threading.Timer(self.seconds, self.expire)
        self.timer.start()
        return (False, None)

    def disable(self, alt):
        # print("Cancel", self.seconds)
        self.timer.cancel()
        self.alt = None

    def expire(self):
        self.expired = True
        with CFuture():
            self.alt.schedule(self, 0)


# ******************** Channels ********************

class ChannelEnd:
    """The channel ends are objects that wrap the Channel read()
    and write() methods, and adds methods for forwarding poison() calls.
    The channel ends are used for implementing ALT semantics and guards. """
    def __init__(self, chan):
        self._chan = chan

    def channel(self):
        "Returns the channel that this channel end belongs to."
        return self._chan

    def poison(self):
        return self._chan.poison()


class PendingChanWriteGuard(Guard):
    """Used to store a pending write that will only be executed if
    this particular guard is ready to be executed and is selected.
    """
    def __init__(self, chan, obj):
        self.chan = chan
        self.obj = obj

    def enable(self, alt):
        return self.chan.wenable(alt, self)

    def disable(self, alt):
        return self.chan.wdisable(alt)

    def __repr__(self):
        return f"<PendingChanWriteGuard for {self.chan.name}>"


class ChannelWriteEnd(ChannelEnd):
    """Write end of a Channel. This end cannot be used directly as a Guard as
    we need to implement a lazy/pending write that is only executed if the
    write guards is selected in the ALT. The current solution is to
    call ch.write.alt_pending_write(value) to get a PendingChanWriteGuard
    which is used as a write guard and will execute the write if selected.
    """
    def __init__(self, chan):
        ChannelEnd.__init__(self, chan)

    def __call__(self, val):
        return self._chan._write(val)

    def __repr__(self):
        return "<ChannelWriteEnd wrapping %s>" % self._chan

    def alt_pending_write(self, obj):
        """Returns a pending write guard object that will only write if this guard
        is selected by the ALT.
        """
        return PendingChanWriteGuard(self._chan, obj)


class ChannelReadEnd(ChannelEnd, Guard):
    def __init__(self, chan):
        Guard.__init__(self)
        ChannelEnd.__init__(self, chan)

    def __call__(self):
        return self._chan._read()

    def enable(self, alt):
        return self._chan.renable(alt)

    def disable(self, alt):
        return self._chan.rdisable(alt)

    def __repr__(self):
        return "<ChannelReadEnd wrapping %s>" % self._chan

    # support async for ch.read:  # TODO: normal iter for channel read end
    def __iter__(self):
        return self

    def __next__(self):
        return self._chan._read()


class _ChanOP:
    """Used to store channel cmd/ops for the op queues."""
    def __init__(self, cmd, obj, alt=None):
        self.cmd = cmd
        self.obj = obj
        self.fut = None   # Future is used for commands that have to wait
        self.alt = alt

    def __repr__(self):
        return f"<_ChanOP: {self.cmd}>"


class Channel:
    """CSP Channels for aPyCSP. This is a generic channel that can be used with multiple readers
    and writers. The channel ends also supports being used as read guards (read ends) and for
    creating lazy/pending writes that be submitted as write guards in an ALT.
    """
    def __init__(self, name=""):
        self.name = name
        self.poisoned = False
        self.wqueue = collections.deque()
        self.rqueue = collections.deque()
        self.read = ChannelReadEnd(self)
        self.write = ChannelWriteEnd(self)

    def __repr__(self):
        return "<Channel {} wq {} rq {}>".format(self.name, len(self.wqueue), len(self.rqueue))

    def _queue_waiting_op(self, queue, op, fut):
        """Used when we need to queue an operation and wait for its completion.
        Returns a future we can wait for that will, upon completion, contain
        the result from the operation.
        """
        op.fut = fut
        queue.append(op)
        return fut

    def _rw_nowait(self, wcmd, rcmd):
        """Execute a 'read/write' and wakes up any futures. Returns the
        return value for (write, read).
         NB: a _read ALT calling _rw_nowait should represent its own
        command as a normal 'read' instead of an ALT to avoid having
        an extra schedule() called on it. The same goes for a _write
        op.
        """
        obj = wcmd.obj
        if wcmd.fut:
            wcmd.fut.set_result(0)
        if rcmd.fut:
            rcmd.fut.set_result(obj)
        if wcmd.cmd == 'ALT':
            # Handle the alt semantics for a sleeping write ALT.
            wcmd.alt.schedule(wcmd.wguard, 0)
        if rcmd.cmd == 'ALT':
            # Handle the alt semantics for a sleeping read ALT.
            rcmd.alt.schedule(self.read, obj)
        return (0, obj)

    # TODO: moved the decorated versions of _read and _write to test/common_exp.py for easier
    # experimenting with alternative implementations.
    # This is currently the fastest version that uses the least amount of memory, but the context manager version
    # is almost as lean at an execution time cost closer to the decorator version.
    # TODO: consider how to solve poison checking for the ALT as well.
    def _read(self):
        with CFuture() as c:
            try:
                if self.poisoned:
                    return
                rcmd = _ChanOP('read', None)
                if len(self.rqueue) > 0 or len(self.wqueue) == 0:
                    # readers ahead of us, or no writiers
                    self._queue_waiting_op(self.rqueue, rcmd, c)
                    return c.wait()
                # find matching write cmd.
                wcmd = self.wqueue.popleft()
                return self._rw_nowait(wcmd, rcmd)[1]
            finally:
                if self.poisoned:
                    raise ChannelPoisonException()

    def _write(self, obj):
        with CFuture() as c:
            try:
                if self.poisoned:
                    return
                wcmd = _ChanOP('write', obj)
                if len(self.wqueue) > 0 or len(self.rqueue) == 0:
                    # a) Somebody else is already waiting to write, so we're not going to
                    #    change the situation any with this write. simply append ourselves and wait
                    #    for somebody to wake us up with the result.
                    # b) nobody is waiting for our write. (TODO: buffered channels)
                    self._queue_waiting_op(self.wqueue, wcmd, c)
                    return c.wait()
                # Find matching read cmd.
                rcmd = self.rqueue.popleft()
                return self._rw_nowait(wcmd, rcmd)[0]
            finally:
                if self.poisoned:
                    raise ChannelPoisonException()

    def poison(self):
        """Poison a channel and wake up all ops in the queues so they can catch the poison."""
        # This doesn't need to be an async method any longer, but we
        # keep it like this to simplify poisoning of remote channels.
        with CFuture():
            if self.poisoned:
                return

            def poison_queue(queue):
                while len(queue) > 0:
                    op = queue.popleft()
                    if op.fut:
                        op.fut.set_result(None)

            if self.poisoned:
                return
            self.poisoned = True
            poison_queue(self.wqueue)
            poison_queue(self.rqueue)

    def _remove_alt_from_pqueue(self, queue, alt):
        """Common method to remove an alt from the read or write queue."""
        # TODO: this is inefficient, but should be ok for now.
        # A slightly faster alternative might be to store a reference to the cmd in a dict
        # with the alt as key, and then use deque.remove(cmd).
        # An alt may have multiple channels, and a guard may be used by multiple alts, so
        # there is no easy place for a single cmd to be stored in either.
        # Deque now supports del deq[something], and deq.remove(), but need to find the obj first.
        #
        # print("......remove_alt_pq : ", queue, list(filter(lambda op: not(op.cmd == 'ALT' and op.alt == alt), queue)))
        #
        # TODO: one option _could_ be to use an ordered dict (new dicts are ordered as well), but we would need to
        # have a unique key that can be used to cancel commands later (and remove the first entry when popping)
        # collections.OrderedDict() has a popitem() method.
        return collections.deque(filter(lambda op: not (op.cmd == 'ALT' and op.alt == alt), queue))

    # TODO: read and write alts needs poison check, but we need de-register guards properly before we
    # consider throwing an exception.
    def renable(self, alt):
        """enable for the input/read end"""
        if len(self.rqueue) > 0 or len(self.wqueue) == 0:
            # Reader ahead of us or no writers.
            # The code is similar to _read(), and we
            # need to enter the ALT as a potential reader
            rcmd = _ChanOP('ALT', None, alt=alt)
            self.rqueue.append(rcmd)
            return (False, None)
        # We have a waiting writer that we can match up with, so we execute the read and return
        # the  read value as well as True for the guard.
        # Make sure it's treated as a read to avoid having rw_nowait trying to call schedule.
        rcmd = _ChanOP('read', None)
        wcmd = self.wqueue.popleft()
        ret = self._rw_nowait(wcmd, rcmd)[1]
        return (True, ret)

    def rdisable(self, alt):
        """Removes the ALT from the reader queue."""
        self.rqueue = self._remove_alt_from_pqueue(self.rqueue, alt)

    def wenable(self, alt, pguard):
        """Enable write guard."""
        if len(self.wqueue) > 0 or len(self.rqueue) == 0:
            # Can't execute the write directly, so we queue the write guard.
            wcmd = _ChanOP('ALT', pguard.obj, alt=alt)
            wcmd.wguard = pguard
            self.wqueue.append(wcmd)
            return (False, None)
        # Make sure it's treated as a write without a sleeping future.
        wcmd = _ChanOP('write', pguard.obj)
        rcmd = self.rqueue.popleft()
        ret = self._rw_nowait(wcmd, rcmd)[0]
        return (True, ret)

    def wdisable(self, alt):
        """Removes the ALT from the writer queue."""
        self.wqueue = self._remove_alt_from_pqueue(self.wqueue, alt)

    # Support iteration over channel to read from it:
    def __iter__(self):
        return self

    def __next__(self):
        return self._read()


def poisonChannel(ch):
    "Poisons a channel or a channel end."
    ch.poison()


# TODO:
# - This could be an option on the normal channel.
#   (we could just reassign the _write on channels with buffer set).
# - Buffer limit.
# - ALT writes should be considered as successful and transformed into normal
#   writes if there is room in the buffer, otherwise, we will have to
#   consider them again when there is room.
# - When write ops are retired, we need to consdier waking up alts and writes
#   that are sleeping on a write.
class BufferedChannel(Channel):
    """Buffered Channel. """
    def __init__(self, name=""):
        super().__init__(name=name)

    @chan_poisoncheck
    async def _write(self, obj):
        wcmd = _ChanOP('write', obj)
        if len(self.wqueue) > 0 or len(self.rqueue) == 0:
            # a) Somebody else is already waiting to write, so we're not going to
            #    change the situation any with this write.
            # b) Nobody is waiting for our write.
            # The main difference with normal write: simply append a write op without a future and return to the user.
            self.wqueue.append(wcmd)
            return 0
        # find matching read cmd.
        rcmd = self.rqueue.popleft()
        return self._rw_nowait(wcmd, rcmd)[0]


# ******************** ALT ********************
# TODO: based on aPyCSP comments. Needs to be verified.
#
# This differs from the old thread-based implementation in the following way:
# 1. Guards are enabled, stopping on the first ready guard if any.
# 2. If the alt is waiting for a guard to go ready, the first guard to
#    switch to ready will immediately jump into the ALT and execute the necessary bits
#    to resolve and execute operations (like read in a channel).
#    This is possible as there is a global no lock and we're, in practice, running single-threaded code.
#    This means that searching for guards in disableGuards is no longer necessary.
# 3. disableGuards is simply cleanup code removing the ALT from the guards.
# This requires that all guard code is synchronous.
#
# NB:
#
# - This implementation should be able to support multiple ALT readers
#   on a channel (the first one will be resolved).
# - As we're resolving everything in a synchronous function and no
#   longer allow multiple guards to go true at the same time, it
#   should be safe to allow ALT writers and ALT readers in the same
#   channel!
# - Don't let anything yield while runnning enable, disable priselect.
#   NB: that would not let us run remote ALTs/Guards... but the reference implementation cannot
#   do this anyway (there is no callback for schedule()).


class Alternative:
    # States for the Alternative construct.
    _ALT_INACTIVE = "inactive"
    _ALT_READY    = "ready"
    _ALT_ENABLING = "enabling"
    _ALT_WAITING  = "waiting"

    """Alternative. Selects from a list of guards."""
    def __init__(self, *guards):
        self.guards = guards
        self.state = self._ALT_INACTIVE
        self.enabled_guards = []  # List of guards we successfully enabled (and would need to disable on exit).
        self.wait_fut = None      # Wait future when we need to wait for any guard to complete.

    def _enableGuards(self):
        "Enable guards. Selects the first ready guard and stops, otherwise it will enable all guards."
        self.enabled_guards = []  # TODO: check and raise an error if the list was not already empty
        for g in self.guards:
            self.enabled_guards.append(g)
            enabled, ret = g.enable(self)
            if enabled:
                # Current guard is ready, so use this immediately (works for priSelect).
                self.state = self._ALT_READY
                return (g, ret)
        return (None, None)

    def _disableGuards(self):
        "Disables guards that we successfully entered in enableGuards."
        for g in self.enabled_guards:
            g.disable(self)
        self.enabled_guards = []

    def select(self):
        return self.priSelect()

    def priSelect(self):
        with CFuture() as c:
            # First, enable guards.
            self.state = self._ALT_ENABLING
            g, ret = self._enableGuards()
            if g:
                # We found a guard in enableGuards.
                self._disableGuards()
                self.state = self._ALT_INACTIVE
                return (g, ret)

            # No guard has been selected yet. Wait for one of the guards to become "ready".
            # The guards wake us up by calling schedule() on the alt (see Channel for example).
            self.state = self._ALT_WAITING
            self.wait_fut = c
            g, ret = c.wait()
            # By this time, everything should be resolved and we have a selected guard
            # and a return value (possibly None). We have also disabled the guards.
            self.state = self._ALT_INACTIVE
            return (g, ret)

    def schedule(self, guard, ret):
        """A wake-up call to processes ALTing on guards controlled by this object.
        Called by the (self) selected guard."""
        if self.state != self._ALT_WAITING:
            # So far, this has only occurred with a single process that tries to alt on both the read and write end
            # of the same channel. In that case, the first guard is enabled but has to wait, and the second
            # guard matches up with the first guard. They are both in the same ALT which is now in an enabling phase.
            # If a wguard enter first, the rguard will remove the wguard (flagged as an ALT), match it with the
            # read (flagged as RD). rw_nowait will try to run schedule() on the wguard's ALT (the same ALT as the rguard's ALT)
            # which is still in the enabling phase.
            # We could get around this by checking if both ends reference the same ALT, but it would be more complicated code,
            # and (apart from rendesvouz with yourself) the semantics of reading and writing from the channel
            # is confusing. You could end up writing without observing the result (the read has, strictly speaking,
            # completed though).
            msg = f"Error: running schedule on an ALT that was in state {self.state} instead of waiting."
            raise Exception(msg)
        # NB: It should be safe to set_result as long as we don't yield in it.
        self.wait_fut.set_result((guard, ret))
        self._disableGuards()

    # Support for context managers. Instead of the following:
    #    (g, ret) = ALT.select():
    # we can use this as an alternative:
    #    with ALT as (g, ret):
    #     ....
    # We may need to specify options to Alt if we want other options than priSelect.
    def __enter__(self):
        return self.select()

    def __exit__(self, exc_type, exc, tb):
        return None


# ############################################################

class SChannel:
    """Simple Channel"""
    def __init__(self):
        self.rq = []
        self.wq = []

    def write(self, val):
        with CFuture() as c:
            if len(self.rq) == 0:
                # nobody waiting for read
                self.wq.append([c, val])
                c.wait()
                return
            # reader waiting, complete operation
            r = self.rq.pop(0)
            r[0].set_result(val)

    def read(self):
        with CFuture() as c:
            if len(self.wq) == 0:
                # nobody waiting to write to us
                self.rq.append([c])
                return c.wait()
            w = self.wq.pop(0)
            val = w[1]
            w[0].set_result(0)
            return val

    def __iter__(self):
        return self

    def __next__(self):
        return self.read()
