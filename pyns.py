#!/usr/bin/env python

import sys, socket
import numpy as n
from PyQt4 import QtCore, QtGui, uic
import Image
import time, datetime
from threading import Thread
import ephem

catfile = "VIII_1A_3cr-120303b.csv"

antenna_group = [[1],  # 1N
				 [0, 1, 2, 3]]  # 2N, 1N, 1S, 2S


def juldate2ephem(num):
	"""Convert Julian date to ephem date, measured from noon, Dec. 31, 1899."""
	return ephem.date(num - 2415020.)


def ephem2juldate(num):
	"""Convert ephem date (measured from noon, Dec. 31, 1899) to Julian date."""
	return float(num + 2415020.)


def get_common_name(name):
	common_name = {'3C144': 'Tau',
				   '3C461': 'Cas-A',
				   '3C405': 'Cyg-A',
				   '3C274': 'Virgo'}
	if name in common_name.keys():
		return common_name[name]
	else:
		return ''


sun = ephem.Sun()
obs = ephem.Observer()
obs.long = 11.645929 * (ephem.pi / 180.)  # Medicina Longitude
obs.lat = 44.523733 * (ephem.pi / 180.)  # Medicina Latitude
obs.epoch = 2000.0


def clickable(widget):
	class Filter(QtCore.QObject):
		clicked = QtCore.pyqtSignal()

		def eventFilter(self, obj, event):
			if obj == widget:
				if event.type() == QtCore.QEvent.MouseButtonRelease:
					if obj.rect().contains(event.pos()):
						self.clicked.emit()
						return True
			return False

	filter = Filter(widget)
	widget.installEventFilter(filter)
	return filter.clicked


def calib_source():
	cat = open(catfile, 'r')

	# Read the catalogue file, ignoring commented lines
	catstr = ''
	# print "Reading catalogue \'%s\'"%catfile
	for line in cat.readlines():
		if line[0] != '#':
			catstr = catstr + line

	catlist = catstr.split('\n')[2:]  # skip title and unit lines
	n_entries = len(catlist)
	epoch = 1950
	body_list = []
	for rn, row in enumerate(catlist):
		if row == '':
			break
		cells = row.split(',')
		name = '3C' + cells[0]
		# print row,cells
		ra = cells[1].replace(' ', ':')
		dec = cells[2].replace(' ', ':')
		flux = n.log10(
			float(cells[3]))  # log flux, so we can store in the magnitude field, which has a relatively small range
		ephemline = '%s,f,%s,%s,%s,%d' % (name, ra, dec, flux, epoch)
		body = ephem.readdb(ephemline)
		body_list.append(body)

	args = [str(ephem.julian_date())]
	for date in args:
		# print '##########################################################################################################################'
		if '/' in date:
			jd = ephem.julian_date(date)
		else:
			jd = float(date)

		obs.date = juldate2ephem(jd)

		sun.compute(obs)
		lst = obs.sidereal_time()
		# print 'LST:', lst,
		ra = obs.sidereal_time()
		# print '(',(ra.real/(ephem.pi))*180.,')',
		# print '     Julian Date:', jd,
		# print '     Day:', obs.date
		# print 'Sun is at (RA, DEC): (%s,%s)' %(str(sun.ra), str(sun.dec))

		common_name = {'3C144': 'Tau',
					   '3C461': 'CasA',
					   '3C405': 'CygA',
					   '3C274': 'Virgo'}

		result = []
		for body in body_list:
			body.compute(obs)
			if body.name in common_name.keys():
				obs.date = juldate2ephem(jd)
				next_transit = obs.next_transit(body)
				time_to_transit = next_transit - juldate2ephem(jd)
				ha = lst - body.ra
				# unwrap
				if ha > n.pi:
					ha = ha - 2 * n.pi
				elif ha < -n.pi:
					ha = ha + 2 * n.pi

				time_to_transit = time_to_transit * 24 * 60 * 60
				left = "%02d"%(time_to_transit/60/60)+":"+"%02d"%(time_to_transit/60%60)+":"+"%02d"%(time_to_transit%60)

				result += ["%-7s %+8s : RA: %11s  DEC: %11s  FLUX: %8s  TRANSIT (UTC): %-20s %.3f    HA: %12s  %s" % (
					body.name, get_common_name(body.name), body.ra, body.dec, '%.2f' % (10 ** body.mag), next_transit,
					ephem.julian_date(next_transit), ephem.hours(ha), left)]
	a=sorted(result, key=lambda tup: tup.split()[13])
	return a


def primi2deg(dec):
	a = dec.split(":")
	return ("%3.1f" % (float(a[0]) + (float(a[1]) / 60.0) + (float(a[2]) / 3600)))


class ImageDialog(QtGui.QMainWindow):
	# Signal for Slots
	antenna_signal = QtCore.pyqtSignal()
	time_left = QtCore.pyqtSignal()

	def __init__(self, uiFile):
		""" Initialise main window """
		super(ImageDialog, self).__init__()
		# Set up the user interface from Designer.
		self.ui = uic.loadUi(uiFile)
		self.setCentralWidget(self.ui)
		self.resize(802, 740)
		self.show()

		self.connected = False
		self.status = "UNDEFINED"
		self.armed = False

		self.ramo = 0

		self.status_string = "  +56.0  +44.5   +44.5  +44.5   +44.5 0 1 0"
		self.target_type = "arb"
		self.actual_dec = [0, 0, 0, 0]  # quella disegnata
		self.target_dec = [None, None, None, None]  # quella da raggiungere
		self.current_dec = [90, 90, 90, 90]  # quella letta nello status

		self.image = QtGui.QImage("small_bg.png")
		self.image2 = QtGui.QImage("small_fg.png")

		self.overlay = Image.open("small_arrow.png")
		ov = self.overlay.rotate(0).tobytes("raw", "RGBA")
		self.qov = QtGui.QImage(ov, self.overlay.size[0], self.overlay.size[1], QtGui.QImage.Format_ARGB32)

		# self.ui.comboBox.setEnabled(False)
		self.ui.arbitrary_dec.setEnabled(False)
		self.ui.button_move_arb.setEnabled(False)
		# self.ui.button_move_src.setEnabled(False)
		self.ui.cb_sel_ramo.setEnabled(False)

		self.process_antenna_status = Thread(target=self.antenna_check)
		self.process_time_left = Thread(target=self.rs_time_left)
		self.process_time_left.start()
		self.stopThreads = False

		painter = QtGui.QPainter()
		painter.begin(self.image)
		painter.drawImage(0, 0, self.qov)
		painter.drawImage(0, 0, self.image2)
		painter.end()

		font = QtGui.QFont()
		font.setPointSize(22)
		font.setBold(True)
		font.setWeight(75)

		self.ant_pics = []
		self.ant_pos = []
		for i in xrange(4):
			self.ant_pics += [QtGui.QLabel(self.ui.tab_dec)]
			self.ant_pics[i].setGeometry(30 + (190 * i), 70, 140, 140)
			self.ant_pics[i].setPixmap(QtGui.QPixmap.fromImage(self.image))
			self.ant_pos += [QtGui.QLabel(self.ui.tab_dec)]
			self.ant_pos[i].setGeometry(30 + (190 * i), 20, 140, 40)
			self.ant_pos[i].setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
			self.ant_pos[i].setStyleSheet("background-color: rgb(255, 255, 255)")
			self.ant_pos[i].setFont(font)
			self.ant_pos[i].setText("44.5")

		self.initPics()
		self.ui.show()

		try:
			self.create_rs_table()
			for i in range(len(self.rs_records)):
				self.rs_records[i]['button_move'].clicked.connect(lambda: self.point_antenna(self.rs_records[i]['name']+","+self.rs_records[i]['dec']))
		except:
			print "\nError: Unable to find a radio source catalogue file!\n"

		self.server_ip = "127.0.0.1"
		self.server_port = 7000
		self.server_polling = 5
		self.client = None
		self.client_buff_len = 1024

		# Connect up the buttons.
		self.ui.button_move_arb.clicked.connect(lambda: self.point_antenna('arb'))
		# self.ui.button_move_src.clicked.connect(lambda: self.point_antenna('src'))
		clickable(self.ui.label_enabled).connect(lambda: self.action_enable())
		clickable(self.ui.label_connected).connect(lambda: self.action_connect())
		self.ui.cb_sel_ramo.currentIndexChanged.connect(lambda: self.select_ramo())

	def create_rs_table(self):
		rs = calib_source()
		self.rs_records = []
		for i in range(len(rs)):
			self.rs_records += [{}]
			self.rs_records[i]['name'] = QtGui.QLabel(self.ui.tab_dec)
			self.rs_records[i]['name'].setGeometry(QtCore.QRect(20, 440 + (i * 30), 81, 31))
			font = QtGui.QFont()
			font.setBold(True)
			font.setWeight(75)
			self.rs_records[i]['name'].setFont(font)
			self.rs_records[i]['name'].setFrameShape(QtGui.QFrame.Box)
			self.rs_records[i]['name'].setAlignment(QtCore.Qt.AlignCenter)
			self.rs_records[i]['name'].setText(rs[i].split()[1])
			self.rs_records[i]['name'].show()

			self.rs_records[i]['astroname'] = QtGui.QLabel(self.ui.tab_dec)
			self.rs_records[i]['astroname'].setGeometry(QtCore.QRect(100, 440 + (i * 30), 81, 31))
			font = QtGui.QFont()
			font.setBold(False)
			font.setWeight(50)
			self.rs_records[i]['astroname'].setFont(font)
			self.rs_records[i]['astroname'].setFrameShape(QtGui.QFrame.Box)
			self.rs_records[i]['astroname'].setAlignment(QtCore.Qt.AlignCenter)
			self.rs_records[i]['astroname'].setText(rs[i].split()[0])
			self.rs_records[i]['astroname'].show()

			self.rs_records[i]['flux'] = QtGui.QLabel(self.ui.tab_dec)
			self.rs_records[i]['flux'].setGeometry(QtCore.QRect(180, 440 + (i * 30), 91, 31))
			font = QtGui.QFont()
			font.setBold(False)
			font.setWeight(50)
			self.rs_records[i]['flux'].setFont(font)
			self.rs_records[i]['flux'].setFrameShape(QtGui.QFrame.Box)
			self.rs_records[i]['flux'].setAlignment(QtCore.Qt.AlignCenter)
			self.rs_records[i]['flux'].setText(rs[i].split()[8])
			self.rs_records[i]['flux'].show()

			self.rs_records[i]['dec'] = QtGui.QLabel(self.ui.tab_dec)
			self.rs_records[i]['dec'].setGeometry(QtCore.QRect(270, 440 + (i * 30), 91, 31))
			font = QtGui.QFont()
			font.setBold(False)
			font.setWeight(50)
			self.rs_records[i]['dec'].setFont(font)
			self.rs_records[i]['dec'].setFrameShape(QtGui.QFrame.Box)
			self.rs_records[i]['dec'].setAlignment(QtCore.Qt.AlignCenter)
			self.rs_records[i]['dec'].setText(primi2deg(rs[i].split()[6]))
			self.rs_records[i]['dec'].show()

			self.rs_records[i]['transit'] = QtGui.QLabel(self.ui.tab_dec)
			self.rs_records[i]['transit'].setGeometry(QtCore.QRect(360, 440 + (i * 30), 191, 31))
			font = QtGui.QFont()
			font.setBold(False)
			font.setWeight(50)
			self.rs_records[i]['transit'].setFont(font)
			self.rs_records[i]['transit'].setFrameShape(QtGui.QFrame.Box)
			self.rs_records[i]['transit'].setAlignment(QtCore.Qt.AlignCenter)
			self.rs_records[i]['transit'].setText(rs[i].split()[11] + " " + rs[i].split()[12])
			self.rs_records[i]['transit'].show()

			self.rs_records[i]['remaining'] = QtGui.QLabel(self.ui.tab_dec)
			self.rs_records[i]['remaining'].setGeometry(QtCore.QRect(550, 440 + (i * 30), 121, 31))
			font = QtGui.QFont()
			font.setBold(False)
			font.setWeight(50)
			self.rs_records[i]['remaining'].setFont(font)
			self.rs_records[i]['remaining'].setFrameShape(QtGui.QFrame.Box)
			self.rs_records[i]['remaining'].setAlignment(QtCore.Qt.AlignCenter)
			self.rs_records[i]['remaining'].setText("-"+rs[i].split()[16])
			self.rs_records[i]['remaining'].show()

			self.rs_records[i]['move'] = QtGui.QLabel(self.ui.tab_dec)
			self.rs_records[i]['move'].setGeometry(QtCore.QRect(670, 440 + (i * 30), 91, 31))
			font = QtGui.QFont()
			font.setBold(False)
			font.setWeight(50)
			self.rs_records[i]['move'].setFont(font)
			self.rs_records[i]['move'].setFrameShape(QtGui.QFrame.Box)
			self.rs_records[i]['move'].setAlignment(QtCore.Qt.AlignCenter)
			self.rs_records[i]['move'].show()

			self.rs_records[i]['button_move'] = QtGui.QPushButton(self.ui.tab_dec)
			self.rs_records[i]['button_move'].setGeometry(QtCore.QRect(680, 444 + (i * 30), 71, 22))
			self.rs_records[i]['button_move'].setText("Go!")
			self.rs_records[i]['button_move'].setEnabled(False)
			self.rs_records[i]['button_move'].show()

	def updatetimeleft(self):
			self.create_rs_table()

	def action_connect(self):
		if not self.connected:
			self.server_ip = self.ui.server_ip.text()
			self.server_port = int(self.ui.server_port.text())
			self.server_polling = int(self.ui.poll_time.text())
			self.ui.comment.setText("Connecting to server " + self.server_ip + ":" + str(self.server_port))
			time.sleep(0.2)
			try:
				self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
				self.client.connect((self.server_ip, self.server_port))
				if not self.client == None:
					self.ui.label_connected.setText("ONLINE")
					self.ui.label_connected.setStyleSheet("background-color: rgb(0, 255, 0); color: rgb(0, 0, 0)")
					if not self.process_antenna_status.isAlive():
						self.process_antenna_status.start()
					self.ui.comment.setText("Successfully Connected to the Antenna Server")
					self.connected = True
			except:
				self.ui.comment.setText(
					"ERROR: Unable to connect to server " + self.server_ip + ":" + str(self.server_port))
				self.connected = False
				self.ui.label_connected.setText("OFFLINE")
				self.ui.label_connected.setStyleSheet("background-color: rgb(122, 122, 122); color: rgb(255, 255, 255)")
		else:
			self.ui.label_connected.setText("OFFLINE")
			self.ui.label_connected.setStyleSheet("background-color: rgb(122, 122, 122); color: rgb(255, 255, 255)")
			self.connected = False
			self.ui.comment.setText(
				"Disconnected from the Antenna Server" + self.server_ip + ":" + str(self.server_port))
			if self.client is not None:
				self.client = None

	def antenna_check(self):
		while True:
			if self.connected:
				self.status, self.current_dec = self.ask_status()
				if not self.current_dec == self.actual_dec:
					self.antenna_signal.emit()
				time.sleep(self.server_polling - 1)
			time.sleep(1)
			if self.stopThreads:
				break

	def rs_time_left(self):
		while True:
			self.time_left.emit()
			time.sleep(3)
			if self.stopThreads:
				break


	def ask_status(self):
		self.client.send("status")
		ans = self.client.recv(self.client_buff_len).split()
		pos = ans[2:6]
		status = ans[0]
		for i in xrange(len(pos)):
			pos[i] = float(pos[i])
		# print pos, status
		return status, pos

	def select_ramo(self):
		self.ramo = int(self.ui.cb_sel_ramo.currentIndex())

	#def calc_src_dec(self):
    #	return float(self.ui.comboBox.currentText().split("-")[0])

	def draw_antenna(self, pos):
		print "Draw"

	def action_enable(self):
		if not self.armed:
			self.move_arm()
		else:
			self.move_disarm()

	def move_disarm(self):
		self.ui.label_enabled.setText("DISABLED")
		self.ui.label_enabled.setStyleSheet("background-color: rgb(122, 122, 122); color: rgb(255, 255, 255)")
		self.ui.arbitrary_dec.setEnabled(False)
		self.ui.button_move_arb.setEnabled(False)
		self.ui.comboBox.setEnabled(False)
		self.ui.button_move_src.setEnabled(False)
		self.ui.cb_sel_ramo.setEnabled(False)
		self.armed = False

	def move_arm(self):
		self.ui.label_enabled.setText("ENABLED")
		self.ui.label_enabled.setStyleSheet("background-color: rgb(0, 255, 0); color: rgb(0, 0, 0)")
		self.ui.arbitrary_dec.setEnabled(True)
		self.ui.button_move_arb.setEnabled(True)
		#self.ui.comboBox.setEnabled(True)
		#self.ui.button_move_src.setEnabled(True)
		self.ui.cb_sel_ramo.setEnabled(True)
		self.armed = True

	def point_antenna(self, dst='arb'):
		self.target_type = dst
		result = QtGui.QMessageBox.question(self,
											"Confirm to Move...",
											"Are you sure you want to Move the Antenna?",
											QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
		if result == QtGui.QMessageBox.Yes:
			if dst == "arb":
				angle = float(self.ui.arbitrary_dec.text())
				print "Pointing Antenna to Declination ", str(angle)
				self.client.send("best " + str(angle))
			else:
				angle = float(dst.split(",")[1])
				print "Pointing Antenna to RadioSource " + dst.split(",")[0] + " @ " + str(angle)
				self.client.send("best " + str(angle))

			ans = self.client.recv(self.client_buff_len).split()[0]
			if ans == "MOVING":
				self.status = "MOVING"
				self.ui.comment.setText("Antenna is Moving")
				for i in antenna_group[self.ramo]:
					self.target_dec[i] = float("%3.1f" % angle)
				self.move_disarm()
			else:
				self.ui.comment.setText("ERROR")

	def updateDec(self):
		# print "Running SLOT"
		for i in xrange(4):

			self.ant_pos[i].setText("%3.1f" % (self.current_dec[i]))
			self.ant_pos[i].show()

			ov_actual = self.overlay.rotate((self.current_dec[i] - 44.5)).tobytes("raw", "RGBA")
			self.qov_actual = QtGui.QImage(ov_actual, self.overlay.size[0], self.overlay.size[1],
										   QtGui.QImage.Format_ARGB32)

			if not self.target_dec[i] is None:
				ov = self.overlay.rotate((self.target_dec[i] - 44.5)).tobytes("raw", "RGBA")
				self.qov = QtGui.QImage(ov, self.overlay.size[0], self.overlay.size[1], QtGui.QImage.Format_ARGB32)

			self.image = QtGui.QImage("small_bg.png")
			self.image2 = QtGui.QImage("small_fg.png")

			painter = QtGui.QPainter()
			painter.begin(self.image)
			painter.drawImage(0, 0, self.qov_actual)
			if not self.target_dec[i] is None:
				painter.setOpacity(0.5)
				painter.drawImage(0, 0, self.qov)
			painter.setOpacity(1)
			painter.drawImage(0, 0, self.image2)
			painter.end()

			self.ant_pics[i].setPixmap(QtGui.QPixmap.fromImage(self.image))
			self.ant_pics[i].show()

		self.ui.label_status.setText(self.status)
		if self.status == "ONSOURCE":
			self.ui.label_status.setStyleSheet("background-color: rgb(0, 255, 0); color: rgb(0, 0, 0)")
			self.server_polling = float(self.ui.poll_time.text())
		elif self.status == "MOVING":
			self.ui.label_status.setStyleSheet("background-color: rgb(255, 255, 0); color: rgb(0, 0, 0);")
			self.server_polling = 1
		elif self.status == "ERROR":
			self.ui.label_status.setStyleSheet("background-color: rgb(255, 0, 0); color: rgb(255, 255, 255)")
			self.server_polling = float(self.ui.poll_time.text())
		else:
			self.ui.label_status.setStyleSheet("background-color: rgb(122, 122, 122); color: rgb(255, 255, 255);")

		self.ui.comment.setText(datetime.datetime.strftime(
			datetime.datetime.utcfromtimestamp(time.time()), "Last update: %Y/%m/%d %H:%M:%S UTC"))

	def initPics(self):

		for i in xrange(4):
			self.ant_pos[i].setText("---")
			self.ant_pos[i].show()

			ov = self.overlay.tobytes("raw", "RGBA")
			self.qov = QtGui.QImage(ov, self.overlay.size[0], self.overlay.size[1], QtGui.QImage.Format_ARGB32)

			self.image = QtGui.QImage("small_bg.png")
			self.image2 = QtGui.QImage("small_fg.png")

			painter = QtGui.QPainter()
			painter.begin(self.image)
			painter.setOpacity(0.5)
			painter.drawImage(0, 0, self.qov)
			painter.setOpacity(1)
			painter.drawImage(0, 0, self.image2)
			painter.end()

			self.ant_pics[i].setPixmap(QtGui.QPixmap.fromImage(self.image))
			self.ant_pics[i].show()

	def closeEvent(self, event):
		result = QtGui.QMessageBox.question(self,
											"Confirm Exit...",
											"Are you sure you want to exit ?",
											QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
		event.ignore()

		if result == QtGui.QMessageBox.Yes:
			event.accept()
			self.connected = False
			self.stopThreads = True
			print "Stopping Threads"
			time.sleep(0.5)


if __name__ == "__main__":
	# parser = OptionParser()
	#
	# parser.add_option("-f", "--file",
	#                   dest="spe_file",
	#                   default="",
	#                   help="Input Time Domain Data file '.tdd' saved using tpm_dump.py")
	#
	# parser.add_option("-d", "--directory",
	#                   dest="directory",
	#                   default="",
	#                   help="Directory containing '.tdd' files to be averaged")
	#
	# (options, args) = parser.parse_args()

	app = QtGui.QApplication(sys.argv)
	window = ImageDialog("gui_ns_pointing.ui")
	window.antenna_signal.connect(window.updateDec)
	window.time_left.connect(window.updatetimeleft)

	sys.exit(app.exec_())
