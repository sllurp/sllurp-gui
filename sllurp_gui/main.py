#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" GUI Frontend for SLLURP to control LLRP RFID Readers

This GUI uses an implementation of the Low Level Reader Protocol controller
in python (see: github.com/ransford/sllurp), however, for the moment, a
particular rework branch (fviard-develop-v2) has to be used here (see:
github.com/fviard/sllurp/tree/fviard-develop-v2).

The GUI relies on PyQt5, pyqtgraph and using Python 3.6 or higher is
recommended. It has not been tested on any other OS than Linux.


Important warning:
This project is in a Work In Progress state, and a few bugs and unfinished
features are to be expected.


Copyright (C) 2020 Contributors


Authors:
    - Florent Viard (florent@sodria.com)
    - Papapel
    - Thijmen Ketel

Website:
    https://github.com/fviard/sllurp-gui

License:
    GPL Version 3

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.
This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.

"""

import datetime
import logging as logger
import math
import os
import pprint
import sys
import threading

from collections import OrderedDict

from PyQt5.QtCore import (Qt, QObject, pyqtSignal, QTimer, QRegExp, QPoint,
                          QAbstractTableModel)
from PyQt5.QtGui import (QIcon, QRegExpValidator, QStandardItem,
                         QStandardItemModel)
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QMenu,
                             QDialog, QDialogButtonBox, QTextEdit, QVBoxLayout,
                             QHBoxLayout, QGroupBox, QPushButton, QLabel,
                             QCheckBox, QLineEdit, QSlider, QTabWidget,
                             QPlainTextEdit, QMessageBox, QTableView,
                             QAction, QComboBox)

from pyqtgraph import GraphicsLayoutWidget, mkPen
from pyqtgraph.parametertree import ParameterTree, Parameter
from signal import SIGINT, SIGTERM, signal
from time import monotonic

try:
    from sllurp.version import __version__ as sllurp_version
except ImportError:
    print("Please install the `sllurp` package")
    raise
from sllurp.llrp import (C1G2Read, C1G2Write, LLRPReaderClient,
                         LLRPReaderConfig, LLRPReaderState, llrp_data2xml)

logger.basicConfig(level=logger.INFO)

GUI_APP_TITLE = 'SLLURP GUI - RFID inventory control'
GUI_ICON_PATH = 'rfid.png'
GUI_DEFAULT_HOST = '169.254.1.1'
GUI_DEFAULT_PORT = 5084

TAGS_TABLE_HEADERS = ["EPC", "Antenna", "Best\nRSSI", "First\nChannel",
                      "Tag Seen\nCount", "Last\nRSSI", "Last\nChannel"]
TAGS_TABLE_COLUMNS = ['epc', 'antenna_id', 'rssi', 'channel_index',
                      'seen_count', 'last_rssi', 'last_channel_index']

DEFAULT_POWER_TABLE = [index for index in range(15, 25, 1)]
DEFAULT_ANTENNA_LIST = [1]

READER_MODES_TITLES = OrderedDict(sorted({
    '0 - (Impinj: Max Throughput)': 0,
    '1 - (Impinj: Hybrid M=2)': 1,
    '2 - (Impinj: Dense Reader M=4)': 2,
    '3 - (Impinj: Dense Reader M=8)': 3,
    '4 - (Impinj: Max Miller M=4)': 4,
    '5 - (Impinj: Dense Reader 2 M=4)': 5,
    '6': 6,
    '7': 7,
    '8': 8,
    '9': 9,
    '10': 10,
    '11': 11,
    '12': 12,
    '13': 13,
    '14': 14,
    '15': 15,
    '16': 16,
    '17': 17,
    '18': 18,
    '19': 19,
    '20': 20,
    '1000 - (Impinj: Autoset)': 1000,
    '1002 - (Impinj: Autoset Static)': 1002,
    '1003 - (Impinj: Autoset Static Fast)': 1003,
    '1004 - (Impinj: Autoset Static DRM)': 1004,
    '1005': 1005,
}.items(), key=lambda x: x[1]))

IMPINJ_SEARCH_MODE_TITLES = OrderedDict(sorted({
    '0 - Reader Selected (default)': 0,
    '1 - Single Target Inventory': 1,
    '2 - Dual Target Inventory': 2,
    '3 - Single Target Inventory with Suppression': 3,
    '5 - Single Target Reset Inventory': 5,
    '6 - Dual Target Inventory with Reset': 6,
}.items(), key=lambda x: x[1]))

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
        'title': 'Tari (Tari value; default 0=auto)',
        'type': 'int', 'value': 0
    }, {
        'name': 'session',
        'title': 'Session (Gen2 session; default 2)',
        'type': 'list', 'values': [0, 1, 2, 3],
        'value': 2
    }, {
        'name': 'mode_identifier',
        'title': 'Mode identifier (ModeIdentifier value)',
        'type': 'list', 'values': READER_MODES_TITLES,
        'value': 2
    }, {
        'name': 'tag_population',
        'title': 'Tag population (Tag Population value; default 4)',
        'type': 'int', 'value': 4
    }, {
        'name': 'frequencies',
        'title': 'Frequencies to use (Comma-separated; 0=all; default 1)',
        'type': 'str', 'value': '1'
    }, {
        'name': 'impinj_extensions',
        'title': 'Impinj readers extensions',
        'type': 'group',
        'expanded': True,
        'children': [
            {
                'name': 'enabled',
                'title': 'Enable Impinj extensions',
                'type': 'bool',
                'value': False
            }, {
                'name': 'search_mode',
                'title': 'Impinj search mode',
                'type': 'list',
                'values': IMPINJ_SEARCH_MODE_TITLES,
                'value': 0
            }
        ]
    }, {
        'name': 'zebra_extensions',
        'title': 'Zebra readers extensions',
        'type': 'group',
        'expanded': True,
        'children': [
            {
                'name': 'enabled',
                'title': 'Enable Zebra extensions',
                'type': 'bool',
                'value': False
            }
        ]

    }
]


class TagsTableModel(QAbstractTableModel):

    def __init__(self, data):
        super(TagsTableModel, self).__init__()
        self._data = data
        self._data_vals = list(data.values())

    def update(self, data):
        self._data = data
        self._data_vals = list(data.values())
        #self.dataChanged.emit(self.createIndex(0, 0),
        #                      self.createIndex(self.rowCount(),
        #                                       self.columnCount()))
        self.layoutChanged.emit()

    def data(self, index, role):
        if role == Qt.DisplayRole:
            # See below for the nested-list data structure.
            # .row() indexes into the outer list,
            # .column() indexes into the sub-list
            return self._data_vals\
                [index.row()].get(TAGS_TABLE_COLUMNS[index.column()], '')
        elif role == Qt.TextAlignmentRole:
            return Qt.AlignVCenter | Qt.AlignRight

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return TAGS_TABLE_HEADERS[section]

            if orientation == Qt.Vertical:
                ## Alternative to have line number as row headers
                #return str(section)
                ## No row headers
                return ''

    def rowCount(self, index):
        # The length of the outer list.
        return len(self._data)

    def columnCount(self, index):
        # The following takes the first sub-list, and returns
        # the length (only works if all rows are an equal length)
        #if not self._data:
        #    return 0
        return len(TAGS_TABLE_COLUMNS)


class ReadSpeedCounter:
    def __init__(self, size, default_val=0):
        self._size = size
        self._pos = -size
        now = monotonic()
        self._prev_time = [now for _ in range(size)]
        self._prev_value = [default_val for _ in range(size)]

    def get_speed(self, new_value):
        now = monotonic()
        size = self._size
        cur_pos = self._pos
        if cur_pos >= 0:
            ref_pos = (cur_pos + 1) % size
            prev_time = self._prev_time[ref_pos]
            prev_val = self._prev_value[ref_pos]
        elif cur_pos < 0:
            prev_time = self._prev_time[self._size - 1]
            prev_val = self._prev_value[self._size - 1]
            ref_pos = cur_pos + 1

        runtime = now - prev_time
        speed = float((new_value - prev_val) / runtime)

        self._pos = ref_pos
        self._prev_time[ref_pos] = now
        self._prev_value[ref_pos] = new_value

        return speed

    def reset(self, default_val=0):
        size = self._size
        self._pos = -size
        now = monotonic()
        self._prev_time = [now for _ in range(size)]
        self._prev_value = [default_val for _ in range(size)]


class TagHistory:

    def __init__(self, name):
        self.name = name
        self.times = []
        self.phases = []
        self.corrects = []
        self.diffs = [0, 0]
        self.dopplers = []
        self.rssis = []
        self.channels = []

        self.shift = 0
        self.last_size = 0
        self.last_channel = None

        self.data_by_id = {
            0: self.phases,
            1: self.corrects,
            2: self.dopplers,
            3: self.rssis,
            4: self.diffs
        }

        self.data_lock = threading.Lock()

    def add_data(self, data_time, rssi=-120, channel=1, phase=None,
                 doppler=None):
        with self.data_lock:
            self.times.append(data_time)
            self.rssis.append(rssi)
            self.channels.append(channel)

            if phase is None:
                # What for default value?
                phase = 0
            self.phases.append(phase * ((math.pi * 2) / 4096))

            if doppler is None:
                # What for default value?
                doppler = 0
            self.dopplers.append(doppler)

            # Useless if not impinj, but let it for a first version
            self.phase_diff()

    def remove_shift(self, sine):
        if self.last_channel is None:
            self.last_channel = self.channels[0]
        times_len = len(self.times)
        missed = times_len - self.last_size
        if missed:
            for i in range(times_len - missed, times_len):
                if self.channels[i] != self.last_channel:
                    self.shift = self.phases[i] - self.corrects[-1]
                    self.corrects.append(
                        (self.phases[i] - self.shift) % (math.pi * 2))
                    self.last_channel = self.channels[i]
                else:
                    self.corrects.append(
                        (self.phases[i] - self.shift) % (math.pi * 2))
                # testing this, works badly
                if sine:
                    self.corrects[-1] = math.sin(2 * self.corrects[-1])
            self.last_size = times_len

    def remove_shift_dummy(self):
        DEFAULT_VALUE = 0
        times_len = len(self.times)
        missed = times_len - self.last_size
        if missed:
            self.corrects += [DEFAULT_VALUE for _ in range(missed)]
            self.last_size = times_len

    def phase_diff(self):
        if len(self.times) > 2:
            if self.channels[-1] != self.channels[-2]:
                # make smarter
                self.diffs.append(self.diffs[-1])
            else:
                diff = self.phases[-1] - self.phases[-2]
                if diff > 6:
                    diff -= math.pi * 2
                elif diff < -6:
                    diff += math.pi * 2
                self.diffs.append(self.diffs[-1] + diff)


class Gui(QObject):
    """graphical unit interface to open connection with a LLRP reader
    and inventory tags.
    """
    inventoryReportReceived = pyqtSignal(set)
    inventoryReportParsed = pyqtSignal(set)
    powerTableChanged = pyqtSignal(list)
    antennaIDListChanged = pyqtSignal(list)
    readerConfigChanged = pyqtSignal()
    readerConnected = pyqtSignal()

    GRAPH_DATASET = {
        0: 'Phase Rotation',
        1: 'Corrected Phase',
        2: 'Doppler Frequency',
        3: 'Peak RSSI',
        4: 'Phase Diff (beta)'
    }

    GRAPH_PLOTPENS = {
        #XXX: Limited colours, needs more elegance, SOLVE!
        0: mkPen('r'),
        1: mkPen('b'),
        2: mkPen('g'),
        3: mkPen('y'),
        4: mkPen('c'),
        5: mkPen('m'),
        6: mkPen('w'),
        7: mkPen('k')
    }

    def __init__(self):
        super(Gui, self).__init__()
        # variables
        self.reader_start_time = None
        self.total_tags_seen = 0
        self.recently_updated_tag_keys = set()
        self.tags_db = {}
        self.tags_db_lock = threading.Lock()
        self.speed_counter = ReadSpeedCounter(6)
        self.history_enabled = False

        self.curves = {}
        self.rolling = False
        # Window size
        self.rollingsize = 1500
        self.graph_current_index = 3

        self.reader = None
        self.readerParam = Parameter.create(name='params',
                                            type='group',
                                            children=readerSettingsParams)
        self.txPowerChangedTimer = QTimer()
        self.txPowerChangedTimer.timeout.connect(self.readerConfigChangedEvent)
        self.txPowerChangedTimer.setSingleShot(True)

        self.tags_table_refresh_timer = QTimer()
        self.tags_table_refresh_timer.timeout.connect(
            self.updateInventoryReport)
        self.tags_table_refresh_timer.setInterval(600)

        self.graph_refresh_timer = QTimer()
        self.graph_refresh_timer.timeout.connect(self.graph_update)
        self.graph_refresh_timer.setInterval(100)


        # ui
        win = MainWindow()
        self.window = win

        win.setWindowTitle(GUI_APP_TITLE)
        win.setWindowIcon(QIcon(GUI_ICON_PATH))

        self.dataplot = win.graph_dataplot

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

        win.graph_history_enable.setChecked(self.history_enabled)
        win.graph_history_enable.stateChanged.connect(
            self.history_enabled_event)
        win.graph_dataset_box.addItems(list(self.GRAPH_DATASET.values()))
        win.graph_dataset_box.setCurrentIndex(self.graph_current_index)
        win.graph_dataset_box.currentIndexChanged.connect(
            self.graph_dataset_event)
        win.graph_gridcheckx.stateChanged.connect(self.graph_gridx_event)
        win.graph_gridchecky.stateChanged.connect(self.graph_gridy_event)
        win.graph_rollgraph.setChecked(self.rolling)
        win.graph_rollgraph.stateChanged.connect(self.graph_roll_enable)
        win.graph_restore_btn.clicked.connect(self.graph_restore_view)

        self.inventoryReportReceived.connect(self.parseInventoryReport)
        # connect event to handlers
        #self.inventoryReportParsed.connect(self.updateInventoryReport)
        self.powerTableChanged.connect(self.updatePowerTableParameterUI)
        self.antennaIDListChanged.connect(self.updateAntennaParameterUI)
        self.readerConfigChanged.connect(self.readerConfigChangedEvent)
        self.readerConnected.connect(self.reader_connected_event)

        self.graph_create()

        self.log("Using sllurp version %s" % sllurp_version)
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
                event_selector={
                    'HoppingEvent': False,
                    'GPIEvent': False,
                    'ROSpecEvent': True,
                    'ReportBufferFillWarning': True,
                    'ReaderExceptionEvent': True,
                    'RFSurveyEvent': False,
                    'AISpecEvent': True,
                    'AISpecEventWithSingulation': False,
                    'AntennaEvent': False,
                },
            )
            impinj_ext_fn = r_param_fn('impinj_extensions').param
            if impinj_ext_fn('enabled').value():
                search_mode = impinj_ext_fn('search_mode').value()
                factory_args['impinj_search_mode'] = search_mode

                factory_args['impinj_tag_content_selector'] = {
                    'EnableRFPhaseAngle': True,
                    'EnablePeakRSSI': True,
                    'EnableRFDopplerFrequency': True
                }

            host = self.host()
            config = LLRPReaderConfig(factory_args)
            self.reader = LLRPReaderClient(host, GUI_DEFAULT_PORT, config)
            self.reader.add_tag_report_callback(self.tag_report_cb)
            self.reader.add_state_callback(LLRPReaderState.STATE_CONNECTED,
                                           self.onConnection)
            self.reader.add_event_callback(self.reader_event_cb)
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

            self.graph_refresh_timer.stop()
            self.tags_table_refresh_timer.stop()
            self.resetWindowWidgets()

            self.log('Disconnected')

    def check_connection_state(self):
        if self.isConnected() and self.reader and not self.reader.is_alive():
            self.log("LLRP reader unexpectedly disconnected")
            self.disconnect()
            self.update_status("Unexpectedly disconnected")
            return False
        return True

    def startInventory(self, duration=None, report_every_n_tags=None,
                       antennas=None, tx_power=None, tari=None, session=None,
                       mode_identifier=None, tag_population=None,
                       tag_filter_mask=None):
        """ask to the reader to start an inventory
        """
        if self.isConnected() and self.check_connection_state():
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
                    "EnableAntennaID": True,
                    "EnableChannelIndex": True,
                    "EnablePeakRSSI": True,
                    "EnableFirstSeenTimestamp": True,
                    "EnableLastSeenTimestamp": True,
                    "EnableTagSeenCount": True,
                    "EnableAccessSpecID": True,
                },
                event_selector={
                    'HoppingEvent': False,
                    'GPIEvent': False,
                    'ROSpecEvent': True,
                    'ReportBufferFillWarning': True,
                    'ReaderExceptionEvent': True,
                    'RFSurveyEvent': False,
                    'AISpecEvent': True,
                    'AISpecEventWithSingulation': False,
                    'AntennaEvent': False,
                },
            )

            impinj_ext_fn = r_param_fn('impinj_extensions').param
            if impinj_ext_fn('enabled').value():
                search_mode = impinj_ext_fn('search_mode').value()
                factory_args['impinj_search_mode'] = search_mode

                factory_args['impinj_tag_content_selector'] = {
                    'EnableRFPhaseAngle': True,
                    'EnablePeakRSSI': True,
                    'EnableRFDopplerFrequency': True
                }

            # update config
            self.reader.update_config(LLRPReaderConfig(factory_args))
            # update internal variable
            self.reader.llrp.parseCapabilities(self.reader.llrp.capabilities)
            # start inventory with update rospec which has been generated with
            # previous config
            self.reader.llrp.startInventory(force_regen_rospec=True)
            self.reader.join(0.1)

            self.tags_table_refresh_timer.start()
            self.graph_refresh_timer.start()
            self.log('Inventory started')
            self.update_status('| STARTED')

    def stopInventory(self):
        """ask to the reader to stop inventory
        """
        if self.isConnected():
            if not self.check_connection_state():
                return
            logger.info("stopping inventory...")
            self.tags_table_refresh_timer.stop()
            self.graph_refresh_timer.stop()

            try:
                self.reader.llrp.stopPolitely()
            except Exception as exc:
                logger.warning("stop_inventory: Reader error ignored for "
                               "stopPolitely : %s" % str(exc))
            self.reader.join(0.1)

            self.log('Inventory stopped')
            unique_tags = len({x[0] for x in self.get_tags_db_copy().keys()})
            msg = '%d tags seen (%d uniques) | PAUSED' % (
                self.total_tags_seen, unique_tags)
            self.update_status(msg)

    def tag_report_cb(self, reader, tags):
        """sllurp tag report callback, it emits a signal in order to perform
        the report parsing on the QT loop to avoid GUI freezing
        """
        with self.tags_db_lock:

            history_enabled = self.history_enabled
            tags_db = self.tags_db
            start_time = self.reader_start_time
            if start_time is None:
                start_time = 0

            new_tag_seen_count = 0
            updated_tag_keys = set()

            #logger.info('%s tag_filter_mask=<%s>', str(tags),
            #            str(self.reader.llrp.config.tag_filter_mask))
            #logger.info('Full: %s', pprint.pformat(tags))

            # parsing each tag in the report
            for tag in tags:
                # get epc ID. (EPC covers EPC-96 and EPCData)
                epc = tag["EPC"].decode("utf-8").upper()
                ant_id = tag["AntennaID"]
                # Convert to milliseconds
                if start_time:
                    new_first_seen_tstamp = \
                        (tag.get('FirstSeenTimestampUTC', start_time)
                        - start_time) // 1000
                else:
                    # ROSpec start was missed, or data was cleared
                    # mid-inventory
                    new_first_seen_tstamp = 0
                    start_time = tag.get('FirstSeenTimestampUTC', 0)
                    self.reader_start_time = start_time

                last_seen_tstamp = (tag.get('LastSeenTimestampUTC', start_time)
                                    - start_time) // 1000
                key = (epc, ant_id)
                prev_info = tags_db.get(key, {})
                prev_history = prev_info.get('history', TagHistory(key))

                seen_count_new = tag.get('TagSeenCount', 1)
                seen_count = prev_info.get('seen_count', 0) + seen_count_new

                channel_idx_new = tag.get('ChannelIndex', 0)
                channel_idx_old = prev_info.get('channel_index', 0)

                # PeakRSSI highest value
                peakrssi_new = tag.get('PeakRSSI', -120)
                peakrssi_best = max(peakrssi_new, prev_info.get('rssi', -120))

                first_seen_tstamp = prev_info.get('first_seen',
                                                new_first_seen_tstamp)

                new_info = {
                    'epc': epc,
                    'antenna_id': ant_id,
                    'history': prev_history,
                    'rssi': peakrssi_best,
                    'channel_index': channel_idx_old or channel_idx_new,
                    'seen_count': seen_count,
                    'first_seen': first_seen_tstamp,
                    'last_seen': last_seen_tstamp,
                    'last_rssi': peakrssi_new,
                    'last_channel_index': channel_idx_new
                }

                # Add Impinj specific data if available
                phase = tag.get('ImpinjRFPhaseAngle')
                if phase is not None:
                    new_info['impinj_phase'] = phase
                doppler_freq = tag.get('ImpinjRFDopplerFrequency')
                if doppler_freq is not None:
                    new_info['impinj_doppler'] = doppler_freq

                tags_db[key] = new_info

                if history_enabled:
                    prev_history.add_data(new_first_seen_tstamp,
                                        peakrssi_new,
                                        channel_idx_new,
                                        phase,
                                        doppler_freq)


                new_tag_seen_count += seen_count_new
                updated_tag_keys.add(key)

            self.total_tags_seen += new_tag_seen_count


        self.inventoryReportReceived.emit(updated_tag_keys)

    def reader_event_cb(self, reader, events):
        timestamp_event = events.get('UTCTimestamp', {})
        timestamp_us = timestamp_event.get('Microseconds', 0)
        if self.reader_start_time:
                timestamp_since_start = timestamp_us - self.reader_start_time
        else:
                timestamp_since_start = 0

        # Set reader_start at the time of the first ROSpec start event
        rospec_event = events.get('ROSpecEvent', {})
        if rospec_event:
            event_type = rospec_event.get('EventType')
            if event_type == 'Start_of_ROSpec' and not self.reader_start_time:
                self.reader_start_time = timestamp_us

    def clear_tags_db(self):
        with self.tags_db_lock:
            self.tags_db = {}

    def get_tags_db_copy(self):
        """Freeze the value of the tags db for display

        Warning: This is not a deep copy of the db, and except the tag key list
        itself, it will still be "reference" to inner tag info and history.
        This should be crash-free acceptable even if maybe not always
        perfectly consistent as tags info are updated atomically by
        tag_report_cb.
        The goal of the lock and copy is mainly to avoid unexpected issues
        with the "clear_tags" operation at the wrong time.
        """
        with self.tags_db_lock:
            return self.tags_db.copy()

    def parseInventoryReport(self, updated_tag_keys):
        """Function called each time the reader reports seeing tags,
        It is run on the QT loop to avoid GUI freezing.
        """
        self.recently_updated_tag_keys.update(updated_tag_keys)
        #self.inventoryReportParsed.emit(updated_tag_keys)

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

        buttonBox = QDialogButtonBox(QBtn)
        buttonBox.accepted.connect(dlg.accept)
        buttonBox.rejected.connect(dlg.reject)
        layout.addWidget(buttonBox)
        dlg.setLayout(layout)
        paramTree.setParameters(self.readerParam, showTop=False)

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
        old_db_total_tags = self.total_tags_seen
        self.reader_start_time = None
        self.total_tags_seen = 0
        self.speed_counter.reset()

        self.dataplot.clear()
        self.curves.clear()
        self.dataplot.legend = None
        self.dataplot.addLegend()

        self.clear_tags_db()
        win.tags_view_table.update(self.get_tags_db_copy())
        win.tags_view.resizeColumnsToContents()

        if old_db_total_tags:
            # Only show the log entry when it did something
            self.log('Tag data cleared')
        self.update_status('')

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

    def updateInventoryReport(self):
        """called to update inventory tree view
        """
        if not self.check_connection_state():
            return
        # update inventory widget
        tags_copy = self.get_tags_db_copy()
        if self.recently_updated_tag_keys:
            speed = self.speed_counter.get_speed(self.total_tags_seen)

            self.window.tags_view_table.update(tags_copy)
            self.recently_updated_tag_keys = set()
            self.window.tags_view.resizeColumnsToContents()

            unique_tags = len({x[0] for x in tags_copy.keys()})
            msg = '%d tags/second - %d tags seen (%d uniques) | RUNNING' % (
                speed, self.total_tags_seen, unique_tags)
            self.update_status(msg)

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
        self.readerConnected.emit()

    def reader_connected_event(self):
        self.updateconnectionButton()
        self.log('Connected to %s' % self.reader.get_peername()[0])

        # parse reader capabilities
        self.powerTableChanged.emit(self.reader.llrp.tx_power_table)
        self.antennaIDListChanged.emit(
            list(range(1, self.reader.llrp.max_ant + 1)))

        try:
            ## TO BE FIXED: We use too much sllurp internals knowledge
            capab = self.reader.llrp.capabilities
            #capab_msg = self.reader.llrp.LLRPMessage(capab)
            capab_msg = llrp_data2xml({'GET_READER_CAPABILITIES_RESPONSE':
                                       capab})
            self.window.reader_capacities_box.setPlainText(capab_msg)
        except Exception as exc:
            logger.error("Error setting the reader capacities box: %s",
                         str(exc))

        ## TO BE ADDED for reader config
        #try:
        #    self.window.reader_config_box.setText(
        #        pprint.pformat(self.reader.llrp.capabilities))
        #except Exception:
        #    pass

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

    def graph_create(self):
        self.curves.clear()
        self.dataplot.setLabel('bottom', text='Time', units='ms')
        self.dataplot.legend = None
        self.dataplot.addLegend()
        self.graph_restore_view()

    def graph_restore_view(self):
        self.dataplot.setLabel(
            'left',
            text=self.GRAPH_DATASET[self.graph_current_index]
        )
        #self.graphwidget.setStatusTip(self.dataSelect.get(
        #    self.selectDataBox.currentIndex()) + ' graph representation')
        rangeswitch = {
            0: (0, math.pi * 2),
            1: (0, math.pi * 2),
            2: (-2000, 2000),
            3: (-90, -10),
            4: (-4, 4)
        }
        r = rangeswitch.get(self.graph_current_index)
        self.dataplot.setYRange(r[0], r[1])
        if self.rolling:
            self.dataplot.setXRange(0, self.rollingsize)
        else:
            self.dataplot.enableAutoRange(
                axis=self.dataplot.getViewBox().XAxis)

        self.graph_update()

    def graph_update(self):
        if not self.history_enabled:
            return
        if not self.check_connection_state():
            return

        dataset_index = self.graph_current_index
        curves = self.curves
        dataplot = self.dataplot

        reader_mode = self.readerParam.param('mode_identifier').value()
        impinj_enabled = \
            self.readerParam.param('impinj_extensions').param('enabled').value()

        tags_db_copy = self.get_tags_db_copy()
        for name, tag in tags_db_copy.items():
            try:
                tag_hist = tag['history']
            except KeyError:
                continue

            if name not in curves:
                # Name is in fact tag key= (epc, ant_id)
                new_name = "%s (%d)" % (name[0], name[1])
                new_pen = self.GRAPH_PLOTPENS.get(len(curves))
                cur_curve = dataplot.plot(pen=new_pen, name=new_name)
                curves[name] = cur_curve
            else:
                cur_curve = curves[name]

            if self.rolling:
                # subsamplelist = tag_hist.data_by_id[dataset_index][-self.rollingsize:]
                subtimelist = tag_hist.times[-self.rollingsize:]
                dataplot.setXRange(subtimelist[0], subtimelist[-1])
                # curves[name].setData(y=subsamplelist, x=subtimelist)
            # else:
            with tag_hist.data_lock:
                if impinj_enabled:
                    # TODO: arg looks to be arbitrary, to be reviewed
                    tag_hist.remove_shift(reader_mode > 0)
                else:
                    # Ensure that "corrects" is also filled with 0 values
                    tag_hist.remove_shift_dummy()

                cur_curve.setData(y=tag_hist.data_by_id[dataset_index],
                                  x=tag_hist.times)

    def history_enabled_event(self, state):
        if state == Qt.Checked:
            self.history_enabled = True
            self.graph_restore_view()
        else:
            self.history_enabled = False

    def graph_dataset_event(self, index):
        self.graph_current_index = index
        self.graph_restore_view()

    def graph_gridx_event(self, state):
        if state == Qt.Checked:
            self.dataplot.showGrid(x=True)
        else:
            self.dataplot.showGrid(x=False)

    def graph_gridy_event(self, state):
        if state == Qt.Checked:
            self.dataplot.showGrid(y=True)
        else:
            self.dataplot.showGrid(y=False)

    def graph_roll_enable(self, state):
        self.graph_restore_view()
        if state == Qt.Checked:
            self.rolling = True
            self.dataplot.disableAutoRange()
        else:
            self.rolling = False
            self.dataplot.enableAutoRange(
                axis=self.dataplot.getViewBox().XAxis)
        self.graph_update()

    def log(self, text):
        timenow = '{0:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now())
        self.window.logger_box.appendPlainText(timenow + ': ' + text)

    def update_status(self, text):
        self.window.status_label.setText(text)


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
        status_label = QLabel('')
        status_bar.addPermanentWidget(status_label)
        self.status_label = status_label

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
        tabbed_body_w = QGroupBox("Reports", parent=parent_widget)
        inventoryL = QVBoxLayout(tabbed_body_w)

        tabs_w = QTabWidget(parent=tabbed_body_w)
        inventoryL.addWidget(tabs_w)

        # Add widget tabs
        inventory_tab = self.create_inventory_tags_tab(tabs_w)
        tabs_w.addTab(inventory_tab, 'Inventory Tag Reads')

        adv_graph_tab = self.create_advanced_graph_tab(tabs_w)
        tabs_w.addTab(adv_graph_tab, 'Advanced Graph')

        log_tab = self.create_logs_tab(tabs_w)
        tabs_w.addTab(log_tab, 'Operation Log')

        capab_tab = self.create_rcapabilities_tab(tabs_w)
        tabs_w.addTab(capab_tab, 'Reader Capabilities')

        #config_tab = self.create_rconfig_tab(tabs_w)
        #tabs_w.addTab(config_tab, 'Reader Config')

        return tabbed_body_w

    def create_inventory_tags_tab(self, parent_widget):
        # Inventory tree view
        tags_view = QTableView(parent=parent_widget)
        tags_view.setAlternatingRowColors(True)

        table_stylesheet = r"""
            QTableView {
                Background-color:rgb(230,230,230);
                gridline-color:white; font-size:12pt;
                font-style:bold;
            };
        """

        tags_view.setStyleSheet(table_stylesheet)

        headers_stylesheet = r"""
            QHeaderView {
                Background-color:rgb(230,230,230);
                border-left-color: black;
                border-right-color: black
            };
            QHeaderView::section{
                Background-color:rgb(200,200,200);
                font-size:12pt;
                font-style:bold;
            };
        """
        tags_view.horizontalHeader().setStyleSheet(headers_stylesheet)
        tags_view.verticalHeader().setStyleSheet(headers_stylesheet)

        # Hide the QTableView corner
        global_stylesheet = r"""
            QTableView QTableCornerButton::section {
                background-color: rgb(230, 230, 230);
            }
        """
        self.setStyleSheet(global_stylesheet)


        # Operation list model
        self.tags_view_table = TagsTableModel({})

        ## treeview.resizeColumnToContents(3)
        ## treeview.resizeColumnToContents(2)
        #treeview.resizeColumnToContents(1)
        #treeview.resizeColumnToContents(0)
        tags_view.resizeColumnsToContents()

        # Set model to view
        tags_view.setModel(self.tags_view_table)
        tags_view.setContextMenuPolicy(Qt.CustomContextMenu)
        tags_view.customContextMenuRequested.connect(self.openMenu)

        self.tags_view = tags_view
        return tags_view

    def create_advanced_graph_tab(self, parent_widget):
        adv_graph_w = QWidget(parent=parent_widget)
        adv_graph_l = QHBoxLayout(adv_graph_w)

        # Graph menu buttons
        history = QCheckBox('Enable tag recording (Graph)')
        history.setStatusTip('Enable/disable tag history recording that is '
                                'needed to be displayed on the graph')
        history.setChecked(False)

        select_data_box = QComboBox()
        select_data_box.setStatusTip('Select data to be shown')

        select_layout = QHBoxLayout()
        select_label = QLabel(self)
        select_label.setText('Data to be shown')
        select_layout.addWidget(select_label)
        select_layout.addWidget(select_data_box)

        gridcheckx = QCheckBox('Enable Grid for X-Axis')
        gridcheckx.setStatusTip('Enable/disable X-Grid')
        gridcheckx.setChecked(False)

        gridchecky = QCheckBox('Enable Grid for Y-Axis')
        gridchecky.setStatusTip('Enable/disable Y-Grid')
        gridchecky.setChecked(False)

        rollgraph = QCheckBox('Enable rolling viewpoint', self)
        rollgraph.setChecked(False)

        restore_btn = QPushButton('Restore view', self)
        restore_btn.setToolTip('Restore current graphs viewpoint')
        restore_btn.setStatusTip('Restore current graphs viewpoint')

        # Create graph menu
        button_layout = QVBoxLayout()
        """
        buttonlayout.addWidget(self.cleardatbtn)
        buttonlayout.addWidget(self.exportbtn)
        buttonlayout.addStretch()
        buttonlayout.addWidget(self.qbtn)
        """
        button_layout.addWidget(history)
        button_layout.addLayout(select_layout)
        button_layout.addStretch()
        button_layout.addWidget(gridcheckx)
        button_layout.addWidget(gridchecky)
        button_layout.addWidget(rollgraph)
        button_layout.addWidget(restore_btn)

        # Create graph main dipslay
        graph_w = GraphicsLayoutWidget()
        graph_w.setBackground('w')

        dataplot = graph_w.addPlot()

        adv_graph_l.addLayout(button_layout, 1)
        adv_graph_l.addWidget(graph_w, 5)

        self.graph_history_enable = history
        self.graph_gridcheckx = gridcheckx
        self.graph_gridchecky = gridchecky
        self.graph_rollgraph = rollgraph
        self.graph_restore_btn = restore_btn
        self.graph_dataset_box = select_data_box

        self.graph_dataplot = dataplot
        return adv_graph_w

    def create_logs_tab(self, parent_widget):
        # Create a logs box
        logger_box_w = QPlainTextEdit()
        logger_box_w.setReadOnly(True)

        self.logger_box = logger_box_w
        return logger_box_w

    def create_rcapabilities_tab(self, parent_widget):
        # Create a logs box
        capab_box_w = QPlainTextEdit()
        capab_box_w.setReadOnly(True)

        self.reader_capacities_box = capab_box_w
        return capab_box_w

    def create_rconfig_tab(self, parent_widget):
        # Create a logs box
        rconfig_box_w = QPlainTextEdit()
        rconfig_box_w.setReadOnly(True)

        self.reader_config_box = rconfig_box_w
        return rconfig_box_w

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
            lambda: self.itemValueToClipboard(self.tags_view.indexAt(pos)))
        menu = QMenu()
        menu.addAction(action)
        pt = QPoint(pos)
        menu.exec(self.tags_view.mapToGlobal(pos))

    def itemValueToClipboard(self, index):
        QApplication.clipboard().setText(
            self.tags_view.model().itemFromIndex(index).text())


def main():
    app = QApplication(sys.argv)
    gui = Gui()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
