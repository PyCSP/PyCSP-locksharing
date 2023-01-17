#!/usr/bin/env python3

"""
Implementation of CFuture.
"""

import _thread
_start_new_thread = _thread.start_new_thread
_allocate_lock = _thread.allocate_lock
RLock = _thread.RLock


class CFuture:
    """The CFuture combines the wait-for-result and send-result mechanisms of a Future with the shared lock
    management of a Monitor (implemented using a Condition variable).
    Instead of transferring control, as in a Hoare monitor, we transfer state like in a Future and release the waiting
    thread like in a normal condition variable.

    Instead of using a condition variable, this version of the CFuture uses some of the same tricks that the
    Condition variable in the threading library uses.
    It reduces some overhead, however, as it doesn't have to re-acquire the shared lock to get back into the monitor.
    Instead, the semantics of the wait() is that the caller has released the shared lock when returning and
    the result is stored in the future.

    In a simple producer-consumer benchmark the overhead of using a condition variable to implement a CFuture is
    50% higher (on the whole benchmark) than using this version of the CFuture.

    The interface is kept simple to avoid complicating the implementation:

    Simple use as a lock:
         with CFuture() as cf:     # This allocates a CFuture and grabs the shared lock
              .. do something with the shared lock ...


    Using it as a Future to wait for some condition and result:
        with CFuture() as cf:
            ... pass the cf object somewhere so some other thread can wake this one up()
            result = cf.wait()
            #  you no longer have the lock after calling wait, so the rest of the context
            #  does not hold the lock

    with CFuture() as cf:
        with CFuture() as cf:
            ... do
            other_cf.set_result('someresult')   # this passes the result and wakes up the waiter
            # or, to trigger an exception in the waiting object (ex: ChannelPoisonExc)
            # this will also wake up the waiter, which will be poisoned
            other_cf.set_exception(exception_object)

    TODO: raise an exception if the future is re_used (wait() or __enter__ is called twice)?
    """
    _global_lock = RLock()  # lock shared by all CFutures

    def __init__(self, lock=None):
        if lock is None:
            # threading.Condition creates a local lock for that condition variable
            # lock = RLock()
            # For the use in PyCSP, we need to use a global lock unless we require all to specify a shared lock.
            lock = self._global_lock
        self._lock = lock
        self._is_owned = lock._is_owned
        self._waiter = None  # we only support one waiter.
        self.result = None   # returned value. Will be set by set_result
        self.waited = False
        self.exception = None
        self._done = False

    def done(self):
        """True if set_exception or set_result has been called on the CFuture"""
        return self._done

    def set_exception(self, exc):
        """Stores the exception in the future and wakes up any sleeping waiter.
        The waiter will then have the exception triggered upon resuming.
        """
        self.exception = exc
        self._notify()

    def set_result(self, res):
        """Sets the result and notifies any waiting process. This should only be done while holding the
        shared lock."""
        self.result = res
        self._notify()

    def wait(self):
        """NB: Once you return, you no longer have the lock!"""
        if not self._is_owned():
            raise RuntimeError("cannot wait on un-acquired lock")
        # Create a lock that this thread can sleep on while waiting for somebody else to notify.
        waiter = _allocate_lock()
        waiter.acquire()
        self._waiter = waiter
        # Relase the shared lock to let others do things inside the pycsp library.
        self._lock.release()
        self.waited = True
        # This will block this thread/method until somebody releases the lock, or continue immediately if
        # another thread managed to release/notify() before this call to acquire.
        waiter.acquire()
        if self.exception:
            raise self.exception
        return self.result

    def _notify(self):
        "Only notifies the first waiter, there should only be one though"
        w = self._waiter
        self._waiter = None
        self._done = True
        w.release()

    def __enter__(self):
        self._lock.acquire()
        return self

    def __exit__(self, *args):
        if not self.waited:
            # Only release if wait() was never called, so the shared lock has to be released.
            # If self.wait() was called, this CFuture no longer has the shared lock.
            self._lock.release()

        # args are usually None (no exceptions etc)
        # Return True to suppress execptions.
        # NB: The exit should not check for exceptions! Otherwise, there might be a race condition
        # with a reader successfully reading from a channel and then getting poisoned afterwards
        # if the context is exited a bit afterwards.
        return False
