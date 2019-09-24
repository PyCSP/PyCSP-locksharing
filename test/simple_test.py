#!/usr/bin/env python3

#############################################################
        
from common import *
from pycsp import *
from pycsp.plugNplay import *
import os
import time
import pycsp



def schan_test():
    print("************************************************************")
    print("Simple channel test")
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


def sguard_test():
    print("************************************************************")
    print("Simple guarded channel test")

    @process
    def writer(p, cout):
        pref = " " * p * 2
        for i in range(10):
            val = (p, i)
            print(f"{pref} W {p} -> {val}")
            cout(val)
            print(f"{pref} W {p} write done")
            time.sleep(random.random()*3+2)
        print(f"{pref} W {p} finishing")            
        #cout.poison()
        
    @process
    def reader(p, cin):
        pref = " " * p * 2
        for i, m in enumerate(cin):
            print(f"{pref} R  {p} got {m} {i}")
            if i == 9:
                break

    @process
    def gread(p, cin):
        pref = " " * p * 2
        alt = Alternative(cin)
        for i in itertools.count():
            if i == 10:
                break # TODO poison doesn't work for alt.select yet
            print(f"{pref} AR  {p} waiting")
            with alt as (g, val):
                print(f"{pref} AR  {p} got {val} from {g}")

    @process
    def gwrite(p, cout):
        pref = " " * p * 2
        for i in range(10):
            val = (p, i)
            print(f"{pref} AW {p} -> {val}")
            g = cout.alt_pending_write(val)
            alt = Alternative(g)
            ret = alt.select()
            print(f"{pref} AW {p} done")
            time.sleep(random.random()*3+2)
        print(f"{pref} AW {p} finishing")            
        #cout.poison()


    ch = Channel()
    Parallel(
        writer(1, ch.write),
        reader(2, ch.read),
        gread(3, ch.read),
        gwrite(4, ch.write)
    )

    print("All done")


    
#schan_test()
sguard_test()
