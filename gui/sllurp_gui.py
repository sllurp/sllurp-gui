#!/usr/bin/python3

'''
Created by Thijmen Ketel (github.com/thijmenketel) (WTFPL)
Sllurp gui for easy starting and stopping of inventory, this code is tested and
mostly used with an Impinj Speedway R420 RFID reader. Due to the extensions used (
RFPhaseAngle, DopplerFrequency and PeakRSSI) this GUI will only work with older 
readers in legacy mode (file -> llrp settings -> enable legacy mode).

This GUI uses an implementation of the Low Level Reader Protocol in python (see:
github.com/ransford/sllurp), however a private fork which removes the Twisted 
dependency is actually used here (see: github.com/fviard/sllurp/tree/develop_untwisted).

The GUI relies on PyQt5 and pyqtgraph and I would advise using Python 3.6 or higher, 
other versions are not guaranteed to work. Also, this software has only been tested on
a Linux machine (Kubuntu 18.04) so no guarantee that it will work on any other OS (but 
as it is just python it probably will).

TODO:
    - Clean up the code somewhat to make more readable
    - Remove calibration code (maybe)
    - Add Y range spinbox

Known issues:
    - Issues with higher modes than zero (1,2,3), these give weird results (might be 
        backend issue because different encoding: FM0 vs Miller) (phase ambiguity)
    - Rolling view wrecks when a new tag comes in later on (maybe fixed)

To be implemented:
    - Powersetting in settingsmenu (prob use percentage), needs linking to backend
    - Log field to display llrp logger info and other stuff (fix logger first)
    - Graceful handling of no connections
    - Fix phase diff function so it won't be unstable
    - Fix pen situation so its not limited to 8 colors
    - Add searchmode option
    - Add import data option to revisualise past data
    - Get frequency hoptable through llrp
    - Add tags per second per tag to table
'''

import copy
import json
import logging
import math
import pprint
import sys
import threading
import time
import datetime
import binascii

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QAction, QApplication, QCheckBox, QComboBox,
                             QDesktopWidget, QDialog, QDockWidget,
                             QErrorMessage, QGridLayout, QHBoxLayout,
                             QInputDialog, QLabel, QLineEdit, QMainWindow,
                             QMessageBox, QPlainTextEdit, QPushButton,
                             QSpinBox, QTableWidget, QTableWidgetItem,
                             QTextEdit, QToolTip, QVBoxLayout, QWidget)

from sllurp.llrp import LLRPReaderClient, LLRPReaderConfig, LLRPReaderState
from sllurp.log import get_logger, is_general_debug_enabled, set_general_debug
from sllurp.util import monotonic

from tag import Tag

# logging.getLogger().setLevel(logging.INFO)
# logger = get_logger(__name__)

tagdict = {}

start_time = 0
no_tags = 0

tagDataLock = threading.Lock()
timeLock = threading.Lock()


class SllurpGui(QMainWindow):

    def __init__(self):
        super().__init__()
        with open('gui/llrpsettings.json', 'r') as settingsfile:
            self.llrp_settings = json.load(settingsfile)
        settingsfile.close()
        self.rolling = False
        self.rollingsize = 1500  # Window size
        self.intervaltags = 0
        self.intervaltime = 0
        self.running = False
        self.calibrated = False
        self.__initUI()

    def __initUI(self):
        self.resize(1800, 900)
        self.center()
        self.setWindowTitle('SLLURP GUI - RFID inventory control')
        self.setWindowIcon(QIcon('rfid.png'))
        self.statusbar = self.statusBar()
        self.centralwidget = QWidget(self)
        self.setCentralWidget(self.centralwidget)

        exitAct = QAction('&Exit', self)
        exitAct.setShortcut('Ctrl+Q')
        exitAct.setStatusTip('Exit application')
        exitAct.triggered.connect(self.close)

        self.settingsMenu = QAction('&Llrp settings', self)
        self.settingsMenu.setStatusTip('Configure llrp settings')
        self.settingsMenu.triggered.connect(self.changeSettings)

        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&File')
        fileMenu.addAction(self.settingsMenu)
        fileMenu.addAction(exitAct)

        self.qbtn = QPushButton('Quit', self)
        self.qbtn.clicked.connect(self.close)
        self.qbtn.setToolTip('Quit application')
        self.qbtn.setStatusTip('Quit application')

        self.startbtn = QPushButton('Start inventory', self)
        self.startbtn.clicked.connect(self.startInventory)
        self.startbtn.setToolTip('Start inventory')
        self.startbtn.setStatusTip('Start inventory')

        self.stopbtn = QPushButton('Stop inventory', self)
        self.stopbtn.clicked.connect(self.stopInventory)
        self.stopbtn.setToolTip('Stop inventory')
        self.stopbtn.setStatusTip('Stop inventory')
        self.stopbtn.setEnabled(False)
        
        self.calibratebtn = QPushButton('Calibrate', self)
        self.calibratebtn.clicked.connect(self.calibrateReader)
        self.calibratebtn.setToolTip('(re-)Calibrate reader phase offsets')
        self.calibratebtn.setStatusTip('(re-)Calibrate reader phase offsets')

        self.calibratebtn.setEnabled(False)

        self.calibratedSwitch = {
            True: 'Reader calibrated',
            False: 'Reader not calibrated'
        }

        self.restorebtn = QPushButton('Restore view', self)
        self.restorebtn.clicked.connect(self.restoreView)
        self.restorebtn.setToolTip('Restore current graphs viewpoint')
        self.restorebtn.setStatusTip('Restore current graphs viewpoint')

        self.cleardatbtn = QPushButton('Clear tag data', self)
        self.cleardatbtn.clicked.connect(self.clearTagData)
        self.cleardatbtn.setToolTip('Clear gathered tagdata')
        self.cleardatbtn.setStatusTip('Clear gathered tagdata')

        self.exportbtn = QPushButton('Export tagdata to file', self)
        self.exportbtn.clicked.connect(self.exportData)
        self.exportbtn.setToolTip('Export tag data to csv file')
        self.exportbtn.setStatusTip('Export tag data to csv file')

        self.dataSelect = {
            0: 'Phase Rotation',
            1: 'Corrected Phase',
            2: 'Doppler Frequency',
            3: 'Peak RSSI',
            4: 'Phase Diff (beta)'
        }

        self.selectDataBox = QComboBox()
        self.selectDataBox.addItems(list(self.dataSelect.values()))
        self.selectDataBox.setCurrentIndex(0)
        self.selectDataBox.setStatusTip('Select data to be shown')
        self.selectDataBox.currentIndexChanged.connect(self.restoreView)
        selectlayout = QHBoxLayout()
        selectLabel = QLabel(self)
        selectLabel.setText('Data to be shown')
        selectlayout.addWidget(selectLabel)
        selectlayout.addWidget(self.selectDataBox)

        self.graphwidget = pg.GraphicsLayoutWidget()
        self.graphwidget.setBackground('w')
        self.dataplot = self.graphwidget.addPlot()
        self.curves = {}

        self.plotPens = {   #XXX: Limited colours, needs more elegance, SOLVE!
            0: pg.mkPen('r'),
            1: pg.mkPen('b'),
            2: pg.mkPen('g'),
            3: pg.mkPen('y'),
            4: pg.mkPen('c'),
            5: pg.mkPen('m'),
            6: pg.mkPen('w'),
            7: pg.mkPen('k')
        }

        self.gridcheckx = QCheckBox('Enable X-Grid')
        self.gridcheckx.setStatusTip('Enable/disable X-Grid')
        self.gridcheckx.stateChanged.connect(self.gridx)
        self.gridcheckx.setChecked(True)
        self.gridchecky = QCheckBox('Enable Y-Grid')
        self.gridchecky.setStatusTip('Enable/disable Y-Grid')
        self.gridchecky.stateChanged.connect(self.gridy)
        self.gridchecky.setChecked(True)

        self.rollgraph = QCheckBox('Enable rolling graph', self)
        self.rollgraph.setChecked(self.rolling)
        self.rollgraph.stateChanged.connect(self.enableRollGraph)

        self.tagsSpeedBox = QLabel('Inventory not active')
        self.statusbar.addPermanentWidget(self.tagsSpeedBox)

        self.tagTable = QTableWidget(0, 5, self)
        self.tagTable.setHorizontalHeaderLabels(
            ['EPC-96 of tag', 'Count', 'RSSI', 'Part (%)', 'Channel'])

        self.loggerBox = QPlainTextEdit()
        self.loggerBox.setReadOnly(True)

        buttonlayout = QVBoxLayout()
        buttonlayout.addWidget(self.startbtn)
        buttonlayout.addWidget(self.stopbtn)
        buttonlayout.addWidget(self.calibratebtn)
        buttonlayout.addLayout(selectlayout)
        buttonlayout.addWidget(self.gridcheckx)
        buttonlayout.addWidget(self.gridchecky)
        buttonlayout.addWidget(self.rollgraph)
        buttonlayout.addWidget(self.restorebtn)
        buttonlayout.addWidget(self.cleardatbtn)
        buttonlayout.addWidget(self.exportbtn)
        buttonlayout.addStretch()
        buttonlayout.addWidget(self.qbtn)

        datalayout = QVBoxLayout()
        datalayout.addWidget(self.tagTable)
        datalayout.addWidget(self.loggerBox)

        mainlayout = QHBoxLayout()
        mainlayout.addLayout(buttonlayout, 1)
        mainlayout.addWidget(self.graphwidget,5)
        mainlayout.addLayout(datalayout, 2)

        # adding stuff: addWidget/addLayout(thing, startrow, startcolumn, rowspan, colspan)
        # mainlayout = QGridLayout()
        # mainlayout.addWidget(self.startbtn, 0, 0)
        # mainlayout.addWidget(self.stopbtn, 1, 0)
        # mainlayout.addWidget(self.calibratebtn, 2, 0)
        # mainlayout.addWidget(self.gridcheckx, 4, 0)
        # mainlayout.addWidget(self.gridchecky, 5, 0)
        # mainlayout.addWidget(self.rollgraph, 6, 0)
        # mainlayout.addLayout(selectlayout, 3, 0)
        # mainlayout.addWidget(self.restorebtn, 7, 0)
        # mainlayout.addWidget(self.cleardatbtn, 8, 0)
        # mainlayout.addWidget(self.exportbtn, 9, 0)
        # mainlayout.addWidget(self.qbtn, 11, 0)
        # mainlayout.addWidget(self.graphwidget, 0, 1, 12, 9)
        # mainlayout.addWidget(self.tagTable, 0, 10, 7, 3)
        # mainlayout.addWidget(self.loggerTextBox, 7, 10, 2, 3)

        self.graphtimer = QTimer()
        self.graphtimer.timeout.connect(self.updateGraphs)
        self.graphtimer.setInterval(25)

        self.tabletimer = QTimer()
        self.tabletimer.timeout.connect(self.updateTable)
        self.tabletimer.setInterval(100)

        self.tagstimer = QTimer()
        self.tagstimer.timeout.connect(self.updateTagsWidget)
        self.tagstimer.setInterval(500)

        self.calibratetimer = QTimer()
        self.calibratetimer.timeout.connect(self.calibrateCheck)
        self.calibratetimer.setInterval(100)

        self.createGraphs()
        self.centralwidget.setLayout(mainlayout)
        self.show()
        self.changeSettings()

    def center(self):
        frame = self.frameGeometry()
        center = QDesktopWidget().availableGeometry().center()
        frame.moveCenter(center)
        self.move(frame.topLeft())

    def changeSettings(self):

        def onClick():
            self.llrp_settings['IP'] = IPbox.text()
            self.llrp_settings['Legacymode'] = legacymode.isChecked()
            self.llrp_settings['ReaderMode'] = selectMode.currentIndex()
            self.llrp_settings['TXPower'] = powerBox.value()
            self.llrp_settings['TagPop'] = popBox.value()
            self.llrp_settings['TagFilter'] = tagFilterEnable.isChecked()
            self.llrp_settings['TagMask'] = tagMask.text()
            self.legacyMode()
            settings.close()

        settings = QDialog(self)
        settings.setFixedSize(350, 270)
        settings.setWindowTitle('Configure llrp settings')

        IPLabel = QLabel(settings)
        IPLabel.setText('Set reader IP')
        IPbox = QLineEdit(settings)
        IPbox.setText(self.llrp_settings['IP'])
        IPlayout = QHBoxLayout()
        IPlayout.addWidget(IPLabel)
        IPlayout.addStretch()
        IPlayout.addWidget(IPbox)

        powerLabel = QLabel(settings)
        powerLabel.setText('Set Tx power (%)')
        powerBox = QSpinBox()
        powerBox.setRange(1, 100)
        powerBox.setSingleStep(5)
        powerBox.setValue(self.llrp_settings['TXPower'])
        powerLayout = QHBoxLayout()
        powerLayout.addWidget(powerLabel)
        powerLayout.addStretch()
        powerLayout.addWidget(powerBox)

        popLabel = QLabel(settings)
        popLabel.setText('Set tag population')
        popBox = QSpinBox()
        popBox.setRange(2, 1024)
        popBox.setSingleStep(2)
        popBox.setValue(self.llrp_settings['TagPop'])
        tagpopLayout = QHBoxLayout()
        tagpopLayout.addWidget(popLabel)
        tagpopLayout.addStretch()
        tagpopLayout.addWidget(popBox)

        legacymode = QCheckBox('Enable Legacy mode', settings)
        legacymode.setChecked(self.llrp_settings['Legacymode'])
        selectMode = QComboBox()
        selectMode.addItems(['0 - Max Throughput', '1 - Hybrid',
                             '2 - M=4', '3 - M=8'])
        selectMode.setCurrentIndex(self.llrp_settings['ReaderMode'])
        selectMode.setToolTip('Select ReaderMode to be used')
        selectlayout = QHBoxLayout()
        selectLabel = QLabel(settings)
        selectLabel.setText('Select ReaderMode')
        selectlayout.addWidget(selectLabel)
        selectlayout.addWidget(selectMode)

        tagFilterEnable = QCheckBox('Enable tag filter', settings)
        tagFilterEnable.setChecked(self.llrp_settings['TagFilter'])
        tagMask = QLineEdit(settings)
        tagMask.setText(self.llrp_settings['TagMask'])
        tagFilterLayout = QHBoxLayout()
        tagFilterLayout.addWidget(tagFilterEnable)
        tagFilterLayout.addStretch()
        tagFilterLayout.addWidget(tagMask)

        applybtn = QPushButton('Accept', settings)
        applybtn.clicked.connect(onClick)

        grid = QGridLayout()

        grid.addLayout(IPlayout, 1, 0, 1, 3)
        grid.addLayout(selectlayout, 2, 0, 2, 3)
        grid.addLayout(powerLayout, 3, 0, 3, 3)
        grid.addLayout(tagpopLayout, 4, 0, 4, 3)
        grid.addLayout(tagFilterLayout, 5, 0, 5, 3)

        grid.addWidget(legacymode, 8, 0)
        grid.addWidget(applybtn, 9, 2)

        settings.setLayout(grid)
        settings.show()
        settings.exec_()

    def legacyMode(self):
        if self.llrp_settings['Legacymode']:
            self.selectDataBox.setCurrentIndex(3)
            self.selectDataBox.setEnabled(False)
        else:
            self.selectDataBox.setEnabled(True)

    def createGraphs(self):
        self.curves.clear()
        self.dataplot.setLabel('bottom', text='Time', units='ms')
        self.dataplot.addLegend()
        self.restoreView()

    def restoreView(self):
        self.dataplot.setLabel('left', text=self.dataSelect.get(
            self.selectDataBox.currentIndex()))
        self.graphwidget.setStatusTip(self.dataSelect.get(
            self.selectDataBox.currentIndex()) + ' graph representation')
        rangeswitch = {
            0: (0, math.pi*2),
            1: (0, math.pi*2),
            2: (-2000, 2000),
            3: (-90, -10),
            4: (-4, 4)
        }
        r = rangeswitch.get(self.selectDataBox.currentIndex())
        self.dataplot.setYRange(r[0], r[1])
        if self.rolling:
            self.dataplot.setXRange(0, self.rollingsize)
        else:
            self.dataplot.enableAutoRange(
                axis=self.dataplot.getViewBox().XAxis)
        if not self.running:
            self.updateGraphs()

    def calibrateReader(self):
        self.offsets = {}
        self.hoptable = {}
        self.tagsSpeedBox.setText('Calibrating...please wait')
        self.log('Started calibration')
        self.startbtn.setEnabled(False)
        self.settingsMenu.setEnabled(False)
        self.cleardatbtn.setEnabled(False)
        self.exportbtn.setEnabled(False)
        self.calibratebtn.setEnabled(False)
        self.calibrator = self.LlrpThread(self.llrp_settings, self.log,
            calibrate=True, offsets=self.offsets, hoptable=self.hoptable)
        self.calibrator.start()
        self.calibratetimer.start()

    def calibrateCheck(self):
        self.tagsSpeedBox.setText('Calibrating...please wait: ' 
            + str(len(self.offsets)) + '/50')
        if not self.calibrator.is_alive():
            self.calibratetimer.stop()
            self.startbtn.setEnabled(True)
            self.settingsMenu.setEnabled(True)
            self.cleardatbtn.setEnabled(True)
            self.exportbtn.setEnabled(True)
            self.calibratebtn.setEnabled(True)
            self.calibrated = True
            self.infoDialog('Reader finished calibration')
            self.log('Calibration complete')
            self.tagsSpeedBox.setText('Inventory not active - ' 
                + self.calibratedSwitch.get(self.calibrated))

    def startInventory(self):
        global no_tags
        self.startbtn.setEnabled(False)
        self.settingsMenu.setEnabled(False)
        self.cleardatbtn.setEnabled(False)
        self.exportbtn.setEnabled(False)
        timeLock.acquire()
        no_tags = 0
        timeLock.release()
        self.reader = self.LlrpThread(self.llrp_settings, self.log)
        self.reader.start()
        self.graphtimer.start()
        self.tagstimer.start()
        self.tabletimer.start()
        self.log('Inventory started')
        self.stopbtn.setEnabled(True)
        self.running = True

    def stopInventory(self):
        global no_tags
        self.stopbtn.setEnabled(False)
        self.graphtimer.stop()
        self.tagstimer.stop()
        self.tabletimer.stop()
        self.reader.stopInventory()
        self.startbtn.setEnabled(True)
        self.settingsMenu.setEnabled(True)
        self.cleardatbtn.setEnabled(True)
        self.exportbtn.setEnabled(True)
        self.running = False
        self.log('Inventory stopped')
        self.tagsSpeedBox.setText('Inventory not active - '
            + self.calibratedSwitch.get(self.calibrated))
        for name, tag in tagdict.items():
            self.log(str(name) + ' : ' + str(tag.getSize())
                  + '(' + str((tag.getSize()/no_tags)*100) + '%)')

    def updateTagsWidget(self):
        global start_time, no_tags
        timeLock.acquire()
        if start_time:
            currtime = monotonic()
            splittags = no_tags - self.intervaltags
            splittime = currtime - self.intervaltime
            self.tagsSpeedBox.setText('Reader mode: '
                                      + str(self.llrp_settings['ReaderMode'])
                                      + ' - Throughput: ' +
                                      str(int(splittags/splittime))
                                      + ' Tags/s')
            self.intervaltime = currtime
            self.intervaltags = no_tags
        else:
            print('Too soon!')
        timeLock.release()

    def updateTable(self):
        global tagdict
        tabledata = []
        tagDataLock.acquire()
        for name, tag in tagdict.items():
            tabledata.append((name, tag.getSize(),
                              tag.getRSSI()[-1], tag.getChannel()[-1]))
        tagDataLock.release()
        temptags = 1
        # might still cause divide by zero exception
        temptags = sum([tag[1] for tag in tabledata])
        if self.tagTable.rowCount() < len(tabledata):
            self.tagTable.setRowCount(self.tagTable.rowCount() + 1)
        tabledata.sort(key=lambda x: x[1], reverse=True)
        self.tagTable.clear()
        self.tagTable.setHorizontalHeaderLabels(
            ['EPC-96 of tag', 'Count', 'RSSI', 'Part (%)', 'Channel'])
        for row in range(len(tabledata)):
            self.tagTable.setItem(
                row, 0, QTableWidgetItem(str(tabledata[row][0])))
            self.tagTable.setItem(row, 1, QTableWidgetItem(
                str(tabledata[row][1])))
            self.tagTable.setItem(row, 2, QTableWidgetItem(
                str(tabledata[row][2])))
            part = round((tabledata[row][1]/temptags)*100, 2)
            self.tagTable.setItem(
                row, 3, QTableWidgetItem(str(part).join(' %')))
            self.tagTable.setItem(row, 4, QTableWidgetItem(
                str(tabledata[row][3])))
        self.tagTable.resizeColumnsToContents()

    def updateGraphs(self):
        global tagdict
        datasetindex = self.selectDataBox.currentIndex()
        tagDataLock.acquire()
        for name, tag in tagdict.items():
            if name not in self.curves:
                self.curves[name] = self.dataplot.plot(
                    pen=self.plotPens.get(len(self.curves)), name=name)
            if not self.llrp_settings['Legacymode']:
                if self.calibrated:
                    tag.removeShiftCalibrated(self.offsets, self.hoptable)
                else:
                    tag.removeShift(self.llrp_settings['ReaderMode'] > 0)
            if self.rolling:
                # subsamplelist = tag.getData(datasetindex)[-self.rollingsize:]
                subtimelist = tag.getTime()[-self.rollingsize:]
                self.dataplot.setXRange(subtimelist[0], subtimelist[-1])
                # self.curves[name].setData(y=subsamplelist, x=subtimelist)
            # else:
            self.curves[name].setData(y=tag.getData(
                datasetindex), x=tag.getTime())
        tagDataLock.release()

    def clearTagData(self):
        if len(tagdict):
            tagdict.clear()
            Tag.start = None
            self.dataplot.clear()
            self.curves.clear()
            self.dataplot.legend.scene().removeItem(self.dataplot.legend)
            self.dataplot.addLegend()
            self.updateTable()
            self.tagTable.setRowCount(0)
            # self.infoDialog('Tag data cleared')
            self.log('Tag data cleared')
        else:
            self.errorDialog('No data')

    def exportData(self):
        if len(tagdict):
            filename, accepted = \
                QInputDialog.getText(self, 'Export', 'Filename: ',
                                     QLineEdit.Normal, 'exportdata')
            if accepted and filename is not '':
                with open(filename + '.csv', 'w') as logfile:
                    if self.llrp_settings['Legacymode']:
                        logfile.write('name,time,rssi,channel\n')
                        for name, tag in tagdict.items():
                            for t, r, c in zip(tag.getTime(), tag.getRSSI(), 
                                            tag.getChannel()):
                                logfile.write('%s,%f,%u,%u\n' %
                                              (name, t, r, c))
                    else:
                        logfile.write(
                            'name,time,phase,correct,doppler,rssi,channel\n')
                        for name, tag in tagdict.items():
                            for t, p, c, d, r, f in zip(tag.getTime(), tag.getPhase(), 
                                                    tag.getCorrect(), tag.getDoppler(), 
                                                    tag.getRSSI(), tag.getChannel()):
                                logfile.write('%s,%f,%f,%f,%u,%u,%u\n'
                                              % (name, t, p, c, d, r, f))
                logfile.close()
                self.infoDialog('Exported to: %s.csv' % filename)
                self.log('Exported to: %s.csv' % filename)
        else:
            self.errorDialog('No data to export')

    def log(self, text):
        timenow = '{0:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())
        self.loggerBox.appendPlainText(timenow + ': ' + text)

    def gridx(self, state):
        if state == Qt.Checked:
            self.dataplot.showGrid(x=True)
        else:
            self.dataplot.showGrid(x=False)

    def gridy(self, state):
        if state == Qt.Checked:
            self.dataplot.showGrid(y=True)
        else:
            self.dataplot.showGrid(y=False)

    def enableRollGraph(self, state):
        self.restoreView()
        if state == Qt.Checked:
            self.rolling = True
            self.dataplot.disableAutoRange()
        else:
            self.rolling = False
            self.dataplot.enableAutoRange(
                axis=self.dataplot.getViewBox().XAxis)
        self.updateGraphs()

    def errorDialog(self, errortext):
        QMessageBox.critical(self, 'Error',
                             'Error: ' + errortext, QMessageBox.Close)

    def infoDialog(self, infotext):
        QMessageBox.information(self, 'Info',
                                infotext, QMessageBox.Close)

    def closeEvent(self, event):
        if self.running:
            self.errorDialog('Inventory still running')
            event.ignore()
        else:
            close = QMessageBox.question(self, 'Sllurp',
                                         'Quit app?', QMessageBox.Yes | QMessageBox.No,
                                         QMessageBox.Yes)

            if close == QMessageBox.Yes:
                with open('gui/llrpsettings.json', 'w') as settingsfile:
                    json.dump(self.llrp_settings, settingsfile, indent=4)
                settingsfile.close()
                event.accept()
            else:
                event.ignore()

    class LlrpThread(threading.Thread):

        def __init__(self, settings, logger, calibrate=False, 
            offsets=None, hoptable=None):
            threading.Thread.__init__(self)
            self.settings = settings
            self.logger = logger    # fix errors here
            self.calibrate = calibrate
            self.offsets = offsets
            self.hoptable = hoptable

        def run(self):
            factory_args = dict(
                session=0,
                mode_identifier=self.settings['ReaderMode'],
                tag_population=self.settings['TagPop'],
                start_inventory=True,
                tag_content_selector={
                    'EnableROSpecID': False,
                    'EnableSpecIndex': False,
                    'EnableInventoryParameterSpecID': False,
                    'EnableAntennaID': False,
                    'EnableChannelIndex': True,
                    'EnablePeakRSSI': True,
                    'EnableFirstSeenTimestamp': True,
                    'EnableLastSeenTimestamp': True,
                    'EnableTagSeenCount': True,
                    'EnableAccessSpecID': False,
                    'C1G2EPCMemorySelector': {
                        'EnableCRC': False,
                        'EnablePCBits': False,
                    }
                },
                tag_filter_mask=self.settings['TagMask'] if self.settings['TagFilter'] else None,
                impinj_search_mode=self.settings['ImpinjSearchMode'],
            )

            if not self.settings['Legacymode']:
                factory_args['impinj_tag_content_selector'] = {
                    'EnableRFPhaseAngle': True,
                    'EnablePeakRSSI': True,
                    'EnableRFDopplerFrequency': True
                }

            config = LLRPReaderConfig(factory_args)
            self.reader = LLRPReaderClient(self.settings['IP'], 5084, config)
            self.reader.add_disconnected_callback(self.finish_cb)
            if self.calibrate:
                self.reader.add_tag_report_callback(self.calibrate_cb)    
                self.caltag = None    
                self.lastphase = 0
                self.lastchannel = 0
            else:
                self.reader.add_tag_report_callback(self.tag_callback)
            self.reader.add_state_callback(LLRPReaderState.STATE_INVENTORYING,
                                           self.inventory_start_cb)

            try:
                self.reader.connect()
            except Exception:
                self.reader.disconnect()

            while self.reader.is_alive():
                self.reader.join(1)

        def tag_callback(self, reader, tags):
            global tagdict, no_tags
            if len(tags):
                # print('saw tag(s): %s', pprint.pformat(tags))
                timeLock.acquire()
                no_tags += tags[0]['TagSeenCount']
                timeLock.release()
                tagDataLock.acquire()
                if tags[0]['EPC-96'] in tagdict:
                    tagdict[tags[0]['EPC-96']
                            ].addDataSwitch(self.settings['Legacymode'], tags[0])
                else:
                    tagdict[tags[0]['EPC-96']
                            ] = Tag(self.settings['Legacymode'], tags[0])
                tagDataLock.release()
            else:
                print('no tags seen')
                return
        
        def calibrate_cb(self, reader, tags):
            '''
            This needs testing to determine if last phase is more 
            accurate or just use delta from last channel
            '''
            if len(tags):
                if self.caltag is None:
                    self.caltag = tags[0]['EPC-96']
                    self.offsets[tags[0]['ChannelIndex']] = \
                        tags[0]['ImpinjPhase']*((math.pi*2)/4096)
                    self.lastchannel = tags[0]['ChannelIndex']
                    self.lastphase = tags[0]['ImpinjPhase']*((math.pi*2)/4096)
                elif tags[0]['EPC-96'] == self.caltag:
                    if tags[0]['ChannelIndex'] != self.lastchannel:
                        if tags[0]['ChannelIndex'] not in self.offsets:
                            self.offsets[tags[0]['ChannelIndex']] = \
                                (tags[0]['ImpinjPhase']*((math.pi*2)/4096))
                            self.lastchannel = tags[0]['ChannelIndex']
                        elif self.calibrate: 
                            self.stopInventory()
                            self.calibrate = False

        def stopInventory(self):
            if self.reader.is_alive():
                print('Disconnecting reader')
                self.reader.disconnect()

        def inventory_start_cb(self, reader, state):
            global start_time
            timeLock.acquire()
            start_time = monotonic()
            print('started at: ' + str(start_time))
            timeLock.release()
            if self.hoptable is not None:
                temp = copy.deepcopy(self.reader.llrp.hoptable)
                for key, value in temp.items():
                    if 'Frequency' in key:
                        self.hoptable[int(key[len('Frequency'):])] = value
                for channel, freq in self.hoptable.items():
                    print(str(channel) + ' - ' + str(freq))

        def finish_cb(self, reader):
            global no_tags, start_time
            runtime = monotonic() - start_time
            print('total # of tags seen: ' + str(no_tags)
                  + ' - ' + str(int(no_tags/runtime)) + ' tags/second')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SllurpGui()
    sys.exit(app.exec_())
