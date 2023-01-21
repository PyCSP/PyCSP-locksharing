#!/usr/bin/env python3
"""
Base and simple guards (channel ends should inherit from a Guard)
"""

import threading
from .cfutures import CFuture


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
