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
from PIL import Image, ImageDraw
from pathlib import Path
from shutil import rmtree


class VirtualPiano(object):
    def __init__(self, config):
        self.keyFrom = config.get('piano', 'keyFrom', fallback='auto')
        self.keyTo = config.get('piano', 'keyTo', fallback='auto')
        self.colorWhiteKeys = config.get('piano', 'colorWhiteKeys', fallback='#FFFFFF')
        self.colorBlackKeys = config.get('piano', 'colorBlackKeys', fallback='#000000')
        self.colorHighlight = config.get('piano', 'colorHighlight', fallback='#FF0000')
        self.blackHeightRatio = float(config.get('piano', 'blackHeightRatio', fallback=0.6))
        self.blackWidthRatio = float(config.get('piano', 'blackWidthRatio', fallback=0.6))
        self.blackOffsetA = float(config.get('piano', 'blackOffset.A', fallback=0.8))
        self.blackOffsetC = float(config.get('piano', 'blackOffset.C', fallback=0.6))
        self.blackOffsetD = float(config.get('piano', 'blackOffset.D', fallback=0.8))
        self.blackOffsetF = float(config.get('piano', 'blackOffset.F', fallback=0.6))
        self.blackOffsetG = float(config.get('piano', 'blackOffset.G', fallback=0.7))
        self.keyWidthWhite = 0
        self.keyHeightWhite = 0
        self.keyWidthBlack = 0
        self.keyHeightBlack = 0
        self.amountWhiteKeys = 0
        self.pianoWidth = 0
        self.pianoHeight = 0

        self.tempDir = None
        self.tempDirShapes = None
        self.tempDirHighlight = None
        self.tempDirFrames = None

    def calculateKeyWidth(self, videoWidth, videoHeight):
        self.pianoWidth = videoWidth
        self.pianoHeight = videoHeight
        self.amountWhiteKeys = self.countWhiteKeys(self.keyFrom, self.keyTo)
        self.keyWidthWhite = self.pianoWidth/self.amountWhiteKeys
        self.keyHeightWhite = self.pianoHeight
        self.keyWidthBlack = self.keyWidthWhite * self.blackWidthRatio
        self.keyHeightBlack = self.keyHeightWhite * self.blackHeightRatio
        

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

    def drawFullPiano(self, targetPath):
        composition = Image.new('RGB', (self.pianoWidth, self.pianoHeight), (0, 0, 0))
        for noteNumber in range(self.keyFrom, self.keyTo+1):
            img = Image.new('RGBA', (self.pianoWidth, self.pianoHeight), (255, 0, 0, 0))
            shapeImg = Image.open(self.getShapeForNoteNumber(noteNumber).resolve())
            offsetX = round(self.getLeftOffsetForKeyPlacement(noteNumber))
            composition.paste(shapeImg, (offsetX, 0), shapeImg)
            composition.paste(img, (0, 0), img)
        composition.save(targetPath.resolve(), 'JPEG')
        return targetPath.resolve()


    def getLeftOffsetForKeyPlacement(self, noteNumber):
        numWhiteKeys = self.countWhiteKeys(self.keyFrom, noteNumber)
        sumWhiteKeysWidth = (numWhiteKeys-1) * self.keyWidthWhite
        if self.isWhiteKey(noteNumber):
            return sumWhiteKeysWidth 

        noteName = self.noteNumberToNoteName(noteNumber)
        print ( "%s %s " % (noteName,  sumWhiteKeysWidth) )

        if noteName == 'A#':
            return sumWhiteKeysWidth + self.keyWidthWhite*self.blackOffsetA
        if noteName == 'C#':
            return sumWhiteKeysWidth + self.keyWidthWhite*self.blackOffsetC
        if noteName == 'D#':
            return sumWhiteKeysWidth + self.keyWidthWhite*self.blackOffsetD
        if noteName == 'F#':
            return sumWhiteKeysWidth + self.keyWidthWhite*self.blackOffsetF
        if noteName == 'G#':
            return sumWhiteKeysWidth + self.keyWidthWhite*self.blackOffsetG

    def getPointsForKeyShape(self, noteNumber, xLeft=None, xRight=None, isFirst="", isLast=""):
        noteName = self.noteNumberToNoteName(noteNumber)

        removeSectionLeft = True
        if noteName in ["C", "F"]:
            removeSectionLeft = False

        removeSectionRight = True
        if noteName in ["E", "B"]:
            removeSectionRight = False


        # in case we start with a white key that is not F or C
        # do not remove section for left black key
        if not isFirst == "" and not noteName in ["C", "F"]:
            xLeft = 0
            removeSectionLeft = False

        # in case we finish with a white key that is not E or B
        # do not remove section for right black key
        if not isLast == "" and not noteName in ["E", "B"]:
            xRight = 0
            removeSectionRight = False

        # all white keys has same bottom line
        points = [
            (0, self.keyHeightWhite),           # left bottom
            (self.keyWidthWhite, self.keyHeightWhite)   # right bottom
        ]

        if removeSectionRight == False:
            points.append((self.keyWidthWhite, 0))            # up till we reach the top
            points.append((xLeft, 0))                 # left until we reach right side left black key
        else:
            points.append((self.keyWidthWhite, self.keyHeightBlack))  # up till we reach bottom line of right black key
            points.append((xRight, self.keyHeightBlack))      # left until we reach left side of right black key
            points.append((xRight, 0))                # up until we reach the top

        if removeSectionLeft == False:
            points.append((0,0))                      # left until we reach right side of left white key
        else:
            points.append((xLeft,0))                  # left until we reach right side of left black key
            points.append((xLeft, self.keyHeightBlack))       # down until we reach the bottom of left black key
            points.append((0, self.keyHeightBlack))           # left until we reach the right side of left white key
        
        points.append((0, self.keyHeightWhite))               # back to startingpoint
        return points

    def getShapeForNoteNumber(self, noteNumber, highlight=False):
        black = self.colorBlackKeys
        white = self.colorWhiteKeys
        color = self.colorHighlight
        filename = "shape-"
        outlineColor = "#acacac"
        isFirstSuffix = ""
        isLastSuffix = ""

        if highlight:
            black = color
            white = color
            filename = "shape-hl-"
            outlineColor = "#6e160f"

        if self.keyFrom == noteNumber:
            isFirstSuffix = "-first"

        if self.keyTo == noteNumber:
            isLastSuffix = "-last"

        noteLetter = self.noteNumberToNoteName(noteNumber)
        noteLetterShapeFile = Path( '%s/%s%s%s%s.png'% (self.tempDirShapes.resolve(), filename, noteLetter, isFirstSuffix, isLastSuffix) )

        if noteLetterShapeFile.is_file():
            return noteLetterShapeFile

        shapeWidth = self.keyWidthWhite
        shapeHeight = self.keyHeightWhite
        fill = white
        if not self.isWhiteKey(noteNumber):
            shapeWidth = self.keyWidthBlack
            shapeHeight = self.keyHeightBlack
            points = [
                (0, shapeHeight),           # left bottom
                (shapeWidth, shapeHeight),  # right bottom
                (shapeWidth, 0),            # right top
                (0, 0),                     # left top
                (0, shapeHeight)            # back to starting point (left bottom)
            ]
            fill = black

        shapeImg = Image.new('RGBA', (round(shapeWidth), round(shapeHeight)), (255, 0, 0, 0))
        draw = ImageDraw.Draw(shapeImg)

        xLeft = 0
        xRight = 0
        if noteLetter in ["C"]:
            xRight = self.keyWidthWhite*self.blackOffsetC
            points = self.getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)
        elif noteLetter in ["D"]:
            xLeft = self.keyWidthBlack - ( self.keyWidthWhite - (self.keyWidthWhite*self.blackOffsetC) )
            xRight = self.keyWidthWhite*self.blackOffsetD
            points = self.getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)
        elif noteLetter in ["E"]:
            xLeft = self.keyWidthBlack - ( self.keyWidthWhite - (self.keyWidthWhite*self.blackOffsetD) )
            points = self.getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)
        elif noteLetter in ["F"]:
            xRight = self.keyWidthWhite*self.blackOffsetF
            points = self.getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)
        elif noteLetter in ["G"]:
            xLeft = self.keyWidthBlack - ( self.keyWidthWhite - (self.keyWidthWhite*self.blackOffsetF) )
            xRight = self.keyWidthWhite*self.blackOffsetG
            points = self.getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)
        elif noteLetter in ["A"]:
            xLeft = self.keyWidthBlack - ( self.keyWidthWhite - (self.keyWidthWhite*self.blackOffsetG) )
            xRight = self.keyWidthWhite*self.blackOffsetA
            points = self.getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)
        elif noteLetter in ["B"]:
            xLeft = self.keyWidthBlack - ( self.keyWidthWhite - (self.keyWidthWhite*self.blackOffsetA) )
            points = self.getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)

        draw.polygon(points, fill=fill, outline=outlineColor)

        shapeImg.save(noteLetterShapeFile.resolve(), 'PNG')
        return noteLetterShapeFile

















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
        baseImgPath = Path("%s/basePiano,jpg" % self.tempDir.resolve())
        baseImg = Image.open(self.piano.drawFullPiano(baseImgPath))

        frameDurationMs = 1000000/self.framesPerSecond
        currentFrameStartMs = 0

        frameFilePaths = []
        for frameNum in range(1,self.videoTotalFrames+1):
            currentFrameEndMs = currentFrameStartMs + frameDurationMs
            self.updateActiveNotesForFrame(currentFrameEndMs)
            frameFilePaths.append("file '%s'" % self.createFrameComposition(baseImg).resolve())
            currentFrameStartMs = currentFrameEndMs

        frameFilePathsFile = Path("%s/singleFrameFileList.txt" % self.tempDir.resolve())
        frameFilePathsFile.write_text(
            '\n'.join(frameFilePaths)
        )

        videoWithoutAudioFile = Path("%s/video-noaudio.mp4" % self.tempDir.resolve())
        os.system("ffmpeg -y -f concat -safe 0 -i %s -framerate %d %s" % (frameFilePathsFile.resolve(), self.framesPerSecond, videoWithoutAudioFile.resolve()) )
        videoPath = Path("%s/%s.mp4" %( self.scriptPath.resolve(),  self.midiFile.name ) )
        if config.get("video", "addAudio") == "1":
            audioWav = Path("%s/audio.wav" % self.tempDir.resolve())
            audioMp3 = Path("%s/audio.mp3" % self.tempDir.resolve())

            os.system("fluidsynth -F %s /usr/share/soundfonts/FluidR3_GM.sf2 %s" % (audioWav.resolve(), self.midiFile.resolve()) )
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


    def createFrameComposition(self, baseImg):
        sortedOpenNotes = {k: self.openNotes[k] for k in sorted(self.openNotes)}
        compHash = '-'.join(map(str, list(sortedOpenNotes.keys())))
        if compHash == "":
            compHash = "blank"

        compPath = Path( '%s/%s.jpg'% (self.tempDirFrames.resolve(), compHash) )
        if compPath.is_file():
            print ('found comp %s' % compHash)
            return compPath

        composition = Image.new('RGB', (self.videoWidth, self.videoHeight), (0, 0, 0))
        composition.paste(baseImg, (0, 0))

        for noteNumber in sortedOpenNotes:
            singleNotePath = Path( '%s/%s.png'% (self.tempDirHighlight.resolve(), noteNumber) )
            if not singleNotePath.is_file():
                singleNoteOverlay = Image.new('RGBA', (self.videoWidth, self.videoHeight), (255, 0, 0, 0))
                shapeImg = Image.open(self.piano.getShapeForNoteNumber(noteNumber, highlight=True).resolve())
                offsetX = round(self.piano.getLeftOffsetForKeyPlacement(noteNumber))
                singleNoteOverlay.paste(shapeImg, (offsetX, 0))
                singleNoteOverlay.save(singleNotePath.resolve(), 'PNG')
                print( "creating new frame overlay for note %s" % noteNumber )
            singleNoteOverlay = Image.open(singleNotePath.resolve())
            composition.paste(singleNoteOverlay, (0, 0), singleNoteOverlay)

        composition.save(compPath.resolve(), 'JPEG')
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
        print ( colored ( "exiting due to config errors...", "red" ) )
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


    return True

if __name__ == '__main__':
    main()
