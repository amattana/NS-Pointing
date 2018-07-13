#!/usr/bin/env python

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

import socket,time,sys
import threading
from termios import tcflush, TCIFLUSH

bind_ip = "0.0.0.0"
bind_port = 5002

stato = False
killall = False
target = 44.5

# Preferred Pointing
STOW = 44.7

# CMDs
ASK_STATUS = "STA\r"
CHK_STATUS = 'CHK\r'
MOVE_BEST = 'NS2 %s \r'
MOVE_GO   = 'GO \r'

# ANT_NUM
EW    = 0
NORD2 = 1
NORD1 = 2
SUD1  = 3
SUD2  = 4

# ERROR CODES
ERR01 = "\tETH-RS232 Connection failed!"
ERR02 = "\tETH-RS232 CMD echo is not equal to the CMD sent"

posizioni = [445, 445, 445, 445, 445]


server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((bind_ip, bind_port))
server.listen(3)
print "Waiting for connections: "

def get_status():
    global posizioni
    status = "  "
    for i in posizioni:
        status += str(i/10.)+"  "
    status += "0 1 0\r"
    return status

def client_handler(client,address):
    global stato, killall, target, posizioni
    message = "[*] ANTENNA: UNEXPECTED ERROR"
    try:
        while True:
            request = client.recv(1024);
            #print "ricevuto: ", request, "\n", len(request.split())
            if request.split()[0] == "NS2" and len(request.split())>1:
                #stato = True
                #print response, response.split()
                target = float(request.split()[1])
                print "[*] ANTENNA: TARGET  --> ", target#, request, len(request.split())
                if len(request.split())>2:
                    client.send(" "+request.split()[0] + " " + request.split()[1] + " \r")
                    if request.split()[2]=="GO":
                        print "[*] ANTENNA: Received GO"
                        stato = True
                else:
                    client.send(" "+request)
            elif request.split()[0]=="GO":
                print "[*] ANTENNA: Received GO"
                client.send(" "+request)
                stato = True
            else:
                client.send(" "+request)
                if len(request) > 0:
                    print "[*] ANTENNA: Request from client:", request
                else:
                    print "[*] ANTENNA: Connection closed"
                    break
                #tcflush(sys.stdin, TCIFLUSH)
                if request.split()[0]==ASK_STATUS.split()[0]:
                    print "[*] ANTENNA: Getting Status", request.split()[0]
                    message = get_status()
                    print "[*] ANTENNA: Sending Status", message
                elif request.split()[0]=="NS2":
                    message = get_status().split()[NORD1]
                client.send(" "+message)
            #client.close()
            if killall:
                print "[*] ANTENNA: Kill Client Handler"
                break
    except:
        print "[*] ANTENNA EXCEPTION! Connection closed..."

def sparo_cazzate(client,address):
    global stato, killall, target, posizioni
    while True:
        if stato:
            print "[*] ANTENNA: Sending status messages..."
            time.sleep(10)
            #client.send(" MOVING\r")
            while not int(posizioni[NORD1])==int(target*10):
                if int(posizioni[NORD1]) < int(target*10):
                    posizioni[NORD1] = posizioni[NORD1] + 1
                else:
                    posizioni[NORD1] = posizioni[NORD1] - 1
                time.sleep(0.2)
                print "[*] ANTENNA:",get_status()
                client.send(get_status())
            print "[*] ANTENNA: ONSOURCE"
            client.send("ONSOURCE\r")
            stato = False
        if killall:
            break

def ammazza_client(client, address):
    global killall
    while True:
        if killall:
            client.close()
            break

try:
    while True:
        client, address = server.accept()
        if len(address) > 0:
            print "[*] ANTENNA: Connected to : %s:%d" % (address[0], address[1])

        handler = threading.Thread(target=client_handler, args=(client, address))
        handler.start()

        msgs = threading.Thread(target=sparo_cazzate, args=(client, address))
        msgs.start()

        uccidi = threading.Thread(target=ammazza_client, args=(client, address))
        uccidi.start()



except KeyboardInterrupt:
    killall = True

    server.close()
    del(server)
    print "[*] ANTENNA: Closing Thread..."
    time.sleep(0.5)
    print "[*] ANTENNA: Ended"
    exit(0)
