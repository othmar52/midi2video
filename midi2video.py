#!/bin/env python3
# -*- coding: utf-8 -*- 

# requirements
# pip install mydy
# ffmpeg


# limitiations
# tempo changes are not supported



# @see https://github.com/vishnubob/python-midi/pull/62/commits/9aa092e653684c871b9ee2293ee8e640bb1cab34
import argparse
import logging
import configparser
import mydy as midi
import sys
import math
import os
from pathlib import Path
from shutil import rmtree
from colorsys import rgb_to_hls, hls_to_rgb


class VirtualPiano(object):
    def __init__(self, config):
        self.keyFrom = config.get('piano', 'keyFrom', fallback='auto')
        self.keyTo = config.get('piano', 'keyTo', fallback='auto')
        self.colorWhiteKeys = config.get('piano', 'colorWhiteKeys', fallback='#FFFFFF')
        self.colorBlackKeys = config.get('piano', 'colorBlackKeys', fallback='#131313')
        self.colorHighlight = config.get('piano', 'colorHighlight', fallback='#DE4439')
        self.amountWhiteKeys = 0
        self.pianoWidth = 0
        self.pianoHeight = 0

        self.svgScaleX = 1
        self.svgScaleY = 1

        self.tempDir = None
        self.tempDirShapes = None
        self.tempDirHighlight = None
        self.tempDirFrames = None

        self.keySvgPaths = {}

    def calculateKeyWidth(self, videoWidth, videoHeight):
        self.pianoWidth = videoWidth
        self.pianoHeight = videoHeight
        self.amountWhiteKeys = self.countWhiteKeys(self.keyFrom, self.keyTo)

    def calculateSvgScales(self):
        # white keys in our path definitions has fixed dimensions of x:100 y:200
        realSvgWidth = self.amountWhiteKeys * 100
        realSvgHeight = 200
        self.svgScaleX = self.pianoWidth / realSvgWidth
        self.svgScaleY = self.pianoHeight / realSvgHeight


    # thanks to https://stackoverflow.com/questions/712679/convert-midi-note-numbers-to-name-and-octave#answer-54546263
    def noteNumberToNoteName(self, noteNumber, appendOctave=False):
        noteNumber -= 21
        # hmmmm do we really need this correction?
        noteNumber += 12
        notes = [ "A", "A#", "B", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#" ]
        octave = math.floor(noteNumber / 12) + 1
        noteName = notes[ noteNumber % 12 ]
        if appendOctave == False:
            return noteName
        return "%s%d" % (noteName, octave)

    def isWhiteKey(self, noteNumber):
        if self.noteNumberToNoteName(noteNumber) in ["A", "B", "C", "D", "E", "F", "G"]:
            return True
        return False

    def countWhiteKeys(self, keyFrom, keyTo):
        counter = 0
        for noteName in range(keyFrom, keyTo+1):
            if self.isWhiteKey(noteName):
                counter += 1

        return counter

    def getLeftOffsetForKeyPlacement(self, noteNumber):
        numWhiteKeys = self.countWhiteKeys(self.keyFrom, noteNumber)
        sumWhiteKeysWidth = (numWhiteKeys-1) * 100
        if self.isWhiteKey(noteNumber):
            return sumWhiteKeysWidth 

        noteName = self.noteNumberToNoteName(noteNumber)
        #print ( "%s %s " % (noteName,  sumWhiteKeysWidth) )

        if noteName == 'A#':
            return sumWhiteKeysWidth + 29.1666666666 + 56.25
        if noteName == 'C#':
            return sumWhiteKeysWidth + 61.1111111111
        if noteName == 'D#':
            return sumWhiteKeysWidth + 19.4444444444 + 61.1111111111
        if noteName == 'F#':
            return sumWhiteKeysWidth + 56.25
        if noteName == 'G#':
            return sumWhiteKeysWidth + 14.5833333333 + 56.25

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

    def getPathChunkForNoteName(self, noteName, noteNumber):

        if str(noteNumber) in self.keySvgPaths:
            #print( "found %s: %s" % (str(noteNumber), self.keySvgPaths[str(noteNumber)]) )
            #sys.exit()
            return self.keySvgPaths[str(noteNumber)]

        whiteW = 100
        whiteH = 200
        blackH = 120
        blackDiff = whiteH - blackH

        # dimensions X for narrow parts of white keys with sum 100
        dimX = {
            'C': [ 61.1111111111, 38.8888888889 ],
            'D': [ 19.4444444444, 61.1111111111, 19.4444444445 ],
            'E': [ 38.8888888889, 61.1111111111 ],

            'F': [ 56.25,         43.75 ],
            'G': [ 14.5833333333, 56.25, 29.1666666667 ],
            'A': [ 29.1666666666, 56.25, 14.5833333333 ],
            'B': [ 43.75,         56.25]
        }

        if noteName in ["C#", "D#", "F#", "G#", "A#"]:
            pathChunk = "%d h 58.3333333333 V 0 h -58.3333333333" % (blackH)
        if noteName == "C":
            pathChunk = "200 h 100 v -%s h -%s V 0 h -%s" % (blackDiff, dimX['C'][1], dimX['C'][0])
            if noteNumber == self.keyTo:
                pathChunk = "200 h 100 V 0 h -100"
        if noteName == "D":
            pathChunk = "200 h 100 v -%s h -%s V 0 h -%s v %s h -%s" % (blackDiff, dimX['D'][2], dimX['D'][1], blackH, dimX['D'][0])
            if noteNumber == self.keyFrom:
                pathChunk = "200 h 100 v -%s h -%s V 0 h -%s" % (blackDiff, dimX['D'][2], dimX['D'][1] + dimX['D'][0])
            if noteNumber == self.keyTo:
                pathChunk = "200 h 100 V 0 h -%s v %s h -%s" % (dimX['D'][2] + dimX['D'][1], blackH, dimX['D'][0])
        if noteName == "E":
            pathChunk = "200 h 100 V 0 h -%s v %s h -%s" % (dimX['E'][1], blackH, dimX['E'][0])
            if noteNumber == self.keyFrom:
                pathChunk = "200 h 100 V 0 h -100"
        if noteName == "F":
            pathChunk = "200 h 100 v -%s h -%s V 0 h -%s" % (blackDiff, dimX['F'][1], dimX['F'][0])
            if noteNumber == self.keyTo:
                pathChunk = "200 h 100 V 0 h -100"
        if noteName == "G":
            pathChunk = "200 h 100 v -%s h -%s V 0 h -%s V %s h -%s" % (blackDiff, dimX['G'][2], dimX['G'][1], blackH, dimX['G'][0])
            if noteNumber == self.keyFrom:
                pathChunk = "200 h 100 v -%s h -%s V 0 h -%s" % (blackDiff, dimX['G'][2], dimX['G'][1] + dimX['G'][0])
            if noteNumber == self.keyTo:
                pathChunk = "200 h 100 V 0 h -%s v %s h -%s" % (dimX['G'][2] + dimX['G'][1], blackH, dimX['G'][0])
        if noteName == "A":
            pathChunk = noteNumber, "200 h 100 v -%s h -%s V 0 h -%s V %s h -%s" % (blackDiff, dimX['A'][2], dimX['A'][1], blackH, dimX['A'][0])
            if noteNumber == self.keyFrom:
                pathChunk = noteNumber, "200 h 100 v -%s h -%s V 0 h -%s" % (blackDiff, dimX['A'][2], dimX['A'][1] + dimX['A'][0])
            if noteNumber == self.keyTo:
                pathChunk = "200 h 100 V 0 h -%s v %s h -%s" % (dimX['A'][2] + dimX['A'][1], blackH, dimX['A'][0])
        if noteName == "B":
            pathChunk = "200 h 100 V 0 h -%s v %s h -%s" % (dimX['B'][1], blackH, dimX['B'][0])
            if noteNumber == self.keyFrom:
                pathChunk = "200 h 100 V 0 h -100"

        self.keySvgPaths[str(noteNumber)] = pathChunk
        return pathChunk


    def getSvgPathForNoteNumber(self, noteNumber, offsetX, highlight=False):

        colorToUse = self.colorBlackKeys
        outlineColor = "black"
        if self.isWhiteKey(noteNumber):
            colorToUse = self.colorWhiteKeys

        if highlight:
            colorToUse = self.darkenColor(self.colorHighlight)
            outlineColor = "#6e160f"

        noteLetter = self.noteNumberToNoteName(noteNumber)

        pathString = '<path fill="%s" stroke="%s" d="M%s %s Z"  transform="scale(%s, %s)" />' % (
            colorToUse,
            outlineColor,
            offsetX,
            self.getPathChunkForNoteName(noteLetter, noteNumber),
            self.svgScaleX,
            self.svgScaleY
        )

        return pathString





class Midi2Video(object):
    def __init__(self, scriptPath, config):
        self.scriptPath = scriptPath
        self.midiFile = None
        self.notesToProcess = []
        self.openNotes = {}
        self.piano = VirtualPiano(config)
        self.lowestFoundNoteNumber = 200
        self.highestFoundNoteNumber = 0
        self.notesCollected = False
        self.videoWidth = int(config.get('video', 'width', fallback=800))
        self.videoHeight = int(config.get('video', 'height', fallback=200))
        self.framesPerSecond = int(config.get('video', 'frameRate', fallback=25))

        self.videoDurationMs = 0
        self.videoTotalFrames = 0

        self.tempDir = None
        self.tempDirShapes = None
        self.tempDirHighlight = None
        self.tempDirFrames = None

    # we need to add an absolute microtimestamp to each note event
    def prepareNoteEvents(self):
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
                if event.__class__.__name__ not in ["NoteOnEvent", "NoteOffEvent"]:
                    continue

                t += event.tick
                eventMicroSecond = t * mpt
                if eventMicroSecond > self.videoDurationMs:
                    self.videoDurationMs = eventMicroSecond

                # skip note events that are outside our keyboard range
                if not self.piano.keyFrom == "auto" and event.data[0] < int(self.piano.keyFrom):
                    continue

                if not self.piano.keyTo == "auto" and event.data[0] > int(self.piano.keyTo):
                    continue

                if event.data[0] < self.lowestFoundNoteNumber:
                    self.lowestFoundNoteNumber = event.data[0]

                if event.data[0] > self.highestFoundNoteNumber:
                    self.highestFoundNoteNumber = event.data[0]
                self.notesToProcess.append(tuple((eventMicroSecond, event)))

                #print ( eventMicroSecond, t, "Note", e.data[0], "on" if e.data[1] > 0 else "off" )

        self.videoTotalFrames = int(math.ceil(self.videoDurationMs/1000000*self.framesPerSecond))
        self.notesCollected = True

    def createTempDirs(self):
        self.tempDir = Path('%s/temp-%s' % (self.scriptPath.resolve(), self.midiFile.name))
        if self.tempDir.is_dir():
            rmtree(self.tempDir.resolve())

        self.tempDir.mkdir(parents=True, exist_ok=True)
        self.tempDirShapes = Path('%s/shapes' % (self.tempDir.resolve() ))
        self.tempDirShapes.mkdir(parents=True, exist_ok=True)
        self.tempDirHighlight = Path('%s/highlight' % (self.tempDir.resolve() ))
        self.tempDirHighlight.mkdir(parents=True, exist_ok=True)
        self.tempDirFrames = Path('%s/frames' % (self.tempDir.resolve() ))
        self.tempDirFrames.mkdir(parents=True, exist_ok=True)

        self.piano.tempDir = self.tempDir
        self.piano.tempDirShapes = self.tempDirShapes
        self.piano.tempDirHighlight = self.tempDirHighlight
        self.piano.tempDirFrames = self.tempDirFrames

    def createVideo(self):

        frameDurationMs = 1000000/self.framesPerSecond
        currentFrameStartMs = 0

        frameFilePaths = []
        for frameNum in range(1,self.videoTotalFrames+1):
            currentFrameEndMs = currentFrameStartMs + frameDurationMs
            self.updateActiveNotesForFrame(currentFrameEndMs)
            frameFilePaths.append("file '%s'" % self.createFrameComposition().resolve())
            currentFrameStartMs = currentFrameEndMs

        frameFilePathsFile = Path("%s/singleFrameFileList.txt" % self.tempDir.resolve())
        frameFilePathsFile.write_text(
            '\n'.join(frameFilePaths)
        )

        videoWithoutAudioFile = Path("%s/video-noaudio.mp4" % self.tempDir.resolve())
        os.system("ffmpeg -y -f concat -r %d -safe 0 -i %s -framerate %d %s" % (
            self.framesPerSecond,
            frameFilePathsFile.resolve(),
            self.framesPerSecond,
            videoWithoutAudioFile.resolve())
        )
        videoPath = Path("%s/%s.mp4" %( self.scriptPath.resolve(),  self.midiFile.name ) )
        if config.get("video", "addAudio") == "1":
            audioWav = Path("%s/audio.wav" % self.tempDir.resolve())
            audioMp3 = Path("%s/audio.mp3" % self.tempDir.resolve())

            os.system("fluidsynth -F %s /usr/share/soundfonts/jRhodes3.sf2 %s" % (audioWav.resolve(), self.midiFile.resolve()) )
            os.system("ffmpeg -y -i %s -vn -ar 44100 -ac 2 -b:a 192k %s" % (audioWav.resolve(), audioMp3.resolve()) )
            os.system("ffmpeg -y -i %s -i %s -c copy -map 0:v:0 -map 1:a:0 %s" % (videoWithoutAudioFile.resolve(),audioMp3.resolve(),videoPath.resolve()) )
        else:
            os.rename(videoWithoutAudioFile.resolve(), videoPath.resolve())


    def getEventsUntilMs(self, microSecond):
        collectedEvents = []
        for event in self.notesToProcess:
            if event[0] > microSecond:
                break
            #print ( "ts:%f no:%s na:%s %s vel:%s" % ( event[0] , event[1].data[0] , noteNumberToNoteName(event[1].data[0]), event[1].__class__.__name__, event[1].data[1], ) )
            collectedEvents.append(event[1])

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
                continue

            self.openNotes[newEvent.data[0]] = newEvent.data[0]


    def createFrameComposition(self):
        sortedOpenNotes = {k: self.openNotes[k] for k in sorted(self.openNotes)}
        compHash = '-'.join(map(str, list(sortedOpenNotes.keys())))
        if compHash == "":
            compHash = "blank"

        compPath = Path( '%s/%s.png'% (self.tempDirFrames.resolve(), compHash) )
        if compPath.is_file():
            print ('found comp %s' % compHash)
            return compPath

        

        pathStrings = []
        for noteNumber in range(self.piano.keyFrom, self.piano.keyTo+1):
            #print (noteNumber)
            offsetX = self.piano.getLeftOffsetForKeyPlacement(noteNumber)
            isHighlight = False
            if noteNumber in sortedOpenNotes:
                isHighlight = True
            pathStrings.append( self.piano.getSvgPathForNoteNumber(noteNumber, offsetX, isHighlight) )


        compPathSvg = Path( '%s/%s.svg'% (self.tempDirFrames.resolve(), compHash) )
        compPathSvg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">%s</svg>' % '\n'.join(pathStrings)
        )
        # convert it to png
        os.system("convert %s %s" % (compPathSvg.resolve(), compPath.resolve()) )
        os.remove(compPathSvg.resolve())
        print( "creating new comp for %s" % compHash )
        return compPath

def main():
    global m2v, config
    logging.basicConfig(level=logging.WARNING)

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

    # TODO given arguments have highest priority override conf values again...

    if validateConfig() != True:
        #print ( colored ( "exiting due to config errors...", "red" ) )
        sys.exit()

    m2v.createTempDirs()

    m2v.createVideo()

    # TODO parse debug conf for non removal of temp files
    #print (" removing temp files %s" % str(m2v.tempDir) )
    #rmtree(m2v.tempDir)

    print ( 'EXIT in __main__' )
    sys.exit()



def validateConfig():
    if not m2v.midiFile.is_file():
        msg = "input midifile \'%s\' does not exist" % m2v.midiFile.resolve()
        raise argparse.ArgumentTypeError(msg)

    keyFrom = config.get('piano', 'keyFrom')
    keyTo = config.get('piano', 'keyTo')

    if keyFrom == 'auto' or keyTo == 'auto':
        m2v.prepareNoteEvents()

    if keyFrom == 'auto':
        m2v.piano.keyFrom = m2v.lowestFoundNoteNumber

    if keyTo == 'auto':
        m2v.piano.keyTo = m2v.highestFoundNoteNumber

    m2v.piano.keyFrom = int(m2v.piano.keyFrom)
    m2v.piano.keyTo = int(m2v.piano.keyTo)
    if not m2v.notesCollected:
        m2v.prepareNoteEvents()


    # ensure we have enclosed white keys
    if m2v.piano.isWhiteKey(m2v.piano.keyFrom) == False:
        m2v.piano.keyFrom -= 1
    if m2v.piano.isWhiteKey(m2v.piano.keyTo) == False:
        m2v.piano.keyTo += 1

    if m2v.piano.keyTo <= m2v.piano.keyFrom:
        print( " quirks in piano key range (keyFrom/keyTo). check config...")
        sys.exit()

    m2v.piano.calculateKeyWidth(m2v.videoWidth, m2v.videoHeight)
    m2v.piano.calculateSvgScales()


    return True

if __name__ == '__main__':
    main()
