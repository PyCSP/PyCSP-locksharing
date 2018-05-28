#!/usr/bin/env python3
"""
Experimental implementation of PyCSP using custom Futures that share a global lock for communication, ALT and guards. 

/usr/lib/python3.6/concurrent/futures/_base.py has the implementation for thread based futures. These use an internal (non-shared) lock, and you can't specify a lock you want to use. 

"""

import threading
import time
import random
import collections
import functools


# ******************** Core code ********************

class ChannelPoisonException(Exception): 
    pass

### Copied from thread version (classic) 
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
    def run(self):
        self.retval = None
        try:
            # Store the returned value from the process
            self.retval = self.fn(*self.args, **self.kwargs)
        except ChannelPoisonException as e:
            # look for channels and channel ends
            for ch in [x for x in self.args if isinstance(x, ChannelEnd) or isinstance(x, Channel)]:
                ch.poison()

def Parallel(*processes):
    """Parallel construct. Takes a list of processes (Python threads) which are started.
    The Parallel construct returns when all given processes exit."""
    # run, then sync with them. 
    for p in processes:
        p.start()
    for p in processes:
        p.join()
    # return a list of the return values from the processes
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

#####




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
        self.rq = []
        self.wq = []

    def write(self, val):
        c = _globalLock.get_cfuture()
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
        c = _globalLock.get_cfuture()
        with c:
            if len(self.wq) == 0:
                ## nobody waiting to write to us
                self.rq.append([c])
                return c.wait()
            w = self.wq.pop(0)
            val = w[1]
            w[0].set_result(0)
            return val
        

@process        
def writer(p, ch):
    pref = " " * p * 2
    for i in range(10):
        val = (p,i)
        print(f"{pref} W {p} -> {val}")
        ch.write(val)
        print(f"{pref} W {p} done")
        time.sleep(random.random()*3 + 2)
@process
def reader(p, ch):
    pref = "                     " + " " * p * 2
    time.sleep(0.1)
    for i in range(10):
        print(f"{pref} R {p} waiting")
        val = ch.read()
        print(f"{pref} R {p} got {val}")
        time.sleep(random.random()*3 + 2)


ch = Channel()
Parallel(writer(1, ch),
         reader(1, ch),
         writer(2, ch),
         reader(2, ch))
print("All done")
