#!/usr/bin/env python

# Copyright (C) 2018, Istituto di RadioAstronomia, INAF, Italy.
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
#       INAF - IRA
#	via di Fiorentina 3513
#	40059, Medicina (BO), Italy

import socket
import time

import threading
import logging.handlers

# Global vars

bind_ip = "0.0.0.0"  # Binding Server IP
bind_port = 7200  # Binding Server port
NCLIENT = 3  # Max number of client allowed
KILLALL = False  # Flag to kill all threads
TARGET = 44.5  # Target declination
BUFF_LEN = 1024  # Length of receiving buffer for server socket

STOW = 44.7  # Preferred Pointing

STATO = ["ONSOURCE", 0]  # State Machine var (status, client address requesting to move)
# allowed status are: ONSOURCE, MOVING

POSIZIONI = [44.5, 44.5, 44.5, 44.5, 44.5]  # Locally stored declinations (EW, 2N, 1N, 1S, 2S)
EW = 0  # Aliases for POSIZIONI element position
NORD2 = 1
NORD1 = 2
SUD1 = 3
SUD2 = 4

# Antenna Server
ANTENNA_IP = "192.168.30.134"  # ETH-RS232 Adapter IP connected to COM2 of Antenna
ANTENNA_PORT = 5002  # ETH-RS232 Adapter PORT connected to COM2 of Antenna
ANTENNA_IP = "127.0.0.1"  # Uncomment to use Antenna simulator
ANTENNA_PORT = 5002  # Uncomment to use Antenna simulator

RANGING_IP = "192.167.189.41"
RANGING_PORT = 5002

# ETH-RS232 Antenna low level CMDs aliases
ASK_STATUS = "STA\r"
CHK_STATUS = 'CHK\r'
MOVE_BEST = 'NS2 %s \r'
MOVE_GO = 'GO \r'

# ERROR CODES
ERR01 = "ETH-RS232 Connection failed!"
ERR02 = "ETH-RS232 CMD echo is not equal to the CMD sent"

# Setting up logging
log_filename = "/tmp/best2_server.log"
logger = logging.getLogger('DataLogger')
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s: %(message)s", "%Y/%m/%d_%H:%M:%S")
logging.Formatter.converter = time.gmtime
console_log = logging.StreamHandler()
console_log.setFormatter(formatter)
file_log = logging.handlers.TimedRotatingFileHandler(log_filename,
													 when="W0",  # every Monday
													 interval=1,  # ignored when weekly
													 backupCount=5)  # ignored when weekly

# file_log = logging.handlers.RotatingFileHandler(log_filename, maxBytes=8388608, backupCount=5)
file_log.setFormatter(formatter)
logger.addHandler(console_log)
logger.addHandler(file_log)


class Pointing:
	def __init__(self, ip="192.168.30.134", port=5002):
		self._conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self._conn.settimeout(120)
		logger.info("ETH-RS232 Connecting to the Master...")
		self.connected = False
		# print "\nConnecting to the Master... ",
		try:
			self._conn.connect((ip, port))
			logger.info("ETH-RS232 Connection estabilished!")
			self.connected = True
		except:
			logger.error(ERR01)
			return None
		# self._conn.settimeout(1)
		self.waiting = 1
		self.moving = 0
		self.buff_len = BUFF_LEN

	def readLine(self):
		line = ''
		cr = ''
		while not cr == '\r':
			cr = self._conn.recv(1)
			line = line + cr
		return line[1:]

	def _send_cmd(self, cmd):
		self._conn.send(cmd)
		# print "SENT: ",
		# print struct.unpack(str(len(cmd))+"B",cmd)
		time.sleep(0.2)
		cmd_echo = self.readLine()
		# print "RECV: ",
		# print struct.unpack(str(len(cmd_echo))+"B",cmd_echo)
		if cmd_echo == cmd:
			return True
		else:
			return False

	def get_dec(self):
		# print "[*] BEST: asking status...",
		self._conn.send(ASK_STATUS)
		# print "done"
		time.sleep(0.5)
		cmd_echo = self.readLine()
		self.waiting = True
		while self.waiting:
			try:
				# print "[*] BEST: Receiving answer"
				ans = self._conn.recv(self.buff_len)
				# print "[*] BEST: Got:", ans
				self.waiting = False
			except:
				time.sleep(0.1)
		# print "STATUS:\n", len(ans.split()),"\n", ans
		# for i in ans.split():
		#    print "--> ", len(i), i
		return ans.split()[NORD1]

	def set_dec(self, newdec):
		self._conn.send(MOVE_BEST % (newdec))
		time.sleep(1)
		self.waiting = True
		while self.waiting:
			try:
				ans = self._conn.recv(self.buff_len)
				self.waiting = False
			except:
				time.sleep(0.1)
		return ans

	def move_go(self):
		try:
			self._conn.send(MOVE_GO)
			self.moving = 1
			time.sleep(0.1)
		except:
			time.sleep(0.1)
		return "MOVING!"

	def check(self):
		self._conn.send(CHK_STATUS)
		time.sleep(0.5)
		self.send_cmd()
		self.waiting = 0
		while not self.waiting:
			try:
				ans = self._conn.recv(BUFF_LEN)
				self.waiting = 1
			except:
				time.sleep(0.1)
		return ans

	def get_status_string(self):
		try:
			if self._send_cmd(ASK_STATUS):
				ans = self.readLine()
				return " ".join(ans.split()[0:5])  # Taglio le flag
			else:
				return ERR02
		except:
			return ERR01

	def close(self):
		self._conn.close()
		logger.info("ETH-RS232 Connection closed!")
		return


def report_status():
	global POSIZIONI
	status = "  "
	for i in POSIZIONI:
		status += str(i) + "  "
	# status += "0 1 0\r"    # Flag disabilitate, non servono a niente

	return status


def client_handler(client, address):
	global STATO, POSIZIONI, KILLALL, TARGET, antenna
	try:
		while True:
			response = client.recv(1024)
			logger.info("%s:%d" % (address[0], address[1]) + " CMD Received  --> " + response + " (" + str(
				len(response)) + " char)")
			if not STATO[0] == "MOVING":
				# print "[*] TEST: ", response
				if response.split()[0] == "best" and len(response.split()) > 1:
					# stato = True
					# print response, response.split()
					TARGET = float(response.split()[-1])

					logger.info("%s:%d" % (address[0], address[1]) + " TARGET  --> " + str(TARGET))
					logger.info("%s:%d" % (address[0], address[1]) + " Sending command to Antenna MOVE")
					message = antenna.set_dec(str(TARGET))
					logger.info("%s:%d" % (address[0], address[1]) + " Sending command to Antenna GO")
					message = antenna.move_go()
					STATO[0] = "MOVING"
					STATO[1] = address[1]
					client.send("MOVING")
				else:
					if len(response) > 0:
						logger.info("%s:%d" % (address[0], address[1]) + " Request from client: " + response)
						if response.split()[0] == "best":
							logger.info("%s:%d" % (
								address[0], address[1]) + " Asking BEST-2 declination to the Antenna... -> " + response)
							message = antenna.get_status_string()
							for i in xrange(5):
								POSIZIONI[i] = float(message.split()[i])
							message = "ONSOURCE "
							message += str(POSIZIONI[NORD1])
							logger.info("%s:%d" % (address[0], address[1]) + " Antenna response: " + message)
						elif response.split()[0] == "status":
							logger.info("%s:%d" % (address[0], address[1]) + " Asking Antenna STATUS...")
							message = antenna.get_status_string()
							for i in xrange(5):
								POSIZIONI[i] = float(message.split()[i])
							message = "ONSOURCE " + message
							logger.info("%s:%d" % (address[0], address[1]) + " Antenna response: " + message)
						else:
							logger.warning(
								"%s:%d" % (address[0], address[1]) + " Unknown command received! -> " + response)
							message = "UNKNOWN CMD --> " + response.split()[0]
					else:
						logger.info("%s:%d" % (address[0], address[1]) + " Connection closed with client %s:%d" % (
							address[0], address[1]))
						break
					# tcflush(sys.stdin, TCIFLUSH)
					# message = raw_input(address[0]+" [*] Write your answer: ")
					client.send(message)
				# client.close()
			else:
				# if not address[1] == STATO[1]:
				# response = client.recv(1024)
				if len(response.split()) == 1:
					logger.info("%s:%d" % (address[0], address[1]) + " Request from client: " + response)
					if response.split()[0] == "best":
						message = "MOVING "
						message += str(POSIZIONI[NORD1])
						logger.info("%s:%d" % (
							address[0],
							address[1]) + " Reporting BEST-2 declination (Antenna is moving) --> " + message)
					elif response.split()[0] == "status":
						message = "MOVING "
						message += report_status()
						logger.info("%s:%d" % (
							address[0], address[1]) + " Reporting Antenna status (while moving) --> " + message)

					else:
						logger.warning("%s:%d" % (address[0], address[
							1]) + " Unknown command received or received a command not supported while Antenna is moving! (" +
									   response.split()[0] + ")")
						message = "CMD unknown or not supported while antenna is moving (" + response.split()[0] + ")"
				elif len(response.split()) == 2:
					logger.warning("%s:%d" % (
						address[0], address[1]) + " Unsupported command received while moving --> " + response)
					message = "Unsupported CMD received while antenna is moving --> " + response
				elif len(response) == 0:
					logger.info("%s:%d" % (address[0], address[1]) + " Connection closed with client %s:%d" % (
						address[0], address[1]))
					break
				else:
					logger.warning("%s:%d" % (address[0], address[1]) + " Malformed or unknown request --> " + response)
					message = "???????"
				# tcflush(sys.stdin, TCIFLUSH)
				# message = raw_input(address[0]+" [*] Write your answer: ")
				client.send(message)

			if KILLALL:
				logger.info("%s:%d" % (address[0], address[1]) + " Killed Client handler")
				break
	except:
		logger.info(
			"%s:%d" % (address[0], address[1]) + " Connection closed with client %s:%d" % (address[0], address[1]))


def ascolto_puntamento(client, address):
	global STATO, KILLALL, TARGET, POSIZIONI
	while True:
		if STATO[0] == "MOVING" and STATO[1] == address[1]:
			move_ack = "START"
			logger.info("%s:%d" % (address[0], address[1]) + " Waiting for Antenna pointing messages...")
			while not move_ack == "NSOURCE\r" and not move_ack.split()[0].upper() == "RROR":
				move_ack = antenna.readLine()
				logger.info("%s:%d" % (address[0], address[1]) + " Received from Antenna --> " + move_ack)
				if len(move_ack.split()) == 8:
					for i in xrange(5):
						POSIZIONI[i] = float(move_ack.split()[i])
			logger.info("%s:%d" % (address[0], address[1]) + " MOVE ACK=" + move_ack)
			if move_ack == "NSOURCE\r":
				STATO[0] = "ONSOURCE"
				logger.info("%s:%d" % (address[0], address[1]) + " Antenna ONSOURCE")
				logger.info("%s:%d" % (address[0], address[1]) + " Sending declination %3.1f to the Ranging System" % (POSIZIONI[2]))
				try:
					s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
					s.connect((RANGING_IP, RANGING_PORT))
					s.send("dec %3.1f \n" % (POSIZIONI[2]))
					time.sleep(0.2)
					ans = s.recv(1024)
					if ans.split()[0] == "ack":
						logger.info("%s:%d" % (address[0], address[1]) + " Received ACK from the Ranging System!")
					else:
						logger.warning("%s:%d" % (address[0], address[1]) + " Received NAK from the Ranging System! ***")
					s.close()
				except:
					logger.warning(
						"%s:%d" % (address[0], address[1]) + " Connection Failed with the Ranging System at %s:%d" % (
						RANGING_IP, RANGING_PORT))
			else:
				STATO[0] = "ERROR"
				logger.error("%s:%d" % (address[0], address[1]) + " Antenna ERROR: " + move_ack[4:])
				if KILLALL:
					break


def ammazza_client(client, address):
	global KILLALL
	while True:
		if KILLALL:
			client.close()
			break


server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((bind_ip, bind_port))
server.listen(NCLIENT)
logger.info("\r##########################################################################\n")
logger.info("Program started")

logger.info("Server Waiting for clients connections... (max " + str(NCLIENT) + " allowed!)")

logger.info("Connecting to the Antenna @ " + ANTENNA_IP + ":" + str(ANTENNA_PORT) + "...")
antenna = Pointing(ip=ANTENNA_IP, port=ANTENNA_PORT)
if not antenna == None and antenna.connected:
	logger.info("Antenna connection established!")
else:
	logger.error("Unable to connect with the RS232-ETH adapter (Antenna Pointing System)")
	logger.info("Program terminated")
	exit()

logger.info("Asking Antenna Status...")
message = antenna.get_status_string()
for i in xrange(5):
	POSIZIONI[i] = float(message.split()[i])
logger.info("Received Status from Antenna --> " + message)

try:
	while True:
		client, address = server.accept()
		if len(address) > 0:
			logger.info("Connected to : %s:%d" % (address[0], address[1]))

		handler = threading.Thread(target=client_handler, args=(client, address))
		handler.start()

		msgs = threading.Thread(target=ascolto_puntamento, args=(client, address))
		msgs.start()

		uccidi = threading.Thread(target=ammazza_client, args=(client, address))
		uccidi.start()



except KeyboardInterrupt:
	KILLALL = True
	server.close()
	del (server)
	logger.info("Closing Threads...")
	time.sleep(0.5)
	logger.info("Execution terminated by the user (KeyboardInterrupt exception)\n")
	exit(0)
