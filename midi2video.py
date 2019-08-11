#!/bin/env python3
# -*- coding: utf-8 -*- 

# requirements
# pip install mydy
# ffmpeg


# limitiations
# tempo changes are not supported



# @see https://github.com/vishnubob/python-midi/pull/62/commits/9aa092e653684c871b9ee2293ee8e640bb1cab34
import mydy as midi
import sys
import math
import os
from PIL import Image, ImageDraw
from pathlib import Path


class VirtualPiano(object):
    def __init__(self, pathObj):
        self.path = pathObj
        self.notesToProcess = []
        self.openNotes = {}

class Midi2Video(object):
    def __init__(self, pathObj):
        self.path = pathObj
        self.notesToProcess = []
        self.openNotes = {}


notesToProcess = []

openNotes = {}

# thanks to https://stackoverflow.com/questions/712679/convert-midi-note-numbers-to-name-and-octave#answer-54546263
def noteNumberToNoteName(noteNumber, appendOctave=False):
    noteNumber -= 21
    # hmmmm do we really need this correction?
    noteNumber += 12
    notes = [ "A", "A#", "B", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#" ]
    octave = math.floor(noteNumber / 12) + 1
    noteName = notes[ noteNumber % 12 ]
    if appendOctave == False:
        return noteName
    return "%s%d" % (noteName, octave)

def isWhiteKey(noteNumber):
    if noteNumberToNoteName(noteNumber) in ["A", "B", "C", "D", "E", "F", "G"]:
        return True
    return False

def countWhiteKeys(keyFrom, keyTo):
    counter = 0
    for noteName in range(keyFrom, keyTo+1):
        if isWhiteKey(noteName):
            counter += 1

    return counter

#midiFile = "lukas.mid"
#midiFile = "lesson05.mid"
#midiFile = "test.mid"
#midiFile = "mary.mid"
midiFile = "example.mid"

tempDir = Path('temp-%s' % (midiFile))
tempDir.mkdir(parents=True, exist_ok=True)

tempDirShapes = Path('temp-%s/shapes' % (midiFile))
tempDirShapes.mkdir(parents=True, exist_ok=True)
tempDirHighlight = Path('temp-%s/highlight' % (midiFile))
tempDirHighlight.mkdir(parents=True, exist_ok=True)
tempDirFrames = Path('temp-%s/frames' % (midiFile))
tempDirFrames.mkdir(parents=True, exist_ok=True)


keyFrom = 21
keyTo = 107

keyFrom = 48
keyTo = 69

# ensure we have enclosed white keys
if isWhiteKey(keyFrom) == False:
    keyFrom -= 1
if isWhiteKey(keyTo) == False:
    keyTo += 1

amountWhiteKeys = countWhiteKeys(keyFrom, keyTo)
frameWidth = 1754
frameHeight = 300
framesPerSecond = 25
whiteWidth = frameWidth/(amountWhiteKeys)
blackHeight = frameHeight*0.6
blackWidth = whiteWidth*0.6

# offset to the right hand side black Key
blackOffsetA = 0.8
blackOffsetC = 0.6
blackOffsetD = 0.8
blackOffsetF = 0.6
blackOffsetG = 0.7





pattern = midi.FileIO.read_midifile(midiFile)

#print ( pattern )
#sys.exit()

tempo = 50000        # default: 120 BPM
ticksPerBeat = pattern.resolution
lastEventTick = 0
microseconds = 0

mpt = tempo / ticksPerBeat

trackDurationMs = 0

# https://stackoverflow.com/questions/34166367/how-to-correctly-convert-midi-ticks-to-milliseconds#answer-34174936
for track in pattern:
    t = 0
    #track.make_ticks_abs()
    for e in track:

        if e.__class__.__name__ == "SetTempoEvent":
            tempo = e.mpqn
            mpt = tempo / ticksPerBeat

        deltaTicks = e.tick - lastEventTick
        lastEventTick = e.tick
        deltaMicroseconds = tempo * deltaTicks / ticksPerBeat
        microseconds += deltaMicroseconds
        if e.__class__.__name__ not in ["NoteOnEvent", "NoteOffEvent"]:
            continue

        t += e.tick
        eventMicroSecond = t * mpt
        if eventMicroSecond > trackDurationMs:
            trackDurationMs = eventMicroSecond

        # skip note events that are outside our keyboard range
        if e.data[0] < keyFrom:
            continue
        if e.data[0] > keyTo:
            continue

        notesToProcess.append(tuple((eventMicroSecond, e)))

        #print ( eventMicroSecond, t, "Note", e.data[0], "on" if e.data[1] > 0 else "off" )





totalFrames = int(math.ceil(trackDurationMs/1000000*framesPerSecond))
#print (totalFrames)

#print (pattern)
#print (notesToProcess)

def getEventsUntilMs(microSecond):
    collectedEvents = []
    for event in notesToProcess:
        if event[0] > microSecond:
            break
        #print ( "ts:%f no:%s na:%s %s vel:%s" % ( event[0] , event[1].data[0] , noteNumberToNoteName(event[1].data[0]), event[1].__class__.__name__, event[1].data[1], ) )
        collectedEvents.append(event[1])

    return collectedEvents


def updateActiveNotesForFrame(frameEndMicroSec):
    newEvents = getEventsUntilMs(currentFrameEndMs)
    for newEvent in newEvents:
        if (
            newEvent.__class__.__name__ == "NoteOffEvent" or
            # treat NoteOn with velocity=0 as NoteOff
            (newEvent.__class__.__name__ == "NoteOnEvent" and newEvent.data[1] == "0")
        ):
            openNotes.pop(newEvent.data[0], None)
            continue

        openNotes[newEvent.data[0]] = newEvent.data[0]

def drawFullKeyboard():
    composition = Image.new('RGB', (frameWidth, frameHeight), (0, 0, 0))
    for noteNumber in range(keyFrom, keyTo+1):
        img = Image.new('RGBA', (frameWidth, frameHeight), (255, 0, 0, 0))
        shapeImg = Image.open(getShapeForNoteNumber(noteNumber).resolve())
        offsetX = round(getLeftOffsetForKeyPlacement(noteNumber))
        composition.paste(shapeImg, (offsetX, 0), shapeImg)
        composition.paste(img, (0, 0), img)



    composition.save('99-base.jpg', 'JPEG')
    #sys.exit()
    return '99-base.jpg'



def getLeftOffsetForKeyPlacement(noteNumber):
    numWhiteKeys = countWhiteKeys(keyFrom, noteNumber)
    sumWhiteKeysWidth = (numWhiteKeys-1) * whiteWidth
    if isWhiteKey(noteNumber):
        return sumWhiteKeysWidth 

    noteName = noteNumberToNoteName(noteNumber)
    print ( "%s %s " % (noteName,  sumWhiteKeysWidth) )

    if noteName == 'A#':
        return sumWhiteKeysWidth + whiteWidth*blackOffsetA
    if noteName == 'C#':
        return sumWhiteKeysWidth + whiteWidth*blackOffsetC
    if noteName == 'D#':
        return sumWhiteKeysWidth + whiteWidth*blackOffsetD
    if noteName == 'F#':
        return sumWhiteKeysWidth + whiteWidth*blackOffsetF
    if noteName == 'G#':
        return sumWhiteKeysWidth + whiteWidth*blackOffsetG

def getPointsForKeyShape(noteNumber, xLeft=None, xRight=None, isFirst="", isLast=""):
    noteName = noteNumberToNoteName(noteNumber)

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
        (0, frameHeight),           # left bottom
        (whiteWidth, frameHeight)   # right bottom
    ]

    if removeSectionRight == False:
        points.append((whiteWidth, 0))            # up till we reach the top
        points.append((xLeft, 0))                 # left until we reach right side left black key
    else:
        points.append((whiteWidth, blackHeight))  # up till we reach bottom line of right black key
        points.append((xRight, blackHeight))      # left until we reach left side of right black key
        points.append((xRight, 0))                # up until we reach the top

    if removeSectionLeft == False:
        points.append((0,0))                      # left until we reach right side of left white key
    else:
        points.append((xLeft,0))                  # left until we reach right side of left black key
        points.append((xLeft, blackHeight))       # down until we reach the bottom of left black key
        points.append((0, blackHeight))           # left until we reach the right side of left white key
    
    points.append((0, frameHeight))               # back to startingpoint
    return points

def getShapeForNoteNumber(noteNumber, highlight=False):
    black = (0,0,0)
    white = (255,255,255)
    color = (255, 0, 0)
    filename = "shape-"
    outlineColor = "#acacac"
    isFirstSuffix = ""
    isLastSuffix = ""

    if highlight:
        black = color
        white = color
        filename = "shape-hl-"
        outlineColor = "#6e160f"

    if keyFrom == noteNumber:
        isFirstSuffix = "-first"

    if keyTo == noteNumber:
        isLastSuffix = "-last"

    noteLetter = noteNumberToNoteName(noteNumber)
    noteLetterShapeFile = Path( '%s/%s%s%s%s.png'% (tempDirShapes.resolve(), filename, noteLetter, isFirstSuffix, isLastSuffix) )

    if noteLetterShapeFile.is_file():
        return noteLetterShapeFile

    shapeWidth = whiteWidth
    shapeHeight = frameHeight
    fill = white
    if not isWhiteKey(noteNumber):
        shapeWidth = blackWidth
        shapeHeight = blackHeight
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
        xRight = whiteWidth*blackOffsetC
        points = getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)
    elif noteLetter in ["D"]:
        xLeft = blackWidth - ( whiteWidth - (whiteWidth*blackOffsetC) )
        xRight = whiteWidth*blackOffsetD
        points = getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)
    elif noteLetter in ["E"]:
        xLeft = blackWidth - ( whiteWidth - (whiteWidth*blackOffsetD) )
        points = getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)
    elif noteLetter in ["F"]:
        xRight = whiteWidth*blackOffsetF
        points = getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)
    elif noteLetter in ["G"]:
        xLeft = blackWidth - ( whiteWidth - (whiteWidth*blackOffsetF) )
        xRight = whiteWidth*blackOffsetG
        points = getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)
    elif noteLetter in ["A"]:
        xLeft = blackWidth - ( whiteWidth - (whiteWidth*blackOffsetG) )
        xRight = whiteWidth*blackOffsetA
        points = getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)
    elif noteLetter in ["B"]:
        xLeft = blackWidth - ( whiteWidth - (whiteWidth*blackOffsetA) )
        points = getPointsForKeyShape(noteNumber, xLeft, xRight, isFirstSuffix, isLastSuffix)

    draw.polygon(points, fill=fill, outline=outlineColor)

    shapeImg.save(noteLetterShapeFile.resolve(), 'PNG')
    return noteLetterShapeFile


def createFrameComposition():
    sortedOpenNotes = {k: openNotes[k] for k in sorted(openNotes)}
    compHash = '-'.join(map(str, list(sortedOpenNotes.keys())))
    if compHash == "":
        compHash = "blank"

    compPath = Path( '%s/%s.jpg'% (tempDirFrames.resolve(), compHash) )
    if compPath.is_file():
        print ('found comp %s' % compHash)
        return compPath

    #print( compHash )

    composition = Image.new('RGB', (frameWidth, frameHeight), (0, 0, 0))
    composition.paste(baseImg, (0, 0))

    for noteNumber in sortedOpenNotes:
        singleNotePath = Path( '%s/%s.png'% (tempDirHighlight.resolve(), noteNumber) )
        if not singleNotePath.is_file():
            singleNoteOverlay = Image.new('RGBA', (frameWidth, frameHeight), (255, 0, 0, 0))
            shapeImg = Image.open(getShapeForNoteNumber(noteNumber, highlight=True).resolve())
            offsetX = round(getLeftOffsetForKeyPlacement(noteNumber))
            singleNoteOverlay.paste(shapeImg, (offsetX, 0))
            singleNoteOverlay.save(singleNotePath.resolve(), 'PNG')
            print( "creating new frame overlay for note %s" % noteNumber )
        singleNoteOverlay = Image.open(singleNotePath.resolve())
        composition.paste(singleNoteOverlay, (0, 0), singleNoteOverlay)

    composition.save(compPath.resolve(), 'JPEG')
    print( "creating new comp for %s" % compHash )
    return compPath

baseImg = Image.open(drawFullKeyboard())

frameDurationMs = 1000000/framesPerSecond
currentFrameStartMs = 0

frameFilePaths = []
for frameNum in range(1,totalFrames+1):
    currentFrameEndMs = currentFrameStartMs + frameDurationMs
    updateActiveNotesForFrame(currentFrameEndMs)
    frameFilePaths.append("file '%s'" % createFrameComposition().resolve())
    currentFrameStartMs = currentFrameEndMs

frameFilePathsFile = Path("makevideo.txt")
frameFilePathsFile.write_text(
    '\n'.join(frameFilePaths)
)
#sys.exit()
os.system("ffmpeg -y -f concat -safe 0 -i makevideo.txt -framerate %d %s.mp4" % (framesPerSecond, midiFile) )
os.system("fluidsynth -F %s.wav /usr/share/soundfonts/FluidR3_GM.sf2 %s" % (midiFile,midiFile) )
os.system("ffmpeg -y -i %s.wav -vn -ar 44100 -ac 2 -b:a 192k %s.mp3" % (midiFile,midiFile) )
os.system("ffmpeg -y -i %s.mp4 -i %s.mp3 -c copy -map 0:v:0 -map 1:a:0 %s-w-audio.mp4" % (midiFile,midiFile,midiFile) )
#print(frameFilePaths)
sys.exit()


# ffmpeg -y -f concat -i makevideo.txt -framerate 24 out.mp4
# fluidsynth -F out.wav /usr/share/soundfonts/FluidR3_GM.sf2 example.mid
# ffmpeg -i out.wav -vn -ar 44100 -ac 2 -b:a 192k out.mp3
# ffmpeg -i out.mp4 -i out.mp3 -c copy -map 0:v:0 -map 1:a:0 output-w-audio.mp4


