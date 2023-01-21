#!/usr/bin/env python3

"""
Core code
"""

import functools
import types
import threading


class PoisonException(Exception):
    """Used to interrupt processes accessing poisoned channels."""


def process(verbose_poison=False):
    """Decorator for creating process functions.
    Annotates a function as a process and takes care of insulating parents from accidental
    poison propagation.

    If the optional 'verbose_poison' parameter is true, the decorator will print
    a message when it captures the PoisonException after the process
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


# -------------

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
        except PoisonException:
            if self.verbose_poison:
                print(f"Process poisoned: {self.fn}({self.args=}, {self.kwargs=})")
            self.poisoned = True
        return self


# TODO: Consider convenience function CSP that is just return par.run().retval
# - run should return self
# pylint: disable-next=C0103
class Parallel(Process):
    """Used to run a set of processes concurrently.
    Takes a list of processes which are started.
    Waits for the processes to complete, and returns a list of return
    values from each process.

    If check_poison is true, it will raise a ChannelPoison exception if
    any of the processes have been poisoned.

    WARNING: To make this composable required a change in how Parallel and
    Sequence are used: The outer construct must be executed by calling
    the run() method after creating the Parallel object.

    For example, a Parallel inside a Parallel:

    Parallel(
       Parallel(
          writer(ch),
          writer(ch)),
       reader(ch)
    ).run()

    Any Parallel or Sequence used inside the composition will have this
    executed by the threads spawned for them.

    The run method returns the Par or Seq itself. This makes it possible to
    use it as a chainable or extract the results as, for example, the
    following:

       rets = Parallel( .... .).run().retval.
    """
    def __init__(self, *processes, check_poison=False):
        super().__init__(None, False)
        self.processes = processes

    def run(self):
        # run, then sync with them.
        for p in self.processes:
            p.start()
        for p in self.processes:
            p.join()
        # retval is set to the return values from the processes, in the same
        # order as the processes were originally specified.
        self.retval = [p.retval for p in self.processes]
        return self


# pylint: disable-next=C0103
class Sequence(Process):
    """Used to run a set of processes one by one (waiting for one to complete before starting the next).

    Takes a list of processes (Python threads).

    The Sequence construct returns the return value when all given processes exit.

    WARNING: This is now composable, which required a change to how it is used. See the docstring
    for Parallel for more information.
    """
    def __init__(self, *processes):
        super().__init__(None, False)
        self.processes = processes

    def run(self):
        for p in self.processes:
            # Call Run directly instead of start() and join()
            # This saves some overhead, but PoisonException can suddenly be exposed here,
            # so this must be handled specifically
            try:
                p.run()
            except PoisonException:
                print("Sequence.run() caught poison exception. TODO: consider flagging p as poisoned?")
        # retval is set to the return values from the processes, in the same
        # order as the processes were originally specified.
        self.retval = [p.retval for p in self.processes]
        return self


def CSP(*procs):
    """Convenience function for running one or more processes
    or Seq / Pars and fetching the result.

    Each specified argument can be a Process, Sequence or Parallel.

    If only one is specified, the run() method of the specified object is executed.

    If multiple procs are specified, it will run everything in parallel,
    wrapping it in a Parallel.
    """
    if len(procs) == 1:
        return procs[0].run().retval
    return Parallel(*procs).run().retval


# pylint: disable-next=C0103
def Spawn(proc):
    """Spawns off and starts a PyCSP process in the background, for
    independent execution. Returns the started process."""
    proc.start()
    return proc
