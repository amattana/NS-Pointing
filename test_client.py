#!/usr/bin/env python
#
# Copyright (C) 2016, Osservatorio di RadioAstronomia, INAF, Italy.
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
# 
# Correspondence concerning this software should be addressed as follows:
#
#	Andrea Mattana
#	Radiotelescopi di Medicina
#       INAF - ORA
#	via di Fiorentina 3513
#	40059, Medicina (BO), Italy

"""
Provides a socket comunication between the RS-232 lane 
of the Northern Cross Pointing System Computer 
done by Andrea Maccaferri for the Pulsar Scheduler(1990)
"""

# Python modules
import sys
import socket
import time
import threading

import datetime
import os,sys
from termios import tcflush, TCIFLUSH

__author__ = "Andrea Mattana"
__copyright__ = "Copyright 2016, Osservatorio di RadioAstronomia, INAF, Italy"
__credits__ = ["Andrea Mattana"]
__license__ = "GPL"
__version__ = "1.0"
__maintainer__ = "Andrea Mattana"


BUFFER_SIZE = 1024

KILLALL = False
MOVING = False

def ricevi_posizioni(s, BUFFER_SIZE):
    global KILLALL, MOVING
    while True:
        if MOVING:
            ans = "PARTI DAI"
            while not ans.split()[0] == "ONSOURCE":
                ans = s.recv(BUFFER_SIZE)
                dividi = ans.split(chr(10))
                for i in dividi:
                    if len(i)>0:
                        print "  -  Received msg: ", len(i), "-->", i
                if not dividi[-1] == "":
                    ans = dividi[-1]
                else:
                    ans = dividi[-2]
            MOVING = False
            sys.stdout.write("\n* Type the server cmd: ")
            sys.stdout.flush()

        if KILLALL:
            break


if __name__=="__main__":
    from optparse import OptionParser

    #command line parsing
    op = OptionParser()
    op.add_option("-p", "--port", type="int", dest="port", default=7200)
    op.add_option("-a", "--addr", dest="addr", default="127.0.0.1")
    opts, args = op.parse_args(sys.argv[:])

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((opts.addr, opts.port))

    #msgs = threading.Thread(target=ricevi_posizioni, args=(s, BUFFER_SIZE))
    #msgs.start()

    try:
        print "\nEscape command is \'quit\'\n"
        msg = ""
        tcflush(sys.stdin, TCIFLUSH)
        msg = raw_input("* Type the server cmd: ")

        while not msg=="quit":
            print("Commanding: \'" + msg + "\'...")
            s.sendall(msg)
            #time.sleep(1)
            data = s.recv(BUFFER_SIZE)
            print "\t-\tReceived answer: ", data
            if msg.split()[0]=="best" and len(msg.split())>1 and data == "MOVING\r":
                MOVING = True
            tcflush(sys.stdin, TCIFLUSH)
            msg = raw_input("* Type the server cmd: ")
        KILLALL = True
        s.close()
        print("Closing Comunication.")
        del (s)
        print("Ended Successfully")

    except KeyboardInterrupt:
        KILLALL = True
        print("Closing Comunication.")
        s.close()
        del (s)
        print("Ended Successfully")




