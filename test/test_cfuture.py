#!/usr/bin/env python3

import time
import threading
from threading import RLock
from pycsp.cfutures import CFuture
from pycsp import ChannelPoisonException

SLOW_WAIT = 0.4
FAST_WAIT = 0.2

MAGIC_RESULT = 'res 4000'


def f1(cf, sl, state_exit):
    try:
        with cf:
            print("f1 sleeping holding shared lock before waiting")
            time.sleep(SLOW_WAIT)
            print("f1 waiting")
            ret = cf.wait()
            print("f1 got ", ret, "from wait")
            state_exit['retval'] = ret
    except ChannelPoisonException as cp:
        print("f1 got exception")
        state_exit['exception'] = cp


def f2(cf, sl):
    print("f2 trying to get shared lock")
    with CFuture(sl):
        print("f2 sleeping")
        time.sleep(FAST_WAIT)
        print("f2 woke up, setting result in cf")
        cf.set_result(MAGIC_RESULT)
        print("f2 done")


def sets_exception(cf, sl):
    print("f2 trying to get shared lock")
    with CFuture(sl):
        print("f2 sleeping")
        time.sleep(FAST_WAIT)
        print("f2 woke up, setting exception in cf")
        cf.set_exception(ChannelPoisonException("catch this"))
        print("f2 done")


def test_cfuture_pass_result():
    """Checks if the cfuture passes a result"""
    print("\nCheck passing results")
    print("---------------------")
    sl = RLock()
    cf = CFuture(sl)
    state_exit = {}
    threads = [
        threading.Thread(target=f1, args=[cf, sl, state_exit]),
        threading.Thread(target=f2, args=[cf, sl]),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert state_exit['retval'] == MAGIC_RESULT, f"waiter should have set magic result, got {state_exit}"
    assert 'exception' not in state_exit, f"waiter should not have passed an excpetion, got {state_exit}"


def test_cfuture_pass_exception():
    """Checks if the cfuture passes an exception"""
    print("\nCheck passing excpetions")
    print("---------------------")
    sl = RLock()
    cf = CFuture(sl)
    state_exit = {}
    threads = [
        threading.Thread(target=f1, args=[cf, sl, state_exit]),
        threading.Thread(target=sets_exception, args=[cf, sl]),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert isinstance(state_exit['exception'], ChannelPoisonException), f"waiter should have set exception, got {state_exit}"
    assert 'retval' not in state_exit, f"waiter should not have set result, got {state_exit}"


if __name__ == "__main__":
    test_cfuture_pass_result()
    test_cfuture_pass_exception()
