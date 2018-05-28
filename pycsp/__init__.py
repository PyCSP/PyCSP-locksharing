#!/usr/bin/env python3
"""
Experimental implementation of PyCSP using custom Futures that share a global lock for communication, ALT and guards. 

/usr/lib/python3.6/concurrent/futures/_base.py has the implementation for thread based futures. These use an internal (non-shared) lock, and you can't specify a lock you want to use. 

"""

import threading
import time
import random

class CFuture(threading.Condition):
    """Custom future based on a threading.Condition"""
    def __init__(self, lock):
        """Must specify lock to create one of these"""
        super().__init__(lock)
        self.result = None
        self._wait = threading.Condition.wait

    def set_result(self, res):
        self.result = res
        self.notify()

    def wait(self):
        self._wait(self)
        return self.result

class LockCond:
    def __init__(self):
        self.lock = threading.RLock()

    def get_cfuture(self):
        return CFuture(self.lock)

    ### Todo: make an enter/release so we can write it as
    # with self.lc.get_cfuture() as c:
    # enter must allocate condition, acquire it and return the lock. 
    # exit should get the allocated object... how ?

_globalLock = LockCond()
    

class Channel:
    def __init__(self):
        self.lc = LockCond()
        self.rq = []
        self.wq = []

    def write(self, val):
        c = self.lc.get_cfuture()
        with c:
            if len(self.rq) == 0:
                ## nobody waiting for read
                self.wq.append([c, val])
                c.wait()
                return
            ## reader waiting, complete operation
            r = self.rq.pop(0)
            r[0].set_result(val)

    def read(self):
        c = self.lc.get_cfuture()
        with c:
            if len(self.wq) == 0:
                ## nobody waiting to write to us
                self.rq.append([c])
                return c.wait()
            w = self.wq.pop(0)
            val = w[1]
            w[0].set_result(0)
            return val
        

def writer(p, ch):
    pref = " " * p * 2
    for i in range(10):
        val = (p,i)
        print(f"{pref} W {p} -> {val}")
        ch.write(val)
        print(f"{pref} W {p} done")
        time.sleep(random.random()*3 + 2)

def reader(p, ch):
    pref = "                     " + " " * p * 2
    time.sleep(0.1)
    for i in range(10):
        print(f"{pref} R {p} waiting")
        val = ch.read()
        print(f"{pref} R {p} got {val}")
        time.sleep(random.random()*3 + 2)


ch = Channel()
threads = [
    threading.Thread(target=writer, args=[1, ch]), 
    threading.Thread(target=reader, args=[1, ch]),
    threading.Thread(target=writer, args=[2, ch]), 
    threading.Thread(target=reader, args=[2, ch])
    ]
for t in threads:
    t.start()
for t in threads:
    t.join()
print("All done")
