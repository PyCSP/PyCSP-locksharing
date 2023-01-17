#!/usr/bin/env python3
"""
Multithreaded implementation of PyCSP using custom Futures that share a global lock for communication, ALT and guards.

/usr/lib/python3.6/concurrent/futures/_base.py has the implementation for thread based futures.
These use an internal (non-shared) lock, and you can't specify a lock you want to use.
This inspired the creation of CFutures (see separate file for implementation).
"""

import collections
import functools
import types
from enum import Enum
import threading
from .cfutures import CFuture


# ******************** Core code ********************

class ChannelPoisonException(Exception):
    """Used to interrupt processes accessing poisoned channels."""


def chan_poisoncheck(func):
    "Decorator for making sure that poisoned channels raise ChannelPoinsonException."
    @functools.wraps(func)
    def p_wrap(self, *args, **kwargs):
        # Only check for poison on entry.
        # A poison applied to a channel should only influence any operations that sleep
        # on the channel or ones that try to submit a new operation _after_ the poison
        # was applied.
        # Otherwise there might be a race where a successful read/write lets one of the processes
        # return from the operation and poison the channel before the other process wakes up.
        # Sometimes the late process would be poisoned on a successful operation, sometimes
        # it would not.
        if self.poisoned:
            raise ChannelPoisonException()
        return func(self, *args, **kwargs)
    return p_wrap


def process(verbose_poison=False):
    """Decorator for creating process functions.
    Annotates a function as a process and takes care of poison propagation.

    If the optional 'verbose_poison' parameter is true, the decorator will print
    a message when it captures the ChannelPoisonException after the process
    was poisoned.
    """
    def inner_dec(func):
        @functools.wraps(func)
        def proc_wrapped(*args, **kwargs):
            return Process(func, verbose_poison, *args, **kwargs)
        return proc_wrapped

    # Decorators with optional arguments are a bit tricky in Python.
    # 1) If the user did not specify an argument, the first argument will be the function to decorate.
    # 2) If the user specified an argument, the arguments are to the decorator.
    # In the first case, retturn a decorated function.
    # In the second case, return a decorator function that returns a decorated function.
    if isinstance(verbose_poison, (types.FunctionType, types.MethodType)):
        # Normal case, need to re-map verbose_poison to the default instead of a function,
        # or it will evaluate to True
        func = verbose_poison
        verbose_poison = False
        return inner_dec(func)
    return inner_dec


class Process(threading.Thread):
    """PyCSP process container. Arguments are: <function>, *args, **kwargs.
    Checks for and propagates channel poison (see Channels.py)."""
    def __init__(self, fn, verbose_poison, *args, **kwargs):
        threading.Thread.__init__(self)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.poisoned = False
        self.verbose_poison = verbose_poison
        self.retval = None

    def run(self):
        self.retval = None
        try:
            # Store the returned value from the process
            self.retval = self.fn(*self.args, **self.kwargs)
        except ChannelPoisonException:
            if self.verbose_poison:
                print(f"Process poisoned: {self.fn}({self.args=}, {self.kwargs=})")
            self.poisoned = True
            # look for channels and channel ends
            for ch in [x for x in self.args if isinstance(x, (ChannelEnd, Channel))]:
                ch.poison()


# TODO: see test_plugnplay.py for comments. Parallel and Sequence are not composable in the same
# way they are in aPyCSP.
# pylint: disable-next=C0103
def Parallel(*processes, check_poison=False):
    """Used to run a set of processes concurrently.
    Takes a list of processes which are started.
    Waits for the processes to complete, and returns a list of return values from each process.
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


# pylint: disable-next=C0103
def Sequence(*processes):
    """Sequence construct. Takes a list of processes (Python threads) which are started.
    The Sequence construct returns when all given processes exit."""
    for p in processes:
        # Call Run directly instead of start() and join()
        p.run()
    # return a list of the return values from the processes
    return [p.retval for p in processes]


# pylint: disable-next=C0103
def Spawn(proc):
    """Spawns off and starts a PyCSP process in the background, for
    independent execution. Returns the started process."""
    proc.start()
    return proc


# ******************** Base and simple guards (channel ends should inherit from a Guard) ********************
#

class Guard:
    """Base Guard class."""
    # Based on JCSPSRC/src/com/quickstone/jcsp/lang/Guard.java
    def enable(self, alt):    # pylint: disable=W0613
        """Enable guard. Returns (True, return value) if a guards ready when enabled."""
        return (False, None)

    def disable(self, alt):    # pylint: disable=W0613
        """Disable guard."""
        return False


class Skip(Guard):
    """Based on JCSPSRC/src/com/quickstone/jcsp/lang/Skip.java"""
    def enable(self, alt):
        # Thread.yield() in java version
        return (True, None)

    def disable(self, alt):
        return True


# The following discussion may turn into a more generic advice for creating guards that respond to
# other events than channels.
#
# Older versions of the thread based Timer guard had two potential race conditions :
#
# RC1: threading.Timer threads check whether they are cancelled _before_ running the callback.
#      This does not protect against a callback that wakes up, tries to grab a CFuture lock
#      and sleeps on that while some other thread is able to diable the Timer guard.
#      This other thread could either have managed to grab the lock before the threading.Timer,
#      thread, or it was a thread that already had the lock when the timer fired.
# RC2: If a user is allowed to re-use Timer guards (running multiple alt.selects with the same
#      Timer guard), the condition of the object is unknown when the timer manages to grab
#      the lock.
#      a) It may be unmodified and the callback is correct to run the expire.
#      b) It may be disabled.
#      c) It may be disabled and then enabled again (re-used).
#
# Running alt.schedule from RC1 or RC2.b and RC2.c could potentially cause problems (RC2.a is,
# strictly speaking, correct behaviour).
# - RC1 and RC2.b can be protected against by using a state flag (is_enabled) in the Timer guard and checking
#   that flag in the expire callback (after holding the CFuture lock).
# - RC2.c : Re-use of the Timer guard invalidates the use of is_enabled as that flag may, in principle,
#   have been set and re-set multiple times before the timer thread is able to grab the CFuture.
#
# This quickly gets complicated to analyze and protect against unless the following observations are made:
# O1: A timeout only makes sense as long as the Timer guard is in the same state as it was when it was
#     enabled. If some other thread managed to run either disable() or enable(), the expire that was
#     scheduled in _this_ call to enable() no longer makes sense.
# O2: Running enable() and disable() on guards should only be done while holding the shared lock with a CFture.
#
# The key insight is from O1. A simple mutation counter that is increased every time enable() or disable() is
# called is sufficient to ensure this. The expire callback can then just check that the mutation number is the
# same as when the threading.Timer was created/scheduled.
#
# O2 should be safe as guards are only mutated from channel end operations or alt.select().
# It is, however, something to be aware of when implementing new types of guards.
#
# As a side note: the JCSP CSTimer does not handle timing and timeouts directly. Instead, the enable method
# sets the timeout value in the alt and alt uses a wait with a timeout on the condition variable that protects
# the core (Java Object.wait). The result is that it avoids this problem entirely.
class Timer(Guard):
    """Timer that enables a guard after a specified number of seconds.
    """
    def __init__(self, seconds):
        self.expired = False
        self.alt = None
        self.seconds = seconds
        self.timer = None
        self._mutation = 0   # verion number / mutation number of the Timer object

    def enable(self, alt):
        self._mutation += 1
        self.expired = False
        self.alt = alt
        # Need to create a new thread/timer here since a threading.Timer cannot be reused.
        self.timer = threading.Timer(self.seconds, self._expire, args=[self._mutation])
        self.timer.start()
        return (False, None)

    def disable(self, alt):
        self._mutation += 1
        self.timer.cancel()
        self.alt = None

    def _expire(self, mutation_at_enable):
        if self._mutation != mutation_at_enable:
            # Object mutated since it was enabled. The timeout is no longer needed.
            return
        with CFuture():
            if self._mutation == mutation_at_enable:
                # The mutation count will be increased by schedule() as it calls disable(),
                # so this increase is not required.
                self._mutation += 1
                self.expired = True
                self.alt.schedule(self, 0)

    def __repr__(self):
        return f"<Timer ({self.seconds} S), exp: {self.expired}, mut: {self._mutation}>"


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
        """Poisons the channel"""
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
        return f"<ChannelWriteEnd wrapping {self._chan}>"

    def alt_pending_write(self, obj):
        """Returns a pending write guard object that will only write if this guard
        is selected by the ALT.
        """
        return PendingChanWriteGuard(self._chan, obj)


class ChannelReadEnd(ChannelEnd, Guard):
    """Read end of a channel.

    This can be used directly as a guard. As a guard, it will evaluate to ready
    if the read operation can complete (or woken up by a matching write operation).
    The return value from the guard will then be the value returned by the read.

    The channel end also supports being used as an iterator (async for ch.read)"
    """
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
        return f"<ChannelReadEnd wrapping {self._chan}>"

    # Support for reading from the channel end using a for loop.
    def __iter__(self):
        return self

    def __next__(self):
        return self._chan._read()


class _ChanOpcode(Enum):
    READ = 'r'
    WRITE = 'w'


CH_READ = _ChanOpcode.READ
CH_WRITE = _ChanOpcode.WRITE


# pylint: disable-next=R0903
class _ChanOP:
    """Used to store channel cmd/ops for the op queues."""
    __slots__ = ['cmd', 'obj', 'fut', 'alt', 'wguard']    # reduce some overhead

    def __init__(self, cmd, obj, alt=None):
        self.cmd = cmd    # read or write
        self.obj = obj
        self.fut = None   # Future is used for commands that have to wait
        self.alt = alt    # None if normal read, reference to the ALT if tentative/alt
        self.wguard = None

    def __repr__(self):
        return f"<_ChanOP: {self.cmd}>"


class Channel:
    """CSP Channels for aPyCSP. This is a generic channel that can be used with multiple readers
    and writers. The channel ends also supports being used as read guards (read ends) and for
    creating lazy/pending writes that be submitted as write guards in an ALT.

    Note that the following rules apply:
    1) An operation that is submitted (read or write) is immediately paired with the first corresponding operation in the queue
    2) If no corresponding operation exists, the operation is added to the end of the queue

    Following from these rules, the queue can only be either empty or have a queue of a single
    type of operation (read or write).
    """
    def __init__(self, name=""):
        self.name = name
        self.poisoned = False
        self.queue = collections.deque()
        self.read = ChannelReadEnd(self)
        self.write = ChannelWriteEnd(self)

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.name} ql={len(self.queue)} p={self.poisoned}>"

    def _queue_waiting_op(self, op, fut):
        """Used when we need to queue an operation and wait for its completion.
        Returns a future we can wait for that will, upon completion, contain
        the result from the operation.
        """
        op.fut = fut
        self.queue.append(op)
        return fut

    def _rw_nowait(self, wcmd, rcmd):
        """Execute a 'read/write' and wakes up any futures.
        Returns the return value for (write, read).
         NB: a _read ALT calling _rw_nowait should send a non-ALT read
        instead of an ALT to avoid having an extra schedule() called on it.
        The same goes for write ops.
        """
        obj = wcmd.obj
        if wcmd.fut:
            wcmd.fut.set_result(0)
        if rcmd.fut:
            rcmd.fut.set_result(obj)
        if wcmd.alt is not None:
            # Handle the alt semantics for a sleeping write ALT.
            wcmd.alt.schedule(wcmd.wguard, 0)
        if rcmd.alt is not None:
            # Handle the alt semantics for a sleeping read ALT.
            rcmd.alt.schedule(self.read, obj)
        return (0, obj)

    def _pop_matching(self, op):
        """Remove and return the first matching operation from the queue, or return None if not possible"""
        if len(self.queue) > 0 and self.queue[0].cmd == op:
            return self.queue.popleft()
        return None

    # NB: See docstring for the channels. The queue is either empty, or it has
    # a number of queued operations of a single type. There is never both a
    # read and a write in the same queue.
    @chan_poisoncheck
    def _read(self):
        with CFuture() as c:
            rcmd = _ChanOP(CH_READ, None)
            if (wcmd := self._pop_matching(CH_WRITE)) is not None:
                # Found a match
                return self._rw_nowait(wcmd, rcmd)[1]

            # No write to match up with. Wait.
            self._queue_waiting_op(rcmd, c)
            return c.wait()

    @chan_poisoncheck
    def _write(self, obj):
        with CFuture() as c:
            wcmd = _ChanOP(CH_WRITE, obj)
            if (rcmd := self._pop_matching(CH_READ)) is not None:
                return self._rw_nowait(wcmd, rcmd)[0]

            # No read to match up with . Wait.
            self._queue_waiting_op(wcmd, c)
            return c.wait()

    def poison(self):
        """Poison a channel and wake up all ops in the queues so they can catch the poison."""
        # This doesn't need to be an async method any longer, but we
        # keep it like this to simplify poisoning of remote channels.
        with CFuture():
            if self.poisoned:
                return  # already poisoned

            # Cancel any operations in the queue
            while len(self.queue) > 0:
                op = self.queue.popleft()
                if op.fut:
                    # Waiting ops should get an exception
                    op.fut.set_exception(ChannelPoisonException())
                if op.alt:
                    op.alt.poison(self)

            self.poisoned = True

    def _remove_alt_from_queue(self, alt):
        """Remove an alt from the queue."""
        # TODO: this is inefficient, but should be ok for now.
        # Since a user could, technically, submit more than one operation to the same queue with an alt, it is
        # necessary to support removing more than one operation on the same alt.
        self.queue = collections.deque(filter(lambda op: op.alt != alt, self.queue))

    def renable(self, alt):
        """enable for the input/read end"""
        if self.poisoned:
            raise ChannelPoisonException(f"renable on channel {self} {alt=}")
        rcmd = _ChanOP(CH_READ, None)
        if (wcmd := self._pop_matching(CH_WRITE)) is not None:
            # Found a match
            ret = self._rw_nowait(wcmd, rcmd)[1]
            return (True, ret)

        # Can't match the operation on the other queue, so it must be queued.
        rcmd.alt = alt
        self.queue.append(rcmd)
        return (False, None)

    def rdisable(self, alt):
        """Removes the ALT from the queue."""
        self._remove_alt_from_queue(alt)

    def wenable(self, alt, pguard):
        """Enable write guard."""
        if self.poisoned:
            raise ChannelPoisonException(f"wenable on channel {self} {alt=} {pguard=}")

        wcmd = _ChanOP(CH_WRITE, pguard.obj)
        if (rcmd := self._pop_matching(CH_READ)) is not None:
            # Make sure it's treated as a write without a sleeping future.
            ret = self._rw_nowait(wcmd, rcmd)[0]
            return (True, ret)

        # Can't execute the write directly. Queue the write guard.
        wcmd.alt = alt
        wcmd.wguard = pguard
        self.queue.append(wcmd)
        return (False, None)

    def wdisable(self, alt):
        """Removes the ALT from the queue."""
        self._remove_alt_from_queue(alt)

    # Support iteration over channel to read from it:
    def __iter__(self):
        return self

    def __next__(self):
        return self._read()

    def verify(self):
        """Checks the state of the channel using assert."""
        if self.poisoned:
            assert len(self.queue) == 0, "Poisoned channels should never have queued messages"

        assert len(self.queue) == 0 or all(x.cmd == self.queue[0].cmd for x in self.queue), \
               "Queue should be empty, or only contain messages with the same operation/cmd"
        return True


def poison_channel(ch):
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
    def _write(self, obj):
        wcmd = _ChanOP(CH_WRITE, obj)
        if (rcmd := self._pop_matching(CH_READ)) is not None:
            return self._rw_nowait(wcmd, rcmd)[0]

        # The main difference with normal write: simply append a write op without a future and return to the user.
        self.queue.append(wcmd)
        return 0


# ******************** ALT ********************
#
class Alternative:
    """Alternative. Selects from a list of guards.

    This differs from the old thread-based implementation in the following way:
    1. Guards are enabled, stopping on the first ready guard if any.
    2. If the alt is waiting for a guard to go ready, the first guard to
       switch to ready will immediately jump into the ALT and execute the necessary bits
       to resolve and execute operations (like read in a channel).
       This is possible as there is no lock and we're running single-threaded code.
       This means that searching for guards in disable_guards is no longer necessary.
    3. disable_guards is simply cleanup code removing the ALT from the guards.
    This requires that all guard code is synchronous / atomic.

    NB:
    - This implementation supports multiple ALT readers on a channel
      (the first one will be resolved).
    - As everything is resolved atomically it is safe to allow allow
      ALT writers and ALT readers in the same channel.
    - The implementation does not, however, support a single Alt to send a read
      _and_ a write to the same channel as they might both resolve.
      That would require the select() function to return more than one guard.
    - Don't let anything yield while runnning enable, disable pri_select.
      NB: that would not let us run remote ALTs/Guards... but the reference implementation cannot
      do this anyway (there is no callback for schedule()).
    """
    # States for the Alternative construct.
    _ALT_INACTIVE = "inactive"
    _ALT_READY    = "ready"
    _ALT_ENABLING = "enabling"
    _ALT_WAITING  = "waiting"

    def __init__(self, *guards):
        self.guards = guards
        self.state = self._ALT_INACTIVE
        self.enabled_guards = []  # List of guards we successfully enabled (and would need to disable on exit).
        self.wait_fut = None      # Wait future when we need to wait for any guard to complete.

    def _enable_guards(self):
        "Enable guards. Selects the first ready guard and stops, otherwise it will enable all guards."
        assert len(self.enabled_guards) == 0, "Running _enable_guards() on an alt with existing enabled guards"
        try:
            for g in self.guards:
                self.enabled_guards.append(g)
                enabled, ret = g.enable(self)
                if enabled:
                    # Current guard is ready, so use this immediately (works for pri_select).
                    self.state = self._ALT_READY
                    return (g, ret)
            return (None, None)
        except ChannelPoisonException as e:
            # Disable any enabled guards.
            self._disable_guards()
            self.state = self._ALT_INACTIVE
            # Re-throwing the exception to reach the caller of alt.select.
            raise e

    # This should not need to check for poison as any already enabled guards should have blabbered
    # about the poison directly through alt.poison().
    # Also, _disable_guards() is called when _enable_guards() detects poison.
    def _disable_guards(self):
        "Disables guards that we successfully entered in enable_guards."
        for g in self.enabled_guards:
            g.disable(self)
        self.enabled_guards = []

    # TODO: pri_select always tries the guards in the same order. The first successful will stop the attemt and unroll the other.
    # If all guards are enabled, the first guard to succeed will unroll the others.
    # The result is that other types of select could be provided by reordering the guards before trying to enable them.

    def select(self):
        """Calls the default select method (currently pri_select) to wait for any one guard to become ready.
        Returns a tuple with (selected guard, return value from guard).
        """
        return self.pri_select()

    def pri_select(self):
        """Waits for any of the guards to become ready.

        It generally uses three phases internally:
        1) enable, where it enables guards, stopping if any is found to be ready
        2) wait - it will wait until one of the guards becomes ready and calls schedule.
           This phase is skipped if a guard was selected in the enable phase.
        3) diable - any guards enabled in the enable phase will be disabled.

        A guard that wakes up in phase 2 will notify the alt by calling schedule() on the alt.
        See Channel for an example.

        Returns a tuple with (selected guard, return value from guard).
        """
        with CFuture() as c:
            # 1) First, enable guards.
            self.state = self._ALT_ENABLING
            g, ret = self._enable_guards()
            if g:
                # We found a guard in enable_guards, skip to phase 3.
                self._disable_guards()
                self.state = self._ALT_INACTIVE
                return (g, ret)

            # 2) No guard has been selected yet. Wait for one of the guards to become "ready".
            self.state = self._ALT_WAITING
            self.wait_fut = c
            g, ret = c.wait()
            # By this time, schedule() will have resolved everything and executed phase 3.
            # The selected guard and return value are available in (g, ret)
            # Poion that propagated while sleeping will be handled by poison using set_exception().
            self.state = self._ALT_INACTIVE
            return (g, ret)

    def schedule(self, guard, ret):
        """A wake-up call to processes ALTing on guards controlled by this object.
        Called by the (self) selected guard.
        NB: this should only be called from a thread that already holds the shared lock (using a CFuture).
        """
        if self.state != self._ALT_WAITING:
            # So far, this has only occurred with a single process that tries to alt on both the read and write end
            # of the same channel. In that case, the first guard is enabled, waiting for a matching operation. The second
            # guard then matches up with the first guard. They are both in the same ALT which is now in an enabling phase.
            # If a wguard enter first, the rguard will remove the wguard (flagged as an ALT), match it with the
            # read (flagged as RD). rw_nowait will try to run schedule() on the wguard's ALT (the same ALT as the rguard's ALT)
            # which is still in the enabling phase.
            # We could get around this by checking if both ends reference the same ALT, but it would be more complicated code,
            # and (apart from rendesvouz with yourself) the semantics of reading and writing from the channel
            # is confusing for a normal Alt (you would need something like a ParAlt).
            # Furthermore, the results from the alt need to signal that there were two selected guards (and results).
            # There is a risk of losing events that way. A workaround to detect this earlier could be to examine
            # the guard list when running select() and trigger an exception here, but that would only work if
            # we know beforehand which guards might create this problem.
            msg = f"Error: running schedule on an ALT that was in state {self.state} instead of waiting."
            raise Exception(msg)
        # NB: It should be safe to set_result as long as we don't yield in it.
        self.wait_fut.set_result((guard, ret))
        self._disable_guards()

    def poison(self, guard):
        """Used to poison an alt that has enabled guards"""
        msg = f"ALT {self} was poisoned by guard {guard}"
        # print(msg)
        # Running disable_guards is safe as long as none of the guards try to set the wait_fut
        self._disable_guards()
        if self.wait_fut.done():
            print("WARNING: alt.wait_fut was already done in alt.poison. This will raise an exception.")
        self.wait_fut.set_exception(ChannelPoisonException(msg))

    # Support for context managers. Instead of the following:
    #    (g, ret) = ALT.select():
    # we can use this as an alternative:
    #    with ALT as (g, ret):
    #     ....
    # We may need to specify options to Alt if we want other options than pri_select.
    def __enter__(self):
        return self.select()

    def __exit__(self, exc_type, exc, tb):
        return None
