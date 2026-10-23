import numpy as np
from loguru import logger

SAMPLE_RATE = 22050


def _tone(frequency: float, seconds: float, volume: float) -> np.ndarray:

    count = int(SAMPLE_RATE * seconds)
    t = np.arange(count) / SAMPLE_RATE

    wave = np.sin(2 * np.pi * frequency * t)

    # Fade in and out so there are no clicks.
    fade = min(count // 4, int(0.012 * SAMPLE_RATE))

    envelope = np.ones(count)
    envelope[:fade] = np.linspace(0, 1, fade)
    envelope[-fade:] = np.linspace(1, 0, fade)

    return wave * envelope * volume


def make_chime(kind: str = "wake") -> np.ndarray:
    """
    A short, soft two-note chime as int16 mono at 22.05 kHz.
    "wake" rises (I'm listening); "done" falls.
    """

    notes = (660.0, 880.0) if kind == "wake" else (880.0, 587.0)

    audio = np.concatenate([_tone(f, 0.07, 0.22) for f in notes])

    return (audio * 32767).astype(np.int16)


def play_chime(kind: str = "wake", block: bool = True) -> None:
    """Play the chime; never raises (no speakers is not an error)."""

    try:
        import sounddevice as sd

        sd.play(make_chime(kind), samplerate=SAMPLE_RATE)

        if block:
            sd.wait()

    except Exception:  # noqa: BLE001
        logger.debug("Could not play chime.", exc_info=True)
