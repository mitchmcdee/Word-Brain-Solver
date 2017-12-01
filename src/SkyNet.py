#!/usr/bin/env python3
import pyautogui
import sys
import time
import numpy as np
from math import sqrt
from PIL import Image
from Solver import Solver
from Vision import Vision
from Screen import Screen
import logging

logger = logging.getLogger(__name__)
handler = logging.FileHandler('solutions.log')
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

pyautogui.FAILSAFE = True           # Allows exiting the program by moving mouse to top left of screen
IS_RETINA = True                    # Mitch has a macbook
SCREEN_COORDS = [0, 46, 730, 1290]  # Mitch's screen coords

# TODO(mitch): rewrite this file as a class

# Waits until all animations on board have stopped
def waitForAnimation():
    while True:
        b = vision.getBoard()
        time.sleep(0.1)
        if np.array_equal(b, vision.getBoard()):
            break

# Enters the given word onto the board
def enterWord(word, path, width):
    # Wait for animations to stop, necessary for computing board ratio
    waitForAnimation()

    # board ratio before entering word
    start = vision.getBoardRatio()

    # Move over each letter
    for i, letter in enumerate(word):
        b = vision.getCell(path[i], width)
        a = b
        while np.array_equal(a, b):
            pyautogui.moveTo(*letter, pause=0)
            pyautogui.mouseDown(pause=0)
            a = vision.getCell(path[i], width)
    pyautogui.mouseUp(pause=0)

    # Wait for animations to stop, necessary for computing board ratio
    waitForAnimation()

    # Return true if entered word was valid (board states were different), else false
    return start != vision.getBoardRatio()

# Click the button at the given relative width and height
def clickButton(widthPercentage, heightPercentage):
    w = widthPercentage * vision.width
    h = heightPercentage * vision.height

    # if on retina display, halve the mouse resolution due to scaling
    if IS_RETINA:
        w /= 2
        h /= 2

    pyautogui.moveTo(w, h, pause=0)
    pyautogui.mouseDown(pause=0.025)
    pyautogui.mouseUp(pause=0.025)

# Resets the game board and exits any ads on screen
def reset():
    while True:
        b = vision.getBoardRatio()
        clickButton(*vision.AD_BUTTON)
        clickButton(*vision.RESET_BUTTON)
        clickButton(SCREEN_COORDS[0] / vision.width, SCREEN_COORDS[1] / vision.height)
        time.sleep(0.3)
        if b != vision.getBoardRatio():
            waitForAnimation()
            break

# Generates a mouse grid for clicking board tiles
def generateMouseGrid(width):
    grid = Vision.GRID_CENTRES[width - 2]
    mouseGrid = []
    for j in range(width):
        for i in range(width):
            x = int((grid[0][0] + i * grid[1]) * vision.width)
            y = int((grid[0][1] + j * grid[2]) * vision.height) + SCREEN_COORDS[1]

            # if on retina display, halve the mouse resolution due to scaling
            if IS_RETINA:
                x /= 2
                y /= 2

            mouseGrid.append((x, y))
    return mouseGrid

################################################################################

# Set up computer vision and screen
vision = Vision(SCREEN_COORDS, IS_RETINA)
screen = Screen()

# Wait for screen to become responsive (anrdoid emulator? osx? idek lol)
reset()

# Play the game!
while True:
    # Clear screen
    screen.clear()

    # Wait for any lingering animations
    waitForAnimation()

    # state = ['n', 'a', 'r', 'i', 'e', 't', 's', 'e', 'u', 'd', 't', 'r', 't', 'a', 'l', 't', 'e', 'a', 't', 'h', 'a', 'h', 'c', 'v', 'i', 'l', 'b', 'o', 'l', 'e', 'm', 's', 'g', 'f', 'p', 'l']
    # wordLengths = [7, 6, 7, 4, 4, 3, 5]

    # Get level state and word lengths required
    state, wordLengths = vision.getBoardState()
    width = int(sqrt(len(state)))
    logger.info(f'{state} {wordLengths}')

    # Check state is reasonable
    if width == 0 or width ** 2 != len(state) or len(state) != sum(wordLengths) or len(state) < 4:
        logger.info('Invalid state, resetting')
        reset()
        continue

    # Generate mouse grid
    mouseGrid = generateMouseGrid(width)

    # Keep track of time taking to generate solutions
    startTime = time.time()

    # Loop over valid solutions to try them all
    with Solver() as s:
        for solution in s.getSolutions(state, wordLengths):
            # Compute time it took to find a solution
            solutionTime = str(round(time.time() - startTime, 2))
            logger.info(f'{solutionTime}s - Testing: {solution.words}')

            # Get mouse coordinates for solution and enter them
            for i, path in enumerate(solution.path):
                word = ''.join([solution.allStates[i][j] for j in path])
                logger.info(f'entering {word}')
                s.addTestedWord(word)

                # If the same ratio, the word entered was a bad one, so remove it from all solutions
                isValid = enterWord([mouseGrid[i] for i in path], path, width)
                if not isValid:
                    s.addBadWord(word)
                    logger.info(f'added {word} as a bad word')
                    break

            # Else if no break, all words in solution were entered, exit out of entering solutions
            else:
                if len(solution.words) == len(wordLengths):
                    break

            # If we only entered one word incorrectly, we don't need to clear screen
            if len(solution.path) > 0 and i == 0 and not isValid:
                continue

            # Reset board for next solution
            reset()
