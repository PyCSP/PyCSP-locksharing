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

    def set_result(self, res):
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
        return self.result

    def _notify(self):
        "only notifies the first waiter, there should only be one though"
        w = self._waiter
        self._waiter = None
        w.release()

    def __enter__(self):
        self._lock.acquire()
        return self

    def __exit__(self, *args):
        # If self.wait() was called, this CFuture no longer has the shared lock.
        # TODO: should check if we actually have the shared lock.
        if not self.waited:
            # Only release if wait() was never called, so the shared lock has to be released.
            self._lock.release()
        # args are usually None (no exceptions etc)
        # Return True to suppress execptions.
        return False
