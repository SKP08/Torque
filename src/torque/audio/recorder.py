from pathlib import Path

import sounddevice as sd
import soundfile as sf
from loguru import logger


class MicrophoneService:

    SAMPLE_RATE = 16000
    CHANNELS = 1

    def __init__(self):
        logger.success("Microphone service ready.")

    def record(self):

        logger.info("Waiting for speech...")

        print("\nPress ENTER to start recording.")
        input()

        logger.info("Recording... Press ENTER again to stop.")

        recording = []

        def callback(indata, frames, time, status):
            if status:
                print(status)

            recording.append(indata.copy())

        stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            dtype="float32",
            callback=callback,
        )

        stream.start()

        input()

        stream.stop()
        stream.close()

        import numpy as np

        audio = np.concatenate(recording, axis=0)

        output = (
            Path(__file__).resolve().parents[3]
            / "data"
            / "recording.wav"
        )

        output.parent.mkdir(exist_ok=True)

        sf.write(
            output,
            audio,
            self.SAMPLE_RATE,
        )

        logger.success(f"Saved recording to: {output}")

        return output