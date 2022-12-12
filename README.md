PyCSP - multithreaded implementation using a shared lock through CFutures
==================================

This is one of the two most up to date implementations of PyCSP. 
The other one is the coroutine/asyncio  based implementation at
[https://github.com/PyCSP/aPyCSP](https://github.com/PyCSP/aPyCSP).

This implementation uses threads to implement CSP processes and some
of the constructs (such as Parallel).

Some of the main advantages compared to older implementations are:
- support for input _and_ output guards
- arbitrary number of readers and writers (as well as guarded reads 
  and writes through ALT) can be queued on channel ends
- there is no need for specific channel types that limit the number of readers and writers
- It is also easier to read and understand, partly due to reduced complexity. 
- Better performance compared to more complicated implementations. 

Compared to the asyncio version: 
- The implementation is perhaps easier to read and understand if you are not 
  familiar with asyncio and Python Couroutines
- PyCSP processes can use blocking calls (like systems calls) without special consideration

The major drawbacks compared to aPyCSP: 
- each process is a thread, resulting in more overhead: 
  - memory consumption
  - context switching overhead (including overhead grabbing locks)

See [the PyCSP web page](https://pycsp.github.io/) or the 
[PyCSP GitHub organisation](https://github.com/PyCSP) for more 
links and references to the different PyCSP implementations. 

### CFutures

This implementation of PyCSP uses the lock sharing technique from the 
[CPA 2018 paper](http://wotug.cs.unlv.edu/cpa2018/preprints/02-preprint.pdf). 
The implementation relies on the CFuture described in the paper, combining 
the lock management of Condition variables with result passing from Futures. 

To simplify the implementation of the core library, it was easier to
protect the core with a shared lock. The first version used a
condition variable for this, as this made it easy to implement a
Monitor around the core: a thread that needs to wait for state to
change in the core can wait for somebody else to notify and wake it
up. When the waiting thread was woken up, it needed to re-acquire the
lock, read the result and release the lock again. This created
needless overhead as the only thing the waiting thread needed was the
result.

To reduce the overhead, it would be simpler to use a Future. Python's
concurrent.future objects, however, use another Condition variable in
the implementation, adding more overhead.

CFutures combine the functionality of a shared Condition variable to
protect the core and Futures for use cases where the waiting thread
only needs to wait for a result to be set on the future.

When a thread decides to call wait on the CFuture, it essentially does two things: 
- releases the shared lock on the PyCSP core
- waits for a result to be set on the CFuture. 

The result was a simpler implementation of the core library combined
with improved performance compared both to the version that used
condition variables and older versions that used more fine-grained
locks (partly due to reduced complexity).
