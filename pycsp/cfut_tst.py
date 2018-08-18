#!/usr/bin/env python3

"""
Temp implementation of CFuture. 
"""

import _thread
import threading
_start_new_thread = _thread.start_new_thread
_allocate_lock = _thread.allocate_lock
RLock = _thread.RLock
import sys

# An alternative way of doing this: 
# with CFuture(....) as c:
#      return c.wait()
# the __exit__ in c will do the actual waiting...
# the problem here is getting access to the return value from return and modifying that. 
# 
# The problem with releasing the condition afterwards is that I have a few
# locations in priSelect() where the state of the ALT is modified.
# The other is that it's not clear (unless you read the documentation of wait() that you no longer
# have the lock of the CF after returning from wait).
# We're making a confusing context manager/monitor. 

class CFuture:
    def __init__(self, lock=None):
        if lock is None:
            lock = RLock()
        self._lock = lock
        self._is_owned = lock._is_owned
        self._waiter = None # we only support one waiter. 
        self.result = None  # returned value. Will be set by set_result
        self.waited = False

    def set_result(self, res):
        self.result = res
        self._notify()
        
    def wait(self):
        """NB: Once you return, you no longer have the lock!"""
        if not self._is_owned():
            raise RuntimeError("cannot wait on un-acquired lock")
        waiter = _allocate_lock()
        waiter.acquire()
        self._waiter = waiter
        # TODO: what happens if somebody release waiter before we acquire the second time?
        # it _should_ only let us continue immediately
        self._lock.release()
        # Another lock will block us until somebody releases us
        self.waited = True
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
        # TODO: should check if we actually have it.
        if not self.waited:
            self._lock.release()
        # nb: if we have called self.wait, we no longer have the lock.
        # This is an ugly way of doing this.
        # args are usually None (no exceptions etc)
        # Return True to suppress execptions. 
        return False

if __name__ == "__main__":
    import traceback
    class CT:
        def foo(self):
            return 'bar'
        def __enter__(self):
            #self._lock.acquire()
            return self
        def __exit__(self, *args):
            print("__exit__", args)
            print("__exit__", sys.exc_info())
            tb = traceback.extract_stack()
            print("__exit__", tb)
            print(dir(tb))
            return (400, args)

    def test():
        with CT() as c:
            return c.foo()
    print("Return from test() is ", test())

    import time

    def f1(cf, sl):
        with cf:
            print("f1 sleeping holding shared lock before waiting")
            time.sleep(4)
            print("f1 waiting")
            ret = cf.wait()
            print("f1 got ", ret, "from wait")

    def f2(cf, sl):
        print("f2 trying to get shared lock")
        with CFuture(sl) as c:
            print("f2 sleeping")
            time.sleep(2)
            print("f2 woke up, setting result in cf")
            cf.set_result("res 400")
            print("f2 done")

    sl = RLock()
    cf = CFuture(sl)
    threads = [
        threading.Thread(target=f1, args=[cf,sl]),
        threading.Thread(target=f2, args=[cf,sl]),
        ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    
