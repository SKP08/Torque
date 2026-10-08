import time

import numpy as np
import sounddevice as sd
from loguru import logger
from piper import PiperVoice


class TTSService:

    SAMPLE_RATE = 22050

    def __init__(self):

        logger.info("Loading Piper...")

        start = time.perf_counter()

        self.voice = PiperVoice.load(
            "models/piper/en_US-lessac-medium.onnx",
            "models/piper/en_US-lessac-medium.onnx.json",
        )

        logger.success(
            f"Piper ready in {time.perf_counter() - start:.2f}s."
        )

    def speak(self, text: str):

        logger.info(f"Speaking: {text}")

        total_start = time.perf_counter()

        synth_start = time.perf_counter()

        audio_chunks = list(
            self.voice.synthesize(text)
        )

        logger.info(
            f"Synthesis: {time.perf_counter() - synth_start:.2f}s"
        )

        concat_start = time.perf_counter()

        audio = np.concatenate(
            [
                chunk.audio_int16_array
                for chunk in audio_chunks
            ]
        )

        logger.info(
            f"Concatenate: {time.perf_counter() - concat_start:.2f}s"
        )

        play_start = time.perf_counter()

        sd.play(
            audio,
            samplerate=self.SAMPLE_RATE,
        )

        logger.info(
            f"Playback started after {time.perf_counter() - play_start:.2f}s"
        )

        wait_start = time.perf_counter()

        sd.wait()

        logger.info(
            f"Playback duration: {time.perf_counter() - wait_start:.2f}s"
        )

        logger.success(
            f"Total TTS: {time.perf_counter() - total_start:.2f}s"
        )