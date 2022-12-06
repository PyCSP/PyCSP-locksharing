#!/usr/bin/env python3

import sys
import traceback
import time
import threading
from threading import RLock
import common    # noqa E402
from pycsp.cfutures import CFuture


class CT:
    def foo(self):
        return 'bar'

    def __enter__(self):
        # self._lock.acquire()
        return self

    def __exit__(self, *args):
        print("__exit__", args)
        print("__exit__", sys.exc_info())
        tb = traceback.extract_stack()
        print("__exit__", tb)
        print(dir(tb))
        return (400, args)


def CT_test():
    with CT() as c:
        return c.foo()


def f1(cf, sl):
    with cf:
        print("f1 sleeping holding shared lock before waiting")
        time.sleep(4)
        print("f1 waiting")
        ret = cf.wait()
        print("f1 got ", ret, "from wait")


def f2(cf, sl):
    print("f2 trying to get shared lock")
    with CFuture(sl):
        print("f2 sleeping")
        time.sleep(2)
        print("f2 woke up, setting result in cf")
        cf.set_result("res 400")
        print("f2 done")


def test2():
    sl = RLock()
    cf = CFuture(sl)
    threads = [
        threading.Thread(target=f1, args=[cf, sl]),
        threading.Thread(target=f2, args=[cf, sl]),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    print("Return from CT_test() is ", CT_test())
    test2()
