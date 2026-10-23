import time
from collections import deque

import numpy as np


class UtteranceCollector:
    """
    Pure state machine that turns a stream of audio blocks plus VAD events
    into one utterance. No audio hardware involved, so it is unit-testable.

    States:
        waiting   nothing heard yet; blocks go into a rolling pre-roll buffer
                  so the first syllable (before VAD fired) is not clipped
        speaking  VAD says the user is talking
        grace     VAD said speech ended; wait briefly in case they continue

    Feed it blocks with feed(block, event) where event is "start", "end" or
    None. It returns True when the utterance is complete.
    """

    WAITING = "waiting"
    SPEAKING = "speaking"
    GRACE = "grace"

    def __init__(
        self,
        sample_rate=16000,
        block_size=512,
        preroll_seconds=0.4,
        grace_seconds=1.0,
        max_seconds=30.0,
        clock=time.monotonic,
    ):

        self.sample_rate = sample_rate
        self.grace_seconds = grace_seconds
        self.max_samples = int(max_seconds * sample_rate)
        self._clock = clock

        preroll_blocks = max(1, int(preroll_seconds * sample_rate / block_size))

        self._preroll = deque(maxlen=preroll_blocks)

        self.state = self.WAITING

        self._frames = []
        self._pending = []
        self._samples = 0
        self._grace_started = None

    @property
    def waiting(self) -> bool:
        return self.state == self.WAITING

    def feed(self, block, event=None) -> bool:

        if self.state == self.WAITING:

            self._preroll.append(block)

            if event == "start":
                self._frames = list(self._preroll)
                self._samples = sum(len(b) for b in self._frames)
                self.state = self.SPEAKING

            return False

        if self.state == self.SPEAKING:

            self._append(block)

            if event == "end":
                self.state = self.GRACE
                self._grace_started = self._clock()
                self._pending = []

            return self._too_long()

        # GRACE
        if event == "start":

            # They carried on: keep the pause so the audio stays natural.
            for pending in self._pending:
                self._append(pending)

            self._pending = []
            self._append(block)
            self.state = self.SPEAKING
            self._grace_started = None

            return self._too_long()

        self._pending.append(block)

        return self.expired()

    def expired(self) -> bool:
        """True once the post-speech grace period has run out."""

        return (
            self.state == self.GRACE
            and self._grace_started is not None
            and self._clock() - self._grace_started >= self.grace_seconds
        )

    def _append(self, block):
        self._frames.append(block)
        self._samples += len(block)

    def _too_long(self) -> bool:
        return self._samples >= self.max_samples

    @property
    def has_speech(self) -> bool:
        return bool(self._frames)

    @property
    def duration(self) -> float:
        return self._samples / self.sample_rate

    def audio(self):
        """The utterance as float32 mono, or None if nothing was said."""

        if not self._frames:
            return None

        return np.concatenate(self._frames).astype(np.float32)
