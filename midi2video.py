#!/bin/env python3
# -*- coding: utf-8 -*- 

# limitiations
# tempo changes are not supported

# @see https://github.com/vishnubob/python-midi/pull/62/commits/9aa092e653684c871b9ee2293ee8e640bb1cab34
import argparse
import logging
import subprocess
import configparser
import mydy as midi
import sys
import math
import os
import time
from pathlib import Path
from shutil import rmtree, copyfile
from colorsys import rgb_to_hls, hls_to_rgb
from cairosvg import svg2png

# https://stackoverflow.com/questions/2352181/how-to-use-a-dot-to-access-members-of-dictionary
class Map(dict):
    """dot.notation access to dictionary attributes"""
    def __getattr__(self, attr):
        return self.get(attr)
    __setattr__= dict.__setitem__
    __delattr__= dict.__delitem__

    def __getstate__(self):
        return self

    def __setstate__(self, state):
        self.update(state)
        self.__dict__ = self

class VirtualPiano(object):
    def __init__(self, config):
        self.startNote = config.get('piano', 'startNote', fallback='auto')
        self.endNote = config.get('piano', 'endNote', fallback='auto')
        self.colorWhiteKeys = config.get('piano', 'colorWhiteKeys', fallback='#FFFFFF')
        self.colorBlackKeys = config.get('piano', 'colorBlackKeys', fallback='#131313')
        self.colorHighlight = config.get('piano', 'colorHighlight', fallback='#DE4439')
        self.outlineColorWhiteKeys = config.get('piano', 'outlineColorWhiteKeys', fallback='#131313')
        self.outlineColorBlackKeys = config.get('piano', 'outlineColorBlackKeys', fallback='#131313')
        self.outlineColorHighlight = config.get('piano', 'outlineColorHighlight', fallback='#6e160f')
        self.amountWhiteKeys = 0
        self.pianoWidth = 0
        self.pianoHeight = 0

        self.tempDir = None
        self.tempDirFrames = None

        self.keySvgPaths = {}

        self.svg = Map({
            'A': Map({ 'L':0, 'M':0, 'R':0 }),
            'B': Map({ 'L':0, 'M':0, 'R':0 }),
            'C': Map({ 'L':0, 'M':0, 'R':0 }),
            'D': Map({ 'L':0, 'M':0, 'R':0 }),
            'E': Map({ 'L':0, 'M':0, 'R':0 }),
            'F': Map({ 'L':0, 'M':0, 'R':0 }),
            'G': Map({ 'L':0, 'M':0, 'R':0 }),
            'A#': 0, 'C#': 0, 'D#': 0, 'F#': 0, 'G#': 0,
            'white': Map({ 'w' : 0, 'h' : 0 }),
            'black': Map({ 'w' : 0, 'h' : 0, 'diff': 0 }),
            'scale': Map({ 'x' : 1, 'y' : 1 })
        })

    '''
        This keyboard has following properties (x=octave width).
        1. All white keys have equal width in front (W=x/7).
        2. All black keys have equal width (B=x/12).
        3. The narrow part of white keys C, D and E is W - B*2/3
        4. The narrow part of white keys F, G, A, and B is W - B*3/4
    '''
    def calculateSvgDimensions(self,videoWidth, videoHeight, whiteW=100, whiteH=200, blackH=120):
        self.pianoWidth = videoWidth
        self.pianoHeight = videoHeight
        self.amountWhiteKeys = self.countWhiteKeys(self.startNote, self.endNote)

        self.svg.white.w = whiteW
        self.svg.white.h = whiteH
        self.svg.black.h = blackH
        self.svg.black.diff = whiteH - blackH

        octaveW = whiteW * 7
        self.svg.black.w = octaveW / 12

        narrowPartCDE = self.svg.white.w - self.svg.black.w*2/3
        narrowPartFGAB = self.svg.white.w - self.svg.black.w*3/4

        self.svg.C.L = narrowPartCDE
        self.svg.C.R = self.svg.white.w - narrowPartCDE
        self.svg.D.L = self.svg.black.w - self.svg.C.R
        self.svg.D.M = narrowPartCDE
        self.svg.D.R = self.svg.white.w - self.svg.D.L - self.svg.D.M
        self.svg.E.R = narrowPartCDE
        self.svg.E.L = self.svg.white.w - narrowPartCDE
        self.svg.F.L = narrowPartFGAB
        self.svg.F.R = self.svg.white.w - narrowPartFGAB
        self.svg.G.L = self.svg.black.w - self.svg.F.R
        self.svg.G.M = narrowPartFGAB
        self.svg.G.R = self.svg.white.w - self.svg.G.L - self.svg.G.M
        self.svg.A.L = self.svg.black.w - self.svg.G.R
        self.svg.A.M = narrowPartFGAB
        self.svg.A.R = self.svg.white.w - self.svg.A.L - self.svg.A.M
        self.svg.B.R = narrowPartFGAB
        self.svg.B.L = self.svg.white.w - narrowPartFGAB

        # horizontal offset relative to left white key
        self.svg['A#'] = self.svg.A.L + self.svg.A.M
        self.svg['C#'] = self.svg.C.L
        self.svg['D#'] = self.svg.D.L + self.svg.D.M
        self.svg['F#'] = self.svg.F.L
        self.svg['G#'] = self.svg.G.L + self.svg.G.M

        realSvgWidth = self.amountWhiteKeys * self.svg.white.w
        realSvgHeight = self.svg.white.h

        self.svg.scale.x = self.pianoWidth / realSvgWidth
        self.svg.scale.y = self.pianoHeight / realSvgHeight



    # thanks to https://stackoverflow.com/questions/712679/convert-midi-note-numbers-to-name-and-octave#answer-54546263
    def noteNumberToNoteName(self, noteNumber):
        noteNumber -= 9
        notes = [ "A", "A#", "B", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#" ]
        #octave = math.floor(noteNumber / 12) + 1
        return notes[ noteNumber % 12 ]

    def isWhiteKey(self, noteNumber):
        if self.noteNumberToNoteName(noteNumber) in ["A#", "C#", "D#", "F#", "G#"]:
            return False
        return True

    def countWhiteKeys(self, startNote, endNote):
        counter = 0
        for noteName in range(startNote, endNote+1):
            if self.isWhiteKey(noteName):
                counter += 1

        return counter

    def getLeftOffsetForKeyPlacement(self, noteNumber):
        numWhiteKeys = self.countWhiteKeys(self.startNote, noteNumber)
        sumWhiteKeysWidth = (numWhiteKeys-1) * self.svg.white.w
        if self.isWhiteKey(noteNumber):
            return sumWhiteKeysWidth

        return sumWhiteKeysWidth + self.svg[self.noteNumberToNoteName(noteNumber)]


    def hex2rgb(self, hexString):
        return tuple(int(hexString.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

    def rgb2hex(self, rgb):
        rgblist = list(rgb)
        return '#%02x%02x%02x' % (rgblist[0], rgblist[1], rgblist[2])

    def lightenColor(self, color, amount=0.2):
        rgb = list(self.hex2rgb(color))
        return self.adjustColorLightness(rgb[0], rgb[1], rgb[2], 1 + amount)

    def darkenColor(self, color, amount=0.2):
        rgb = list(self.hex2rgb(color))
        return self.adjustColorLightness(rgb[0], rgb[1], rgb[2], 1 - amount)

    # thanks to https://news.ycombinator.com/item?id=3583564
    def adjustColorLightness(self, r, g, b, factor):
        h, l, s = rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
        l = max(min(l * factor, 1.0), 0.0)
        r, g, b = hls_to_rgb(h, l, s)
        return self.rgb2hex((int(r * 255), int(g * 255), int(b * 255)))

    '''  ___
        |   |
        |   |
        |   |  this shape applies to all black keys, C(last), E(first), F(last), B(first)
        |___|
    '''
    def getSquareShapedPath(self, width, height):
        return "0 v %d h %d V 0 h -%d" % (height, width, width)

    '''  _
        | |
        | |_
        |   |  this shape applies to C, F, D(first), G(first), A(first)
        |___|
    '''
    def getCShapedPath(self, xLeft, xRight):
        return "%s h %s v -%s h -%s V 0 h -%s" % (
            self.svg.white.h,
            self.svg.white.w,
            self.svg.black.diff,
            xRight,
            xLeft
        )

    '''    _
          | |
         _| |_
        |     |  this shape applies to D, G, A
        |_____|
    '''
    def getDShapedPath(self, xLeft, xMiddle, xRight):
        return "%s h %s v -%s h -%s V 0 h -%s v %s h -%s" % (
            self.svg.white.h,
            self.svg.white.w,
            self.svg.black.diff,
            xRight,
            xMiddle,
            self.svg.black.h,
            xLeft
        )

    '''    _
          | |
         _| |
        |   | this shape applies to E, B, D(last), G(last), A(last)
        |___|
    '''
    def getEShapedPath(self, xLeft, xRight):
        return "%s h %s V 0 h -%s v %s h -%s" % (
            self.svg.white.h,
            self.svg.white.w,
            xRight,
            self.svg.black.h,
            xLeft
        )

    def getPathChunkForNoteName(self, noteName, noteNumber):

        if str(noteNumber) in self.keySvgPaths:
            return self.keySvgPaths[str(noteNumber)]

        svg = self.svg
        if not self.isWhiteKey(noteNumber):
            pathChunk = self.getSquareShapedPath(svg.black.w, svg.black.h)

        if noteName in ["C", "F"]:
            pathChunk = self.getCShapedPath(svg[noteName].L, svg[noteName].R)
            if noteNumber == self.endNote:
                pathChunk = self.getSquareShapedPath(svg.white.w, svg.white.h)

        if noteName in ["D", "G", "A"]:
            pathChunk = self.getDShapedPath(svg[noteName].L, svg[noteName].M, svg[noteName].R)
            if noteNumber == self.startNote:
                pathChunk = self.getCShapedPath(svg[noteName].L + svg[noteName].M, svg[noteName].R)
            if noteNumber == self.endNote:
                pathChunk = self.getEShapedPath(svg[noteName].L, svg[noteName].M + svg[noteName].R)

        if noteName in ["E", "B"]:
            pathChunk = self.getEShapedPath(svg[noteName].L, svg[noteName].R)
            if noteNumber == self.startNote:
                pathChunk = self.getSquareShapedPath(svg.white.w, svg.white.h)

        # path does never change. so add it to cache dict
        self.keySvgPaths[str(noteNumber)] = pathChunk
        return pathChunk


    def getSvgPathForNoteNumber(self, noteNumber, offsetX, highlightColor=""):

        colorToUse = self.colorBlackKeys
        outlineColor = self.outlineColorBlackKeys
        if self.isWhiteKey(noteNumber):
            colorToUse = self.colorWhiteKeys
            outlineColor = self.outlineColorWhiteKeys

        if highlightColor:
            colorToUse = highlightColor
            outlineColor = self.outlineColorHighlight

        noteLetter = self.noteNumberToNoteName(noteNumber)

        pathString = '<path fill="%s" stroke="%s" d="M%s %s Z"  transform="scale(%s, %s)" />' % (
            colorToUse,
            outlineColor,
            offsetX,
            self.getPathChunkForNoteName(noteLetter, noteNumber),
            self.svg.scale.x,
            self.svg.scale.y
        )

        return pathString





class Midi2Video(object):
    def __init__(self, scriptPath, config):
        self.scriptPath = scriptPath
        self.midiFile = None
        self.midiFileCopy = None
        self.notesToProcess = []
        self.openNotes = {}
        self.noteFadeIns = {}
        self.noteFadeOuts = {}
        self.piano = VirtualPiano(config)
        self.lowestFoundNoteNumber = 200
        self.highestFoundNoteNumber = 0
        self.notesCollected = False
        self.videoWidth = int(config.get('video', 'width', fallback=800))
        self.videoHeight = int(config.get('video', 'height', fallback=100))
        self.framesPerSecond = int(config.get('video', 'frameRate', fallback=25))
        self.soundFont = config.get('video', 'soundFont', fallback='')
        self.noteFadeIn = config.get('video', 'noteFadeIn', fallback='0')
        self.noteFadeOut = config.get('video', 'noteFadeOut', fallback='0')
        self.fixTrackLength = config.get('preprocess', 'fixTrackLength', fallback='0')

        self.videoDurationMs = 0
        self.videoTotalFrames = 0

        self.tempDir = None
        self.tempDirFrames = None

    # we need to add an absolute microtimestamp to each note event
    # TODO: add configuration like channelWhitelist and/or channelBlacklist
    def prepareNoteEvents(self):
        if self.midiFileCopy:
            pattern = midi.FileIO.read_midifile(self.midiFileCopy.resolve())
        else:
            pattern = midi.FileIO.read_midifile(self.midiFile.resolve())

        tempo = 50000        # default: 120 BPM
        ticksPerBeat = pattern.resolution
        lastEventTick = 0
        microseconds = 0

        mpt = tempo / ticksPerBeat

        # https://stackoverflow.com/questions/34166367/how-to-correctly-convert-midi-ticks-to-milliseconds#answer-34174936
        for track in pattern:
            t = 0
            #track.make_ticks_abs()
            for event in track:

                if event.__class__.__name__ == "SetTempoEvent":
                    tempo = event.mpqn
                    mpt = tempo / ticksPerBeat

                deltaTicks = event.tick - lastEventTick
                lastEventTick = event.tick
                deltaMicroseconds = tempo * deltaTicks / ticksPerBeat
                microseconds += deltaMicroseconds
                t += event.tick
                if event.__class__.__name__ not in ["NoteOnEvent", "NoteOffEvent"]:
                    continue

                eventMicroSecond = t * mpt
                if eventMicroSecond > self.videoDurationMs:
                    self.videoDurationMs = eventMicroSecond

                # skip note events that are outside our visible keyboard range
                if not self.piano.startNote == "auto" and event.data[0] < int(self.piano.startNote):
                    continue

                if not self.piano.endNote == "auto" and event.data[0] > int(self.piano.endNote):
                    continue

                if event.data[0] < self.lowestFoundNoteNumber:
                    self.lowestFoundNoteNumber = event.data[0]

                if event.data[0] > self.highestFoundNoteNumber:
                    self.highestFoundNoteNumber = event.data[0]
                self.notesToProcess.append(tuple((eventMicroSecond, event)))

                #print ( eventMicroSecond, t, "Note", e.data[0], "on" if e.data[1] > 0 else "off" )

        self.videoTotalFrames = int(math.ceil(self.videoDurationMs/1000000*self.framesPerSecond))
        self.notesCollected = True

    def createTempDir(self):
        self.tempDir = Path('%s/temp-%s' % (self.scriptPath.resolve(), self.midiFile.name))
        if self.tempDir.is_dir():
            rmtree(self.tempDir.resolve())

        self.tempDir.mkdir(parents=True, exist_ok=True)

    def createTempSubDirs(self):
        self.tempDirFrames = Path('%s/frames' % (self.tempDir.resolve() ))
        self.tempDirFrames.mkdir(parents=True, exist_ok=True)

        self.piano.tempDir = self.tempDir
        self.piano.tempDirFrames = self.tempDirFrames

        # create a dir for every single (start) note to avoid filesystem boundries
        for noteNumber in range(self.piano.startNote, self.piano.endNote+1):
            noteDir = Path('%s/%s' % ( self.tempDirFrames.resolve(), noteNumber) )
            noteDir.mkdir(parents=True, exist_ok=True)


    def createVideo(self):
        startTime = time.time()
        frameDurationMs = 1000000/self.framesPerSecond
        currentFrameStartMs = 0
        reachedPercent = 0

        frameFilePaths = []
        for frameNum in range(1,self.videoTotalFrames+1):
            reachedPercent = int(frameNum / (self.videoTotalFrames/100))
            print ('create single frames: %i %%' % reachedPercent, end='\r' )
            sys.stdout.flush()
            currentFrameEndMs = currentFrameStartMs + frameDurationMs
            self.updateActiveNotesForFrame(currentFrameEndMs)
            frameFilePaths.append("file '%s'" % self.createFrameComposition( frameNum ).resolve())
            currentFrameStartMs = currentFrameEndMs

        frameFilePathsFile = Path("%s/singleFrameFileList.txt" % self.tempDir.resolve())
        frameFilePathsFile.write_text(
            '\n'.join(frameFilePaths)
        )

        logging.info("finished %s in %s seconds\r" % ( 'create single frames', '{0:.3g}'.format(time.time() - startTime) ) )

        videoWithoutAudioFile = Path("%s/video-noaudio.mp4" % self.tempDir.resolve())

        cmd = [
            'ffmpeg', '-y', '-f', 'concat', '-r', str(self.framesPerSecond),
            '-safe', '0', '-i', self.escapeArg(frameFilePathsFile),
            '-pix_fmt', 'yuv420p',
            '-framerate', str(self.framesPerSecond),
            self.escapeArg(videoWithoutAudioFile)
        ]
        self.generalCmd(cmd, 'concat single frame pics to video')


        videoPath = Path("%s/%s.mp4" %( self.scriptPath.resolve(),  self.midiFile.name ) )
        if config.get("video", "addAudio") == "1":
            audioWav = Path("%s/audio.wav" % self.tempDir.resolve())
            audioMp3 = Path("%s/audio.mp3" % self.tempDir.resolve())
            midiFilePath = self.midiFile
            if self.midiFileCopy:
                midiFilePath = self.midiFileCopy
            cmd = [
                'fluidsynth', '-F', str(audioWav.resolve()),
                str(self.soundFont), str(midiFilePath.resolve())
            ]
            self.generalCmd(cmd, 'convert midi file to audio.wav')

            cmd = [
                'ffmpeg','-y','-i', self.escapeArg(audioWav),
                '-vn', '-ar', '44100', '-ac', '2', '-b:a', '192k',
                self.escapeArg(audioMp3)
            ]
            self.generalCmd(cmd, 'convert wav to mp3')

            cmd = [
                'ffmpeg', '-y', '-i', self.escapeArg(videoWithoutAudioFile),
                '-i', self.escapeArg(audioMp3), '-c', 'copy', '-map', '0:v:0', '-map', '1:a:0', '-shortest',
                self.escapeArg(videoPath)
            ]
            self.generalCmd(cmd, 'merge mp3 stream into video')
        else:
            os.rename(videoWithoutAudioFile.resolve(), videoPath.resolve())


    def getEventsUntilMs(self, microSecond):
        collectedEvents = []
        for event in self.notesToProcess:
            if event[0] > microSecond:
                break
            #print ( "ts:%f no:%s na:%s %s vel:%s" % ( event[0] , event[1].data[0] , noteNumberToNoteName(event[1].data[0]), event[1].__class__.__name__, event[1].data[1], ) )
            collectedEvents.append(event[1])
            self.notesToProcess.remove(event)

        return collectedEvents


    def updateActiveNotesForFrame(self, frameEndMicroSec):
        newEvents = self.getEventsUntilMs(frameEndMicroSec)
        for newEvent in newEvents:
            if (
                newEvent.__class__.__name__ == "NoteOffEvent" or
                # treat NoteOn with velocity=0 as NoteOff
                (newEvent.__class__.__name__ == "NoteOnEvent" and newEvent.data[1] == "0")
            ):
                self.openNotes.pop(newEvent.data[0], None)
                self.noteFadeOuts[str(newEvent.data[0])] = 1
                continue

            self.openNotes[newEvent.data[0]] = newEvent.data[0]
            self.noteFadeIns[str(newEvent.data[0])] = 1
            self.noteFadeOuts.pop( str(newEvent.data[0]), None)


    def createFrameComposition(self, frameNumber = 0):
        sortedOpenNotes = {k: self.openNotes[k] for k in sorted(self.openNotes)}
        compHash = "f"

        for noteNumber in range(self.piano.startNote, self.piano.endNote+1):
            offsetX = self.piano.getLeftOffsetForKeyPlacement(noteNumber)
            isHighlight = False
            highlightColor = ""
            if noteNumber in sortedOpenNotes:
                isHighlight = True
                highlightColor = self.piano.colorHighlight
                if str(noteNumber) in self.noteFadeIns:
                    highlightColor = self.getColorForFadeIn(noteNumber)
            if str(noteNumber) in self.noteFadeOuts:
                highlightColor = self.getColorForFadeOut(noteNumber)

            if highlightColor != "":
                sortedOpenNotes[noteNumber] = highlightColor
                compHash += str(noteNumber) + highlightColor + '-'

        # TODO: create shorter hash as filename to avoid possible filename length limit
        compPath = Path( '%s/%s.png'% (self.tempDirFrames.resolve(), compHash) )
        if(len(sortedOpenNotes) > 0):
            # separate directory for each first open note
            firstOpenNote = str(next(iter(sortedOpenNotes)))
            compPath = Path( '%s/%s/%s.png'% (self.tempDirFrames.resolve(),firstOpenNote, compHash) )

        # don't create already existing identical frame pic again
        if compPath.is_file():
            return compPath

        pathStrings = []
        for noteNumber in range(self.piano.startNote, self.piano.endNote+1):
            offsetX = self.piano.getLeftOffsetForKeyPlacement(noteNumber)
            highlightColor = ""
            if noteNumber in sortedOpenNotes:
                highlightColor = sortedOpenNotes[noteNumber]
            pathStrings.append( self.piano.getSvgPathForNoteNumber(noteNumber, offsetX, highlightColor) )

        svgString = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d">%s</svg>' % (
            self.videoWidth,
            self.videoHeight,
            '\n'.join(pathStrings)
        )
        svg2png( bytestring=svgString, write_to=self.escapeArg(compPath) )
        return compPath


    # TODO: does it make sense to limit fadeIn to NoteOff+NoteOn within very short time?
    def getColorForFadeIn(self, noteNumber):
        if self.noteFadeIn != '1':
            return self.piano.colorHighlight

        localFrameNum = self.noteFadeIns[str(noteNumber)]
        self.noteFadeIns[str(noteNumber)] += 1
        if localFrameNum < 4:
            return self.piano.darkenColor(self.piano.colorHighlight, 0.2)
        if localFrameNum < 5:
            return self.piano.darkenColor(self.piano.colorHighlight, 0.1)

        self.noteFadeIns.pop(str(noteNumber))
        return self.piano.colorHighlight

    # TODO: does it make sense to limit fadeOut to very short notes?
    def getColorForFadeOut(self, noteNumber):
        if self.noteFadeOut != '1':
            return ''

        localFrameNum = self.noteFadeOuts[str(noteNumber)]

        self.noteFadeOuts[str(noteNumber)] += 1
        # TODO based on chosen keycolor a "fade out" may be darken or lighten
        # we assume we have white and black keys and no inverted colors...
        multiplicator = 1 if self.piano.isWhiteKey(noteNumber) else -1
        if localFrameNum < 2:
            return self.piano.lightenColor(self.piano.colorHighlight, 0.4*multiplicator)
        if localFrameNum < 4:
            return self.piano.lightenColor(self.piano.colorHighlight, 0.5*multiplicator)
        if localFrameNum < 8:
            return self.piano.lightenColor(self.piano.colorHighlight, 0.6*multiplicator)
        if localFrameNum < 10:
            return self.piano.lightenColor(self.piano.colorHighlight, 0.8*multiplicator)

        self.noteFadeOuts.pop(str(noteNumber))
        return ""

    def generalCmd(self, cmdArgsList, description, readStdError = False, silent=False):
        if not silent:
            logging.info("starting %s" % description)
        logging.debug(' '.join(cmdArgsList))
        sys.stdout.flush()
        startTime = time.time()
        if readStdError:
            process = subprocess.Popen(cmdArgsList, stderr=subprocess.PIPE)
            processStdOut = process.stderr.read()
        else:
            process = subprocess.Popen(cmdArgsList, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            processStdOut = process.stdout.read()
        retcode = process.wait()
        if retcode != 0:
            print ( "ERROR: %s did not complete successfully (error code is %s)" % (description, retcode) )
            print (processStdOut.decode('utf-8'))

        if not silent:
            logging.info("finished %s in %s seconds\r" % ( description, '{0:.3g}'.format(time.time() - startTime) ) )
            sys.stdout.flush()
        return processStdOut.decode('utf-8')

    def escapeArg(self, item):
        if item.__class__.__name__ == 'PosixPath':
            item = str(item.resolve())

        return item.replace("'", "'\"'\"'")


    # thanks to https://github.com/Pomax/arduino-midi-recorder/blob/master/fix.py
    def fixTrackLengthBytes(self):
        if self.fixTrackLength != '1':
            # disabled by config
            return

        # make a copy of the file. (keep things non-destructive)
        self.midiFileCopy = Path(f"{self.tempDir}/{self.midiFile}.fixedlength.mid")
        copyfile(self.midiFile, self.midiFileCopy)
        file = open(self.midiFileCopy, "rb+")
        file_size = os.path.getsize(self.midiFileCopy)
        track_length = file_size - 22

        field_value = bytearray([
            (track_length & 0xFF000000) >> 24,
            (track_length & 0x00FF0000) >> 16,
            (track_length & 0x0000FF00) >> 8,
            (track_length & 0x000000FF),
        ])

        file.seek(18)
        file.write(field_value)
        file.close()
        logging.info(f"Updated {self.midiFileCopy} track length to {track_length}")

def main():
    global m2v, config
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-i',
        required=True,
        type=Path,
        help='specifies the input midi file'
    )

    args = parser.parse_args()

    scriptPath = Path(os.path.dirname(os.path.abspath(__file__)))

    config = configparser.ConfigParser(strict=False)
    configFiles = [ '%s/m2v.conf' % scriptPath.resolve() ]

    # optional gitignored local configuration
    localConfig = Path( '%s/m2v.local.conf' % scriptPath.resolve() )
    if localConfig.is_file():
        configFiles.append(localConfig.resolve())

    try:
        config.read(configFiles)
    except configparser.ParsingError as parsingError:
        print ( 'parsing error %s' % str(parsingError) )


    m2v = Midi2Video(scriptPath, config)
    m2v.midiFile = args.i

    m2v.createTempDir()
    m2v.fixTrackLengthBytes()
    # TODO given arguments have highest priority override conf values again...

    if validateConfig() != True:
        print ( "exiting due to config errors..." )
        sys.exit()

    m2v.createTempSubDirs()
    m2v.createVideo()

    # TODO parse debug conf for non removal of temp files
    #print (" removing temp files %s" % str(m2v.tempDir) )
    #rmtree(m2v.tempDir)

    print ( 'finished' )
    sys.exit()

def validateConfig():
    if not m2v.midiFile.is_file():
        msg = "input midifile \'%s\' does not exist" % m2v.midiFile.resolve()
        raise argparse.ArgumentTypeError(msg)

    startNote = config.get('piano', 'startNote')
    endNote = config.get('piano', 'endNote')

    if startNote == 'auto' or endNote == 'auto':
        m2v.prepareNoteEvents()

    if startNote == 'auto':
        m2v.piano.startNote = m2v.lowestFoundNoteNumber

    if endNote == 'auto':
        m2v.piano.endNote = m2v.highestFoundNoteNumber

    m2v.piano.startNote = int(m2v.piano.startNote)
    m2v.piano.endNote = int(m2v.piano.endNote)
    if not m2v.notesCollected:
        m2v.prepareNoteEvents()


    # ensure we have enclosed white keys
    if m2v.piano.isWhiteKey(m2v.piano.startNote) == False:
        m2v.piano.startNote -= 1
    if m2v.piano.isWhiteKey(m2v.piano.endNote) == False:
        m2v.piano.endNote += 1

    if m2v.piano.endNote <= m2v.piano.startNote:
        print( " quirks in piano key range (startNote/endNote). check config...")
        sys.exit()

    m2v.piano.calculateSvgDimensions(m2v.videoWidth, m2v.videoHeight)

    # TODO: check if ffmpeg is available
    # TODO: force video dimensions beeing dividable by 2
    # TODO: check if "fluidsynth" bin is available when addAudio=1
    # TODO: check if soundfont-path is valid when addAudio=1

    return True

if __name__ == '__main__':
    main()
