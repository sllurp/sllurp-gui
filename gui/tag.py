#!/usr/bin/python3

'''
Tag class for easy managing of llrp datapoints. Created by Thijmen Ketel.
Use with sllurp python implementation of Low Level Reader Protocol.
'''

import math
import numpy as np

class Tag():

    start = None    # static start time variable

    def __init__(self, legacy, data):
        self.name = data['EPC-96']
        self.time = []
        self.phase = []
        self.correct = []
        self.diff = [0, 0]
        self.doppler = []
        self.rssi = []
        self.channel = []
        self.addDataSwitch(legacy, data)
        self.shift = 0
        self.lastSize = 0
        self.lastChannel = None

    def addDataSwitch(self, legacy, datapoint):
        '''
        If you're operating a reader that does not support Impinj 
        low level extensions, add data points in legacy mode.
        '''
        if legacy:
            self.addLegacyData(datapoint)
        else:
            self.addData(datapoint)

    def addData(self, datapoint):
        if Tag.start == None:
            Tag.start = datapoint['FirstSeenTimestampUTC']/1000
        self.time.append((datapoint['FirstSeenTimestampUTC']/1000) - Tag.start)
        self.phase.append(datapoint['ImpinjPhase']*((math.pi*2)/4096))
        self.doppler.append(datapoint['ImpinjRFDopplerFrequency'])
        self.rssi.append(datapoint['ImpinjPeakRSSI']/100)
        self.channel.append(datapoint['ChannelIndex'])
        self.phaseDiff()

    def addLegacyData(self, datapoint):
        if Tag.start == None:
            Tag.start = datapoint['FirstSeenTimestampUTC']/1000
        self.time.append((datapoint['FirstSeenTimestampUTC']/1000) - Tag.start)
        self.rssi.append(datapoint['PeakRSSI'])
        self.channel.append(datapoint['ChannelIndex'])

    def removeShift(self, sine):
        if self.lastChannel == None:
            self.lastChannel = self.channel[0]
        missed = self.getSize() - self.lastSize
        if missed is not 0:
            for i in range(self.getSize()-missed, self.getSize()):
                if self.channel[i] is not self.lastChannel:
                    self.shift = self.phase[i] - self.correct[-1]
                    self.correct.append(
                        (self.phase[i] - self.shift) % (math.pi*2))
                    self.lastChannel = self.channel[i]
                else:
                    self.correct.append(
                        (self.phase[i] - self.shift) % (math.pi*2))
                if sine:    # testing this, works badly
                    self.correct[-1] = np.sin(2*self.correct[-1])
            self.lastSize = self.getSize()
    
    def removeShiftCalibrated(self, offsets, hoptable):
        '''
        This stuff doesn't seem to work, refer to Tagyro paper for
        theoretical base (page 7, eq. 10 and 11).
        '''
        missed = self.getSize() - self.lastSize 
        if missed is not 0:
            for i in range(self.getSize()-missed, self.getSize()):
                corrected = ((self.phase[i] - offsets.get(self.channel[i])) * 
                    (hoptable.get(1)/hoptable.get(self.channel[i])) + offsets.get(1)) % (math.pi*2)
                if len(self.correct) > 1:
                    self.correct.append(unwrap(self.correct[-1], corrected))
                else:
                    self.correct.append(corrected)
            self.lastSize = self.getSize()            

    def phaseDiff(self):
        if self.getSize() > 2:
            if self.channel[-1] is not self.channel[-2]:
                self.diff.append(self.diff[-1])  # make smarter
            else:
                diff = self.phase[-1] - self.phase[-2]
                if diff > 6:
                    diff -= math.pi*2
                elif diff < -6:
                    diff += math.pi*2
                self.diff.append(self.diff[-1]+diff)

    def getData(self, index):
        switcher = {
            0: self.getPhase,
            1: self.getCorrect,
            2: self.getDoppler,
            3: self.getRSSI,
            4: self.getDiff
        }
        getData = switcher.get(index)
        return getData()

    def getSize(self):
        return len(self.time)

    def getPhase(self):
        return self.phase

    def getCorrect(self):
        return self.correct

    def getDoppler(self):
        return self.doppler

    def getRSSI(self):
        return self.rssi

    def getDiff(self):
        return self.diff

    def getTime(self):
        return self.time

    def getChannel(self):
        return self.channel

def unwrap(p1, p2):
    if p2 - p1 >= math.pi:
        return p2 - 2*math.pi
    elif abs(p2 - p1) < math.pi:
        return p2
    elif p2 - p1 <= -math.pi:
        return p2 + 2*math.pi