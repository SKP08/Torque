"""
Barge-in: talk over Torque and it stops and listens.

Pieces
  tap(block, rate)      called by the speech engine with every block it plays (the reference)
  feed(mic_block)       called by the microphone for every 32 ms block while Torque is speaking
  arm(callback)         start watching; callback() fires once when *you* start talking
  take_preroll()        the last moments of your voice (echo removed), so the first word isn't lost

Your voice is what is left after the echo canceller removes Torque's own voice. It must
be speech (Silero VAD), clearly louder than the echo that slipped through, and last a
few blocks in a row. Until the canceller has heard ~3 seconds of Torque it won't fire
(it can't tell yet), unless the person talks loudly.
"""

import collections
import threading

import numpy as np

from torque.audio.echo import EchoCanceller
from torque.audio.vad import BLOCK_SIZE, SAMPLE_RATE

PREROLL_BLOCKS = 12                 # ~0.4 s


def to_16k(block, rate):
    """int16/float block at `rate` -> float32 at 16 kHz (linear resample; echo path absorbs the error)."""

    audio = np.asarray(block, dtype=np.float32).reshape(-1)

    if audio.dtype != np.float32 or np.abs(audio).max(initial=0) > 1.5:
        audio = audio / 32768.0

    if rate == SAMPLE_RATE or audio.size == 0:
        return audio

    count = max(1, int(round(audio.size * SAMPLE_RATE / rate)))

    return np.interp(np.linspace(0, audio.size - 1, count), np.arange(audio.size), audio).astype(np.float32)


class BargeIn:

    def __init__(self, vad=None, canceller=None, threshold=0.6, min_blocks=5, loudness=0.8,
                 floor=0.012, max_backlog=SAMPLE_RATE):
        """
        threshold  VAD probability that counts as speech on the residual
        min_blocks consecutive speech blocks needed (5 = 160 ms)
        loudness   residual RMS must exceed loudness * (our own echo level)
        floor      ...and this absolute RMS (about -38 dBFS), so quiet hiss never fires
        """

        if vad is None:
            from torque.audio.vad import load_model

            vad = load_model()

        self.vad = vad
        self.canceller = canceller or EchoCanceller()
        self.threshold = threshold
        self.min_blocks = min_blocks
        self.loudness = loudness
        self.floor = floor
        self.max_backlog = max_backlog

        self._lock = threading.Lock()
        self._reference = np.zeros(0, dtype=np.float32)
        self._callback = None
        self._run = 0
        self._preroll = collections.deque(maxlen=PREROLL_BLOCKS)
        self._fired = False

    # ---- speaker side -------------------------------------------------

    def tap(self, block, rate):
        """What is about to be played; queued as the reference for the echo canceller."""

        samples = to_16k(block, rate)

        with self._lock:
            self._reference = np.concatenate([self._reference, samples])[-self.max_backlog:]

    # ---- control ------------------------------------------------------

    def arm(self, callback):
        with self._lock:
            self._callback = callback
            self._run = 0
            self._fired = False
            self._preroll.clear()

        self.vad.reset()

    def disarm(self):
        with self._lock:
            self._callback = None
            self._reference = np.zeros(0, dtype=np.float32)

    @property
    def armed(self) -> bool:
        return self._callback is not None

    def take_preroll(self):
        """int16 blocks of your voice from just before/at the trigger (echo removed)."""

        with self._lock:
            blocks = list(self._preroll)
            self._preroll.clear()

        return [np.clip(b * 32768.0, -32768, 32767).astype(np.int16) for b in blocks]

    # ---- microphone side ---------------------------------------------

    def feed(self, mic_block) -> bool:
        """One 512-sample mic block. Returns True on the block that triggers barge-in."""

        with self._lock:
            callback = self._callback

            if callback is None or self._fired:
                return False

            reference = self._reference[:BLOCK_SIZE]
            self._reference = self._reference[BLOCK_SIZE:]

        mic = np.asarray(mic_block, dtype=np.float32) / 32768.0

        if reference.size < BLOCK_SIZE:
            reference = np.concatenate([reference, np.zeros(BLOCK_SIZE - reference.size, dtype=np.float32)])

        residual = self.canceller.process(mic, reference).astype(np.float32)
        level = float(np.sqrt(np.mean(residual * residual)))
        echo = self.canceller.echo_estimate_rms

        self._preroll.append(residual)

        probability = float(self.vad(residual))              # every block, so the VAD state stays continuous

        loud_enough = level > max(self.floor, self.loudness * echo)

        if not self.canceller.converged:
            loud_enough = loud_enough and level > 3 * max(self.floor, echo)   # unsure yet: need clearly louder

        self._run = self._run + 1 if (loud_enough and probability >= self.threshold) else 0

        if self._run >= self.min_blocks:
            with self._lock:
                self._fired = True

            callback()
            return True

        return False
