from pathlib import Path
from queue import Empty, Queue
import time

import numpy as np
import sounddevice as sd
import soundfile as sf
from loguru import logger

from torque.audio.vad_service import VADService


class MicrophoneService:

    SAMPLE_RATE = 16000
    CHANNELS = 1
    BLOCK_SIZE = 512

    # How long Torque waits after speech ends to see
    # whether the user continues the same thought.
    END_GRACE_SECONDS = 1.0

    def __init__(self):

        logger.info("Initializing Microphone...")

        self.vad = VADService()

        self.queue = Queue()

        self.recording = False
        self.finished = False

        self.frames = []

        logger.success("Microphone ready.")

    # ==========================================================
    # AUDIO CALLBACK
    # ==========================================================

    def _callback(
        self,
        indata,
        frames,
        time_info,
        status,
    ):

        if status:
            logger.warning(status)

        self.queue.put(
            bytes(indata)
        )

    # ==========================================================
    # SAVE AUDIO
    # ==========================================================

    def _save_audio(self):

        if not self.frames:

            logger.warning(
                "No audio frames to save."
            )

            return None

        audio = np.concatenate(
            self.frames
        ).astype(np.float32)

        output = (
            Path(__file__).resolve().parents[3]
            / "data"
            / "recording.wav"
        )

        output.parent.mkdir(
            exist_ok=True
        )

        sf.write(
            output,
            audio,
            self.SAMPLE_RATE,
        )

        logger.success(
            f"Saved recording to: {output}"
        )

        return output

    # ==========================================================
    # RECORD
    # ==========================================================

    def record(self):

        logger.info("Waiting for speech...")

        # ------------------------------------------------------
        # RESET STATE
        # ------------------------------------------------------

        self.queue = Queue()

        self.vad.reset()

        self.frames = []

        self.recording = False

        self.finished = False

        # True when VAD has detected the end of speech
        # and we are waiting briefly for continuation.
        waiting_for_continuation = False

        continuation_started_at = None

        with sd.RawInputStream(
            samplerate=self.SAMPLE_RATE,
            blocksize=self.BLOCK_SIZE,
            channels=self.CHANNELS,
            dtype="int16",
            callback=self._callback,
        ):

            logger.success(
                "Microphone stream started."
            )

            while not self.finished:

                try:

                    chunk = self.queue.get(
                        timeout=0.1
                    )

                except Empty:

                    # --------------------------------------------------
                    # CHECK CONTINUATION TIMEOUT
                    # --------------------------------------------------

                    if (
                        waiting_for_continuation
                        and continuation_started_at
                        is not None
                        and time.monotonic()
                        - continuation_started_at
                        >= self.END_GRACE_SECONDS
                    ):

                        logger.success(
                            "No continuation detected. "
                            "Speech ended."
                        )

                        self.finished = True

                    continue

                # --------------------------------------------------
                # CONVERT AUDIO
                # --------------------------------------------------

                audio = (
                    np.frombuffer(
                        chunk,
                        dtype=np.int16,
                    )
                    .astype(np.float32)
                    / 32768.0
                )

                result = self.vad.process(
                    audio
                )

                # ==================================================
                # STATE 1: CURRENTLY RECORDING SPEECH
                # ==================================================

                if self.recording:

                    # Keep all audio while the user is speaking.
                    self.frames.append(audio)

                    if (
                        result is not None
                        and "end" in result
                    ):

                        logger.info(
                            "VAD detected end of speech. "
                            "Waiting for continuation..."
                        )

                        self.recording = False

                        waiting_for_continuation = True

                        continuation_started_at = (
                            time.monotonic()
                        )

                    continue

                # ==================================================
                # STATE 2: WAITING FOR CONTINUATION
                # ==================================================

                if waiting_for_continuation:

                    # IMPORTANT:
                    # Do NOT continuously save silence here.
                    #
                    # Only resume recording when VAD detects
                    # genuine new speech.

                    if (
                        result is not None
                        and "start" in result
                    ):

                        logger.success(
                            "Speech continued. "
                            "Continuing same user turn."
                        )

                        waiting_for_continuation = False

                        continuation_started_at = None

                        self.recording = True

                        # Save the chunk where continuation begins.
                        self.frames.append(audio)

                        continue

                    # Check timeout even while audio chunks
                    # continue arriving.

                    if (
                        continuation_started_at
                        is not None
                        and time.monotonic()
                        - continuation_started_at
                        >= self.END_GRACE_SECONDS
                    ):

                        logger.success(
                            "Continuation window expired. "
                            "Finalizing recording."
                        )

                        self.finished = True

                    continue

                # ==================================================
                # STATE 3: WAITING FOR INITIAL SPEECH
                # ==================================================

                if (
                    result is not None
                    and "start" in result
                ):

                    logger.success(
                        "Speech detected."
                    )

                    self.recording = True

                    # Save the chunk where speech begins.
                    self.frames.append(audio)

        # ------------------------------------------------------
        # FINALIZE
        # ------------------------------------------------------

        self.recording = False

        self.finished = False

        return self._save_audio()

    # ==========================================================
    # STOP
    # ==========================================================

    def stop(self):

        self.recording = False

        self.finished = True

        self.frames.clear()

        logger.info(
            "Microphone stopped."
        )

    # ==========================================================
    # RESET
    # ==========================================================

    def reset(self):

        self.queue = Queue()

        self.frames = []

        self.recording = False

        self.finished = False

        self.vad.reset()

        logger.info(
            "Microphone reset."
        )