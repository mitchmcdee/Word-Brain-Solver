import sys
import os
import logging
import pickle
from math import ceil
from Trie import Trie
from State import State
from collections import Counter
from multiprocessing import Process, Queue, Lock, Manager, current_process

logger = logging.getLogger(__name__)
handler = logging.FileHandler('workers.log')
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


class Solver:
    SEEN_THRESHOLD = 25 # Minimum state size that will yield any new words seen

    def __init__(self):
        m = Manager()              # TODO(mitch): profile this and see if its performant?
        self.badWords  = m.dict()  # Set of words not to search
        self.seenWords = m.dict()  # Set of words already seen
        self.testedWords = m.dict()  # Set of words already tested
        self.workers   = []        # List of workers

        self.solutionQueue = Queue()
        self.testQueue     = Queue()

    # Return self on enter
    def __enter__(self):
        return self

    # Clear queues and words on exit
    def __exit__(self, t, v, traceback):
        [w.terminate() for w in self.workers]
        [w.join() for w in self.workers]

    # Add a bad word to avoid it being searched again
    def addBadWord(self, word):
        self.badWords[word] = 1

    # Add a seen word to avoid it being tested again
    def addTestedWord(self, word):
        self.testedWords[word] = 1

    # Generates a trie tailored to the given state and word lengths and broadcasts it
    def initialiseTrie(self, state, wordLengths):
        numWords = 0
        trie = Trie()
        with open('../resources/goodWords.txt', 'r') as f:
            for line in f:
                word = line.strip('\n')

                # Skip words that have lengths not of interest
                if len(word) not in wordLengths:
                    continue

                stateCounter = Counter(state)
                wordCounter = Counter(word)
                stateCounter.subtract(wordCounter)

                # Skip words that cannot be made from the initial state of letters
                if any(v < 0 for v in stateCounter.values()):
                    continue

                numWords += trie.addWord(word)
        logger.info(f'Added {numWords} words to trie')
        return trie

    # Solve the current level
    def getSolutions(self, state, wordLengths):
        # Initialise trie tree
        self.trie = self.initialiseTrie(state, wordLengths)

        # Generate all root states
        initialState = State(state, wordLengths)
        rootStates = self.getChildStates('pre:', initialState)

        # Split root states up evenly to distribute to processes
        numWorkers = max(1, os.cpu_count() // 2)
        splitStates = [rootStates[i::numWorkers] for i in range(numWorkers)]

        # Start workers
        for i in range(numWorkers):
            p = Process(target=self.solvingWorker, args=(i, splitStates[i]))
            p.daemon = True
            p.start()
            self.workers.append(p)

        # Yield found solutions
        activeWorkers = numWorkers
        while True:
            # Check for complete solutions
            try:
                solution = self.solutionQueue.get_nowait()
            except:
                # No more solutions and no more workers!
                if activeWorkers == 0:
                    break
            else:
                if type(solution) == int:
                    p = self.workers[solution]
                    p.terminate() and p.join()
                    activeWorkers -= 1
                    logger.info(f'{activeWorkers} workers left!')
                    continue

                elif all(w not in self.badWords for w in solution.words):
                    yield solution

            # Check for test solutions
            try:
                testWord, testState = self.testQueue.get_nowait()
            except:
                pass
            else:
                if testWord not in self.testedWords and all(w not in self.badWords for w in testState.words):
                    yield testState
                if testWord in self.seenWords:
                    logger.info(f'{testWord} {testState.path}')
                    del self.seenWords[testWord]

    # Worker which solves states and sends solutions to main process
    def solvingWorker(self, i, stack):
        while len(stack) != 0:
            state = stack.pop()

            # Check state doesn't contain any bad words
            if any(w in self.badWords for w in state.words):
                continue

            # Calculate child states
            stack.extend(self.getChildStates(i, state))

        # Send death message
        self.solutionQueue.put(i)

    # Generates all child solutions of a root state
    def getChildStates(self, i, state):
        childStates = []
        uniqueStates = set()
        for root in state.getValidRoots(self.trie):
            for path in root.getValidPaths(self.trie, state):
                # If the child word already exists, skip over the state
                childWord = state.getWord(path)
                if childWord in state.words:
                    continue

                # If the child state already exists, skip over the state
                childState = state.getRemovedPathState(path)
                if tuple(childState.state) in uniqueStates:
                    continue

                # Check state doesn't contain any bad words
                if any(w in self.badWords for w in childState.words):
                    continue

                # If there are no more words, we've found a complete solution
                if len(childState.wordLengths) == 0:
                    self.solutionQueue.put(childState)
                    continue

                childStates.append(childState)
                uniqueStates.add(tuple(childState.state))
                # logger.info(f'{i}: {childState.words}')

                # If we're solving a small state, don't bother testing solutions
                if len(childState.state) <= Solver.SEEN_THRESHOLD:
                    continue

                # If we haven't seen a word before, test it
                for word in childState.words:
                    if word not in self.seenWords and word not in self.testedWords:
                        self.seenWords[word] = 1
                        self.testQueue.put((word, childState))
                        # logger.info(f'{i}: {word} {childState.words}')
                        break
        return childStates