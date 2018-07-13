#!/usr/bin/env python

import sys, socket
import numpy as np
from PyQt4 import QtCore, QtGui, uic
import Image
import time, datetime
from threading import Thread
antenna_group = [[1],       # 1N
                 [0,1,2,3]]  # 2N, 1N, 1S, 2S


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


class ImageDialog(QtGui.QMainWindow):
    # Signal for Slots
    antenna_signal = QtCore.pyqtSignal()

    def __init__(self, uiFile):
        """ Initialise main window """
        super(ImageDialog, self).__init__()
        # Set up the user interface from Designer.
        self.ui = uic.loadUi(uiFile)
        self.setCentralWidget(self.ui)
        self.resize(710,500)
        self.show()

        self.connected = False
        self.status = "UNDEFINED"
        self.armed = False

        self.ramo = 0

        self.status_string  = "  +56.0  +44.5   +44.5  +44.5   +44.5 0 1 0"
        self.target_type    = "arb"
        self.actual_dec     = [0, 0, 0, 0]               # quella disegnata
        self.target_dec     = [None, None, None, None]   # quella da raggiungere
        self.current_dec    = [90, 90, 90, 90]           # quella letta nello status

        self.image = QtGui.QImage("small_bg.png")
        self.image2 = QtGui.QImage("small_fg.png")


        self.overlay = Image.open("small_arrow.png")
        ov = self.overlay.rotate(0).tobytes("raw","RGBA")
        self.qov = QtGui.QImage(ov, self.overlay.size[0], self.overlay.size[1], QtGui.QImage.Format_ARGB32)

        self.ui.comboBox.setEnabled(False)
        self.ui.arbitrary_dec.setEnabled(False)
        self.ui.button_move_arb.setEnabled(False)
        self.ui.button_move_src.setEnabled(False)
        self.ui.cb_sel_ramo.setEnabled(False)

        self.process_antenna_status = Thread(target=self.antenna_check)
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
            self.ant_pics[i].setGeometry(30+(160*i), 130, 140, 140)
            self.ant_pics[i].setPixmap(QtGui.QPixmap.fromImage(self.image))
            self.ant_pos += [QtGui.QLabel(self.ui.tab_dec)]
            self.ant_pos[i].setGeometry(30 + (160 * i), 80, 140, 40)
            self.ant_pos[i].setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
            self.ant_pos[i].setStyleSheet("background-color: rgb(255, 255, 255)")
            self.ant_pos[i].setFont(font)
            self.ant_pos[i].setText("44.5")

        self.initPics()
        self.ui.show()

        self.server_ip = "127.0.0.1"
        self.server_port = 7000
        self.server_polling = 5
        self.client = None
        self.client_buff_len = 1024

        # Connect up the buttons.
        self.ui.button_move_arb.clicked.connect(lambda: self.point_antenna('arb'))
        self.ui.button_move_src.clicked.connect(lambda: self.point_antenna('src'))
        clickable(self.ui.label_enabled).connect(lambda: self.action_enable())
        clickable(self.ui.label_connected).connect(lambda: self.action_connect())
        self.ui.cb_sel_ramo.currentIndexChanged.connect(lambda: self.select_ramo())

    def action_connect(self):
        if not self.connected:
            self.server_ip = self.ui.server_ip.text()
            self.server_port = int(self.ui.server_port.text())
            self.server_polling = int(self.ui.poll_time.text())
            self.ui.comment.setText("Connecting to server "+self.server_ip+":"+str(self.server_port))
            time.sleep(0.2)
            try:
                self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client.connect((self.server_ip, self.server_port))
                if not self.client==None:
                    self.ui.label_connected.setText("ONLINE")
                    self.ui.label_connected.setStyleSheet("background-color: rgb(0, 255, 0); color: rgb(0, 0, 0)")
                    if not self.process_antenna_status.isAlive():
                        self.process_antenna_status.start()
                    self.ui.comment.setText("Successfully Connected to the Antenna Server")
                    self.connected = True
            except:
                self.ui.comment.setText("ERROR: Unable to connect to server " + self.server_ip + ":" + str(self.server_port))
                self.connected = False
                self.ui.label_connected.setText("OFFLINE")
                self.ui.label_connected.setStyleSheet("background-color: rgb(122, 122, 122); color: rgb(255, 255, 255)")
        else:
            self.ui.label_connected.setText("OFFLINE")
            self.ui.label_connected.setStyleSheet("background-color: rgb(122, 122, 122); color: rgb(255, 255, 255)")
            self.connected = False
            self.ui.comment.setText("Disconnected from the Antenna Server" + self.server_ip + ":" + str(self.server_port))
            if self.client is not None:
                self.client = None


    def antenna_check(self):
        while True:
            if self.connected:
                self.status, self.current_dec = self.ask_status()
                if not self.current_dec == self.actual_dec:
                    self.antenna_signal.emit()
                time.sleep(self.server_polling-1)
            time.sleep(1)
            if self.stopThreads:
                break

    def ask_status(self):
        self.client.send("status")
        ans = self.client.recv(self.client_buff_len).split()
        pos = ans[2:6]
        status = ans[0]
        for i in xrange(len(pos)):
            pos[i] = float(pos[i])
        #print pos, status
        return status, pos

    def select_ramo(self):
        self.ramo = int(self.ui.cb_sel_ramo.currentIndex())

    def calc_src_dec(self):
        return float(self.ui.comboBox.currentText().split("-")[0])

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
        self.ui.comboBox.setEnabled(True)
        self.ui.button_move_src.setEnabled(True)
        self.ui.cb_sel_ramo.setEnabled(True)
        self.armed = True

    def point_antenna(self, dst='arb'):
        self.target_type = dst
        result = QtGui.QMessageBox.question(self,
                      "Confirm to Move...",
                      "Are you sure you want to Move the Antenna?",
                      QtGui.QMessageBox.Yes| QtGui.QMessageBox.No)
        if result == QtGui.QMessageBox.Yes:
            if dst == "arb":
                angle = float(self.ui.arbitrary_dec.text())
                print "Pointing Antenna to Declination ", str(angle)
                self.client.send("best "+str(angle))
            else:
                angle = float(self.calc_src_dec())
                print "Pointing Antenna to RadioSource ", str(angle)
                self.client.send("best "+str(angle))

            ans = self.client.recv(self.client_buff_len).split()[0]
            if ans=="MOVING":
                self.status="MOVING"
                self.ui.comment.setText("Antenna is Moving")
                for i in antenna_group[self.ramo]:
                    self.target_dec[i] = float("%3.1f"%angle)
                self.move_disarm()
            else:
                self.ui.comment.setText("ERROR")


    def updateDec(self):
        #print "Running SLOT"
        for i in xrange(4):

            self.ant_pos[i].setText("%3.1f"%(self.current_dec[i]))
            self.ant_pos[i].show()

            ov_actual = self.overlay.rotate((self.current_dec[i] - 44.5)).tobytes("raw", "RGBA")
            self.qov_actual = QtGui.QImage(ov_actual, self.overlay.size[0], self.overlay.size[1], QtGui.QImage.Format_ARGB32)

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
            datetime.datetime.utcfromtimestamp(time.time()),"Last update: %Y/%m/%d %H:%M:%S UTC"))


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



    def closeEvent(self,event):
        result = QtGui.QMessageBox.question(self,
                      "Confirm Exit...",
                      "Are you sure you want to exit ?",
                      QtGui.QMessageBox.Yes| QtGui.QMessageBox.No)
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

    sys.exit(app.exec_())
