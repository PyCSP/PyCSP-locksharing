#!/usr/bin/env python3
# -*- coding: latin-1 -*-
"""
Copyright (c) 2018 John Markus Bjørndalen, jmb@cs.uit.no.
See LICENSE.txt for licensing details (MIT License).
"""
from common import *
import time
from pycsp import Channel, process, Parallel

@process
def writer(N, cout):
    for i in range(N):
        cout(i)

@process        
def reader(N, cin):
    for i in range(N):
        v = cin()

@process
def reader_verb(N, cin):
    for i in range(N):
        v = cin()
        print(v, end=" ")

# We're doing the timing inside the reader and writer procs to time the
# channel overhead without the process start/stop overhead.
# We add 10 write+reads as a warmup time and to make sure both are ready. 
@process
def writer_timed(N, cout):
    global t1
    for i in range(10):
        cout(i)
    t1 = time.time()
    for i in range(N):
        cout(i)

@process        
def reader_timed(N, cin):
    global t2
    for i in range(N+10):
        v = cin()
    t2 = time.time()

        
        
N = 10
c = Channel('a')
Parallel(writer(N, c.write),
         reader_verb(N, c.read))

def run_timing(read_end, write_end):
    dts = []
    for i in range(5):
        N = 1000
        print(f"Run {i}:", end="")
        #t1 = time.time()
        Parallel(writer_timed(N, write_end),
                 reader_timed(N, read_end))
        #t2 = time.time()
        dt_ms    = (t2-t1) * 1000
        dt_op_us = (dt_ms / N) * 1000
        print(f"  DT    = {dt_ms:8.3f} ms  per op: {dt_op_us:8.3f} us")
        dts.append(dt_op_us)
    print(" -- min {:.3f} avg {:.3f} max {:.3f} ".format(min(dts), avg(dts), max(dts)))

    
print("timing with channel ends")
run_timing(c.read, c.write)    

print("timing with _read and _write directly")
run_timing(c._read, c._write)    
    
