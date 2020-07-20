import initExample  # just to work with sllurp of this repo
import sys
import logging as logger
import os
import pprint
import sys
import threading

from PyQt5.QtCore import Qt, QObject, pyqtSignal, QTimer, QRegExp, QPoint
from PyQt5.QtGui import (QIcon, QRegExpValidator, QStandardItem,
                         QStandardItemModel)
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QMenu,
                             QDialog, QDialogButtonBox, QTextEdit, QVBoxLayout,
                             QHBoxLayout, QGroupBox, QPushButton, QLabel,
                             QCheckBox, QLineEdit, QSlider, QTabWidget,
                             QPlainTextEdit, QMessageBox, QTreeView, QAction,
                             QComboBox)

from pyqtgraph import GraphicsLayoutWidget, mkPen
from pyqtgraph.parametertree import ParameterTree, Parameter
from signal import SIGINT, SIGTERM, signal

from sllurp.llrp import (C1G2Read, C1G2Write, LLRPReaderClient,
                         LLRPReaderConfig, LLRPReaderState)

logger.basicConfig(level=logger.INFO)

GUI_APP_TITLE = 'SLLURP GUI - RFID inventory control'
GUI_ICON_PATH = 'rfid.png'
GUI_DEFAULT_HOST = '169.254.1.1'
GUI_DEFAULT_PORT = 5084

DEFAULT_POWER_TABLE = [index for index in range(15, 25, 1)]
DEFAULT_ANTENNA_LIST = [1]
readerSettingsParams = [
    {
        'name': 'time',
        'title': 'Time (seconds to inventory)',
        'type': 'float', 'value': 10
    }, {
        'name': 'report_every_n_tags',
        'title': 'Report every N tags (issue a TagReport every N tags)',
        'type': 'int', 'value': 1
    }, {
        'name': 'tari',
        'title': 'Tari (Tari value (default 0=auto))',
        'type': 'int', 'value': 0
    }, {
        'name': 'session',
        'title': 'Session (Gen2 session (default 2))',
        'type': 'int', 'value': 2
    }, {
        'name': 'mode_identifier',
        'title': 'Mode identifier (ModeIdentifier value)',
        'type': 'int', 'value': 2
    }, {
        'name': 'tag_population',
        'title': 'Tag population (Tag Population value (default 4))',
        'type': 'int', 'value': 4
    },
]


class Gui(QObject):
    """graphical unit interface to open connection with a LLRP reader
    and inventory tags.
    """
    inventoryReportReceived = pyqtSignal(list)
    inventoryReportParsed = pyqtSignal(list)
    powerTableChanged = pyqtSignal(list)
    antennaIDListChanged = pyqtSignal(list)
    readerConfigChanged = pyqtSignal()

    def __init__(self):
        super(Gui, self).__init__()
        # variables
        self.knownTagList = []
        self.lock = threading.Lock()
        self.reader = None
        self.readerParam = Parameter.create(name='params',
                                            type='group',
                                            children=readerSettingsParams)
        self.txPowerChangedTimer = QTimer()
        self.txPowerChangedTimer.timeout.connect(self.readerConfigChangedEvent)
        self.txPowerChangedTimer.setSingleShot(True)
        # ui
        win = MainWindow()
        self.window = win

        win.setWindowTitle(GUI_APP_TITLE)
        win.setWindowIcon(QIcon(GUI_ICON_PATH))

        # connect UI events to handlers
        win.setExitHandler(self.exithandler)
        win.connectionButton.clicked.connect(self.connectionEvent)
        win.openAdvancedReaderConfigButton.clicked.connect(
            self.openAdvancedReaderConfigEvent
        )
        win.runInventoryButton.clicked.connect(self.runInventoryEvent)
        win.antennaComboBox.currentIndexChanged.connect(
            self.readerConfigChangedEvent
        )
        win.powerSlider.valueChanged.connect(
            self.delayreaderConfigChangedEvent
        )
        win.tagFilterMasklineEdit.editingFinished.connect(
            self.readerConfigChangedEvent
        )
        win.tagFilterMasklineEdit.editingFinished.connect(
            self.clearInventoryEvent
        )
        win.clearInventoryButton.clicked.connect(self.clearInventoryEvent)

        self.inventoryReportReceived.connect(self.parseInventoryReport)
        # connect event to handlers
        self.inventoryReportParsed.connect(self.updateInventoryReport)
        self.powerTableChanged.connect(self.updatePowerTableParameterUI)
        self.antennaIDListChanged.connect(self.updateAntennaParameterUI)
        self.readerConfigChanged.connect(self.readerConfigChangedEvent)

        self.resetWindowWidgets()

    def connect(self):
        """open connection with the reader through LLRP protocol
        """
        logger.info("connecting...")
        if not self.isConnected():
            r_param_fn = self.readerParam.param
            duration_time = r_param_fn("time").value()
            duration = None if duration_time == 0.0 else duration_time
            factory_args = dict(
                duration=duration,
                report_every_n_tags=r_param_fn("report_every_n_tags").value(),
                antennas=(DEFAULT_ANTENNA_LIST[0],),
                tx_power={
                    DEFAULT_ANTENNA_LIST[0]: 0
                },  # index of the power table to set the minimal power available
                tari=r_param_fn("tari").value(),
                session=r_param_fn("session").value(),
                # mode_identifier=args.mode_identifier,
                tag_population=r_param_fn("tag_population").value(),
                start_inventory=False,
                # disconnect_when_done=True,
                # tag_filter_mask=args.tag_filter_mask
                tag_content_selector={
                    "EnableROSpecID": False,
                    "EnableSpecIndex": False,
                    "EnableInventoryParameterSpecID": False,
                    "EnableAntennaID": False,
                    "EnableChannelIndex": False,
                    "EnablePeakRSSI": False,
                    "EnableFirstSeenTimestamp": False,
                    "EnableLastSeenTimestamp": False,
                    "EnableTagSeenCount": True,
                    "EnableAccessSpecID": True,
                },
            )
            host = self.host()
            config = LLRPReaderConfig(factory_args)
            self.reader = LLRPReaderClient(host, GUI_DEFAULT_PORT, config)
            self.reader.add_tag_report_callback(self.tag_report_cb)
            self.reader.add_state_callback(LLRPReaderState.STATE_CONNECTED,
                                           self.onConnection)
            try:
                self.reader.connect()
            except Exception:
                logger.warning("%s Destination Host Unreachable", host)
                self.window.showMessageDialog(
                    "Host Unreachable",
                    "%s Destination Host Unreachable" % host
                )
                self.window.connectionButton.setChecked(False)

    def disconnect(self):
        """close connection with the reader
        """
        if self.reader is not None:
            logger.info("disconnecting...")
            self.reader.join(0.1)
            logger.info("Exit detected! Stopping readers...")
            try:
                self.reader.disconnect()
                self.reader.join(0.1)
            except Exception:
                logger.exception("Error during disconnect. Ignoring...")
                pass
            self.resetWindowWidgets()

    def startInventory(self, duration=None, report_every_n_tags=None,
                       antennas=None, tx_power=None, tari=None, session=None,
                       mode_identifier=None, tag_population=None,
                       tag_filter_mask=None):
        """ask to the reader to start an inventory
        """
        if self.isConnected():
            logger.info("inventoring...")
            r_param_fn = self.readerParam.param
            if duration is None and r_param_fn("time").value() > 0.0:
                duration = r_param_fn("time").value()
            if report_every_n_tags is None:
                report_every_n_tags = \
                    r_param_fn("report_every_n_tags").value()
            if antennas is None:
                antennas = (self.currentAntennaId(),)
            if tx_power is None:
                tx_power = {
                    self.currentAntennaId(): self.currentPower()
                }
            if tari is None:
                tari = r_param_fn("tari").value()
            if session is None:
                session = r_param_fn("session").value()
            if mode_identifier is None:
                mode_identifier = \
                    r_param_fn("mode_identifier").value()
            if tag_population is None:
                tag_population = \
                    r_param_fn("tag_population").value()
            if tag_filter_mask is None:
                tag_filter_mask = self.currentTagFilterMask()

            factory_args = dict(
                duration=duration,
                report_every_n_tags=report_every_n_tags,
                antennas=antennas,
                tx_power=tx_power,
                tari=tari,
                session=session,
                mode_identifier=mode_identifier,
                tag_population=tag_population,
                tag_filter_mask=tag_filter_mask,
                start_inventory=False,
                tag_content_selector={
                    "EnableROSpecID": False,
                    "EnableSpecIndex": False,
                    "EnableInventoryParameterSpecID": False,
                    "EnableAntennaID": False,
                    "EnableChannelIndex": False,
                    "EnablePeakRSSI": False,
                    "EnableFirstSeenTimestamp": False,
                    "EnableLastSeenTimestamp": False,
                    "EnableTagSeenCount": True,
                    "EnableAccessSpecID": True,
                },
            )
            # update config
            self.reader.update_config(LLRPReaderConfig(factory_args))
            # update internal variable
            self.reader.llrp.parseCapabilities(self.reader.llrp.capabilities)
            # start inventory with update rospec which has been generated with
            # previous config
            self.reader.llrp.startInventory(force_regen_rospec=True)
            self.reader.join(0.1)

    def stopInventory(self):
        """ask to the reader to stop inventory
        """
        if self.isConnected():
            logger.info("stopping inventory...")
            self.reader.llrp.stopPolitely()
            self.reader.join(0.1)

    def tag_report_cb(self, reader, tags):
        """sllurp tag report callback, it emits a signal in order to perform
        the report parsing on the QT loop to avoid GUI freezing
        """
        self.lock.acquire()
        self.inventoryReportReceived.emit(tags)
        self.lock.release()

    def parseInventoryReport(self, tags):
        """Function called each time the reader reports seeing tags,
        It is run on the QT loop to avoid GUI freezing.
        """
        tagList = []  # use to display all tags on the window
        logger.info('%s tag_filter_mask=<%s>', str(tags),
                    str(self.reader.llrp.config.tag_filter_mask))
        epc = None
        # parsing each tag in the report
        for tag in tags:
            # get epc ID
            if "EPC-96" in tag:
                # sllurp return specific formatting when epc length = 96
                epc = tag["EPC-96"].decode("utf-8")
                strepc = tag["EPC-96"]
            elif "EPCData" in tag:
                epc = tag["EPCData"]["EPC"].decode("utf-8")
                strepc = tag["EPCData"]["EPC"]
            else:
                logger.warning("Unknown inventory report fomartting:%s",
                               str(tags))
            # append tag seen in the list
            tagList.append((epc, tag["TagSeenCount"]))
            # # parse data if it is an OpSpec report
            # if "OpSpecResult" in tag:
            #     # copy the binary data to the standard output stream
            #     data = tag["OpSpecResult"].get("ReadData")
            #     # ignore data if empty
            #     if data != b"" and data:
            #         # parse data
            #         values = []
            #         len_data = len(data)
            #         sList = []
            #         for i in range(0, len_data, 2):
            #             sList.append(int.from_bytes(data[i : i + 2], "big"))
            #         if len(sList) == 1:
            #             values = sList[0]
            #         else:
            #             values = sList
        self.inventoryReportParsed.emit(tagList)

    def exithandler(self):
        """called when the user closes the main window
        """
        self.disconnect()

    def connectionEvent(self):
        """called when the user clicks on the connection button
        """
        if self.window.connectionButton.isChecked():
            self.connect()
        else:
            self.disconnect()

    def openAdvancedReaderConfigEvent(self):
        """called when the user clicks on the button to open the reader
        advanced settings
        """
        dlg = QDialog()
        dlg.resize(800, 500)
        dlg.setWindowTitle("Reader Settings")
        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        layout = QVBoxLayout()
        paramTree = ParameterTree(showHeader=False)
        layout.addWidget(paramTree)
        textBox = QTextEdit()
        textBox.setReadOnly(True)
        textBox.value = lambda: str(textBox.toPlainText())
        textBox.setValue = textBox.setPlainText
        textBox.sigChanged = textBox.textChanged
        layout.addWidget(textBox)
        buttonBox = QDialogButtonBox(QBtn)
        buttonBox.accepted.connect(dlg.accept)
        buttonBox.rejected.connect(dlg.reject)
        layout.addWidget(buttonBox)
        dlg.setLayout(layout)
        paramTree.setParameters(self.readerParam, showTop=False)
        try:
            textBox.setText(pprint.pformat(self.reader.llrp.capabilities))
        except:
            pass
        dlg.exec_()
        self.readerConfigChangedEvent()

    def runInventoryEvent(self):
        """called when the user clicks on the button to start or stop
        an inventory
        """
        if self.isConnected():
            if self.window.runInventoryButton.isChecked():
                self.startInventory()
            else:
                self.stopInventory()
            self.updaterunInventoryButton()

    def clearInventoryEvent(self):
        """called when the user clicks on the button to clear the inventory
        tree view
        """
        win = self.window
        win.listModel.clear()
        self.knownTagList.clear()
        win.listModel.setHorizontalHeaderLabels(["EPC", "Tag Seen Count"])
        win.treeview.resizeColumnToContents(1)
        win.treeview.resizeColumnToContents(0)

    def delayreaderConfigChangedEvent(self):
        """used to delay the power applying when the user slides
        the cursor of the power slide bar
        """
        self.txPowerChangedTimer.stop()
        self.txPowerChangedTimer.start(500)  # ms

    def readerConfigChangedEvent(self):
        """called when the user changes any parameter of the reader through the
        GUI. Stop and re-start an inventory with new parameters if required.
        """
        if self.isConnected():
            self.powerTableChanged.emit(self.reader.llrp.tx_power_table)
            if self.reader.llrp.state == LLRPReaderState.STATE_INVENTORYING:
                self.stopInventory()
            if self.window.runInventoryButton.isChecked():
                self.startInventory()
            self.currentEpc = None

    def updateInventoryReport(self, tagList):
        """called to update inventory tree view
        """
        # update inventory widget
        if len(tagList) != 0:
            for tag in tagList:
                epc = tag[0]
                tagSeenCount = tag[1]
                if epc not in self.knownTagList:
                    self.knownTagList.append(epc)
                    epcItem = QStandardItem(epc)
                    epcItem.setEditable(False)
                    epcItem.setSelectable(False)
                    tagSeenCountItem = QStandardItem(str(tagSeenCount))
                    tagSeenCountItem.setEditable(False)
                    tagSeenCountItem.setSelectable(False)
                    self.window.listModel.appendRow(
                        [epcItem, tagSeenCountItem])
                    self.window.treeview.resizeColumnToContents(1)
                    self.window.treeview.resizeColumnToContents(0)
                else:
                    rowId = self.knownTagList.index(epc)
                    self.window.listModel.item(
                        rowId, 1).setText(str(tagSeenCount))

    def resetWindowWidgets(self):
        """set UI to default apparence state
        """
        win = self.window
        win.connectionButton.setText("Connect")
        win.connectionButton.setChecked(False)
        win.connectionStatusCheckbox.setChecked(False)
        win.connectionStatusCheckbox.setStyleSheet(
            "QCheckBox::indicator{border: 1px solid #999999; background-color: #FFFFFF;}")
        win.runInventoryButton.setText("Start inventory")
        win.runInventoryButton.setChecked(False)
        self.clearInventoryEvent()

    def updateconnectionButton(self):
        """update the state of the connection button
        """
        win = self.window
        if win.connectionButton.isChecked():
            win.connectionButton.setText("Disconnect")
            win.connectionStatusCheckbox.setChecked(True)
            win.connectionStatusCheckbox.setStyleSheet(
                "QCheckBox::indicator{border: 1px solid #999999; background-color: #00FF00;}")
        else:
            win.connectionButton.setText("Connect")
            win.connectionStatusCheckbox.setChecked(False)
            win.connectionStatusCheckbox.setStyleSheet(
                "QCheckBox::indicator{border: 1px solid #999999; background-color: #FFFFFF;}")

    def updaterunInventoryButton(self):
        """update the state of the run inventory button
        """
        inventory_bttn = self.window.runInventoryButton
        if inventory_bttn.isChecked():
            inventory_bttn.setText("Stop inventory")
        else:
            inventory_bttn.setText("Start inventory")

    def updatePowerTableParameterUI(self, powerTable):
        """update the state of the power label
        """
        win = self.window
        # update powerSlider position number according to the size of
        # tx_power_table of the reader
        win.powerSlider.setMaximum(len(powerTable) - 1)

        # update power parameter description
        index = win.powerSlider.value()
        power_dB = powerTable[index]
        if power_dB == 0:
            win.powerLabel.setText(
                "TX Power: maximum power of the reader")
        else:
            win.powerLabel.setText(
                "TX Power: " + str(power_dB) + " dB")

    def updateAntennaParameterUI(self, antennaIdList):
        """update the state of the antenna combobox
        """
        self.window.antennaComboBox.clear()
        for antennaId in antennaIdList:
            self.window.antennaComboBox.addItem(str(antennaId))

    def isConnected(self):
        """return connection status
        """
        return self.window.connectionStatusCheckbox.isChecked()

    def host(self):
        """return ip address set by the user
        """
        return str(self.window.hostLineEdit.text())

    def onConnection(self, reader, state):
        """called when connection with the reader is opened
        """
        self.updateconnectionButton()
        # parse reader capabilities
        self.powerTableChanged.emit(reader.llrp.tx_power_table)
        self.antennaIDListChanged.emit(list(range(1, reader.llrp.max_ant + 1)))

    def currentAntennaId(self):
        """return the current antenna ID set by the user
        """
        return self.window.antennaComboBox.currentIndex() + 1

    def currentPower(self):
        """return the current power set by the user
        """
        return self.window.powerSlider.value()

    def currentTagFilterMask(self):
        """return the current taf filter mask set by the user
        """
        txt_value = self.window.tagFilterMasklineEdit.text()
        if txt_value:
            list_value = txt_value.split(',')
        else:
            list_value = []
        return list_value


class MainWindow(QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.exithandler = None

        # workaround to fix showMaximized on Windows
        # https://stackoverflow.com/questions/27157312/qt-showmaximized-not-working-in-windows
        self.resize(800, 600)
        self.showMaximized()
        self.connectUIEventToControllerHandler()

        # Create a status bar
        status_bar = self.statusBar()
        # To be exported
        win_status_label = QLabel('')
        status_bar.addPermanentWidget(win_status_label)

        # create central widget/layout
        centralW = QWidget(self)
        centralL = QVBoxLayout(centralW)
        self.setCentralWidget(centralW)

        # create header widget/layout
        headerW = QWidget(parent=centralW)
        headerL = QHBoxLayout(headerW)
        centralL.addWidget(headerW)

        # create reader controls panel
        readerControlW = QGroupBox("Reader Controls", parent=headerW)
        readerControlL = QVBoxLayout(readerControlW)
        headerL.addWidget(readerControlW)

        # create connect/disconnect button
        self.connectionButton = QPushButton("Connect",
                                                      parent=readerControlW)
        self.connectionButton.setCheckable(True)
        readerControlL.addWidget(self.connectionButton)

        # create connection status widget
        connectionStatusW = QWidget(parent=readerControlW)
        connectionStatusL = QHBoxLayout(connectionStatusW)
        readerControlL.addWidget(connectionStatusW)
        connectionStatusL.addWidget(QLabel("Connection status",
                                           parent=connectionStatusW))
        self.connectionStatusCheckbox = QCheckBox(parent=connectionStatusW)
        connectionStatusL.addWidget(self.connectionStatusCheckbox)
        self.connectionStatusCheckbox.setDisabled(True)
        self.connectionStatusCheckbox.setChecked(False)

        # create open advanced reader settings
        self.openAdvancedReaderConfigButton = QPushButton(
            "Open advanced settings", parent=readerControlW)
        readerControlL.addWidget(self.openAdvancedReaderConfigButton)

        # create start/stop inventory button
        self.runInventoryButton = QPushButton("Start inventory",
                                              parent=readerControlW)
        self.runInventoryButton.setCheckable(True)
        readerControlL.addWidget(self.runInventoryButton)

        # create clear inventory button
        self.clearInventoryButton = QPushButton(
            "Clear inventory report", parent=readerControlW)
        readerControlL.addWidget(self.clearInventoryButton)

        # create reader settings button
        readerSettingsW = QGroupBox("Reader Settings", parent=readerControlW)
        readerSettingsL = QVBoxLayout(readerSettingsW)
        headerL.addWidget(readerSettingsW)

        # create ip parameter widget
        ipW = QWidget(parent=readerSettingsW)
        ipL = QHBoxLayout(ipW)
        readerSettingsL.addWidget(ipW)
        ipL.addWidget(QLabel("IP Address", parent=ipW))
        self.hostLineEdit = QLineEdit(GUI_DEFAULT_HOST, parent=ipW)
        ipL.addWidget(self.hostLineEdit)

        # create antenna parameter widget
        antW = QWidget(parent=readerSettingsW)
        antL = QHBoxLayout(antW)
        readerSettingsL.addWidget(antW)
        antL.addWidget(QLabel("Antenna", parent=antW))
        self.antennaComboBox = QComboBox(parent=antW)
        antL.addWidget(self.antennaComboBox)

        # create power parameter widget
        powerW = QWidget(parent=readerSettingsW)
        powerL = QHBoxLayout(powerW)
        readerSettingsL.addWidget(powerW)
        self.powerLabel = QLabel("TX Power (dB)", parent=powerW)
        powerL.addWidget(self.powerLabel)
        self.powerSlider = QSlider(Qt.Horizontal)
        powerL.addWidget(self.powerSlider)
        self.powerSlider.setTickPosition(QSlider.TicksBelow)
        self.powerSlider.setMinimum(0)
        self.powerSlider.setMaximum(1)
        self.powerSlider.setValue(0)
        self.powerSlider.setSingleStep(1)

        # create tag filter mask parameter widget
        tagFilterMaskW = QWidget(parent=readerSettingsW)
        tagFilterMaskL = QHBoxLayout(tagFilterMaskW)
        readerSettingsL.addWidget(tagFilterMaskW)
        tagFilterMaskL.addWidget(QLabel(
            "Tag Filter Mask", parent=tagFilterMaskW))
        self.tagFilterMasklineEdit = QLineEdit(parent=tagFilterMaskW)
        tagFilterMaskL.addWidget(self.tagFilterMasklineEdit)
        validator = QRegExpValidator(QRegExp("[0-9A-Fa-f,]+"))
        self.tagFilterMasklineEdit.setValidator(validator)

        # Create body/content tabbed widget
        tabbed_body_w = self.create_tabbed_body(centralW)
        centralL.addWidget(tabbed_body_w)

    def create_tabbed_body(self, parent_widget):
        # create bottom widget/layout
        tabbed_body_w = QGroupBox("Inventory", parent=parent_widget)
        inventoryL = QVBoxLayout(tabbed_body_w)

        tabs_w = QTabWidget(parent=tabbed_body_w)
        inventoryL.addWidget(tabs_w)

        # Add widget tabs
        inventory_tab = self.create_inventory_tags_tab(tabs_w)
        tabs_w.addTab(inventory_tab, 'Inventory tag reads')

        adv_graph_tab = self.create_advanced_graph_tab(tabs_w)
        tabs_w.addTab(adv_graph_tab, 'Advanced Graph')

        log_tab = self.create_logs_tab(tabs_w)
        tabs_w.addTab(log_tab, 'Operation Log')


        return tabbed_body_w

    def create_inventory_tags_tab(self, parent_widget):
        # Inventory tree view
        treeview = QTreeView(parent=parent_widget)

        # Operation list model
        self.listModel = QStandardItemModel(treeview)
        self.listModel.setHorizontalHeaderLabels(["EPC", "Tag Seen Count"])
        # treeview.resizeColumnToContents(3)
        # treeview.resizeColumnToContents(2)
        treeview.resizeColumnToContents(1)
        treeview.resizeColumnToContents(0)

        # Set model to view
        treeview.setModel(self.listModel)
        treeview.setContextMenuPolicy(Qt.CustomContextMenu)
        treeview.customContextMenuRequested.connect(self.openMenu)

        self.treeview = treeview
        return treeview

    def create_advanced_graph_tab(self, parent_widget):
        adv_graph_w = QWidget(parent=parent_widget)
        adv_graph_l = QHBoxLayout(adv_graph_w)

        # Create graph menu
        button_layout = QVBoxLayout()
        """
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
        """

        # Create graph main dipslay
        graph_w = GraphicsLayoutWidget()
        graph_w.setBackground('w')
        dataplot = graph_w.addPlot()

        adv_graph_l.addLayout(button_layout, 1)
        adv_graph_l.addWidget(graph_w, 5)

        return adv_graph_w

    def create_logs_tab(self, parent_widget):
        # Create a logs box
        logger_box_w = QPlainTextEdit()
        logger_box_w.setReadOnly(True)

        self.logger_box = logger_box_w
        return logger_box_w

    #def element(self, name):
    #    return self.centralUI.element(name)

    def setExitHandler(self, handler):
        self.exithandler = handler

    def kill(self):
        if self.exithandler is not None:
            self.exithandler()
        else:
            pass

    def closeMainWindowHandler(self, event):
        self.kill()
        event.accept()

    def keyboadInterruptHandler(self, signal, frame):
        self.close()

    def connectUIEventToControllerHandler(self):
        # to close window properly
        self.closeEvent = self.closeMainWindowHandler
        # Allow CTRL+C and/or SIGTERM to kill us (PyQt blocks it otherwise)
        signal(SIGINT, self.keyboadInterruptHandler)
        signal(SIGTERM, self.keyboadInterruptHandler)

    def showMessageDialog(self, title, message):
        msg = QMessageBox()
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()
        del msg

    def openMenu(self, pos):
        action = QAction(QIcon(""), "copy", self)
        action.triggered.connect(
            lambda: self.itemValueToClipboard(self.treeview.indexAt(pos)))
        menu = QMenu()
        menu.addAction(action)
        pt = QPoint(pos)
        menu.exec(self.treeview.mapToGlobal(pos))

    def itemValueToClipboard(self, index):
        QApplication.clipboard().setText(
            self.treeview.model().itemFromIndex(index).text())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = Gui()
    sys.exit(app.exec_())
