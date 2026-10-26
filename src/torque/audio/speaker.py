"""
Speaker verification: only wake for YOUR voice.

A small speaker-embedding network (WeSpeaker ResNet34, ~26 MB, runs on the CPU in
~50 ms) turns a few seconds of speech into a 256-number voice print. Your print is
saved once; later, "Hey Torque" only counts when the voice matches it.

    uv run python -m torque.audio.speaker download     # fetch the model (one time)
    uv run python -m torque.audio.speaker enroll       # read some sentences aloud (~20 s)

The voice print is a list of numbers, not a recording. Nothing here leaves the PC.
"""

import sys
import urllib.request
from pathlib import Path

import numpy as np
from loguru import logger

from torque.paths import DATA_DIR, MODELS_DIR

MODEL_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
             "speaker-recongition-models/wespeaker_en_voxceleb_resnet34.onnx")
MODEL_PATH = MODELS_DIR / "speaker" / "wespeaker_en_voxceleb_resnet34.onnx"
PROFILE_PATH = DATA_DIR / "voice_profile.npy"
MIN_MODEL_BYTES = 20_000_000

SAMPLE_RATE = 16000
MIN_SECONDS = 0.8                       # shorter clips don't carry enough voice


# --------------------------------------------------------------------------
# Features: Kaldi-style 80-bin log mel filterbank (what the model was trained on)
# --------------------------------------------------------------------------

def _mel(freq):
    return 1127.0 * np.log(1.0 + freq / 700.0)


def mel_banks(bins=80, fft_size=512, rate=SAMPLE_RATE, low=20.0, high=None):
    high = high or rate / 2
    mel_points = np.linspace(_mel(low), _mel(high), bins + 2)
    freqs = np.arange(fft_size // 2 + 1) * rate / fft_size
    mel = _mel(freqs)
    banks = np.zeros((bins, fft_size // 2 + 1))

    for i in range(bins):
        left, centre, right = mel_points[i], mel_points[i + 1], mel_points[i + 2]
        up = (mel - left) / (centre - left)
        down = (right - mel) / (right - centre)
        banks[i] = np.maximum(0, np.minimum(up, down))

    return banks


_BANKS = None


def fbank(audio, rate=SAMPLE_RATE):
    """float audio in [-1, 1] -> (frames, 80) log-mel features, mean-normalised over time."""

    global _BANKS

    if _BANKS is None:
        _BANKS = mel_banks()

    x = np.asarray(audio, dtype=np.float64) * 32768.0
    length, shift = int(0.025 * rate), int(0.010 * rate)

    if x.size < length:
        return np.zeros((0, 80), dtype=np.float32)

    count = 1 + (x.size - length) // shift
    index = np.arange(length)[None, :] + shift * np.arange(count)[:, None]
    frames = x[index]

    frames = frames - frames.mean(axis=1, keepdims=True)                      # remove DC
    frames = np.concatenate([frames[:, :1], frames[:, 1:] - 0.97 * frames[:, :-1]], axis=1)   # pre-emphasis
    frames = frames * np.hamming(length)[None, :]

    power = np.abs(np.fft.rfft(frames, n=512, axis=1)) ** 2
    energy = np.log(np.maximum(power @ _BANKS.T, np.finfo(np.float32).eps))

    return (energy - energy.mean(axis=0, keepdims=True)).astype(np.float32)


# --------------------------------------------------------------------------
# Encoder + profile
# --------------------------------------------------------------------------

class SpeakerEncoder:

    def __init__(self, model_path=MODEL_PATH):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 1

        self._session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])

    def embed(self, audio):
        """Unit-length 256-d voice print, or None if the clip is too short."""

        audio = np.asarray(audio, dtype=np.float32)

        if audio.size < MIN_SECONDS * SAMPLE_RATE:
            return None

        features = fbank(audio)[None]
        vector = self._session.run(None, {"feats": features})[0][0].astype(np.float64)
        norm = np.linalg.norm(vector)

        return vector / norm if norm else None


def cosine(a, b) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


class VoiceGate:
    """accepts(audio) -> True when the voice matches the enrolled profile."""

    def __init__(self, encoder, profile, threshold=0.5):
        self.encoder = encoder
        self.profile = np.asarray(profile, dtype=np.float64)
        self.threshold = threshold
        self.last_score = None

    def score(self, audio):
        vector = self.encoder.embed(audio)

        return None if vector is None else cosine(vector, self.profile)

    def accepts(self, audio) -> bool:
        """Too-short or missing audio is accepted: we can't tell, and a false lock-out is worse."""

        if audio is None:
            return True

        score = self.score(audio)
        self.last_score = score

        if score is None:
            return True

        logger.debug(f"Voice match {score:.2f} (needs {self.threshold:.2f})")

        return score >= self.threshold


def enrol(encoder, clips):
    """Average the voice prints of several clips into one profile (unit length)."""

    vectors = [v for v in (encoder.embed(c) for c in clips) if v is not None]

    if len(vectors) < 2:
        raise ValueError("Need at least two usable clips (each longer than a second).")

    centre = np.mean(vectors, axis=0)

    return centre / np.linalg.norm(centre)


def load_gate(config, model_path=MODEL_PATH, profile_path=PROFILE_PATH):
    """A VoiceGate if verification is on and set up, else None (never blocks the wake word by accident)."""

    if not config.get("voice_lock_enabled"):
        return None

    if not Path(model_path).exists() or not Path(profile_path).exists():
        logger.warning("voice_lock_enabled is on but the model or your voice profile is missing; "
                       "run: python -m torque.audio.speaker download / enroll. Wake word works for anyone meanwhile.")
        return None

    try:
        return VoiceGate(SpeakerEncoder(model_path), np.load(profile_path),
                         float(config.get("voice_lock_threshold", 0.5)))
    except Exception:  # noqa: BLE001
        logger.exception("Could not start voice verification.")
        return None


# --------------------------------------------------------------------------
# Command line: download + enrol
# --------------------------------------------------------------------------

PHRASES = [
    "Hey Torque, what time is it?",
    "Open Chrome and play some music.",
    "The quick brown fox jumps over the lazy dog.",
    "Hey Torque, show me the status of my computer.",
    "Remind me in ten minutes to stretch.",
]


def download(dest=MODEL_PATH, url=MODEL_URL):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part")

    with urllib.request.urlopen(url, timeout=60) as response, open(part, "wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)

    if part.stat().st_size < MIN_MODEL_BYTES:
        part.unlink()
        raise RuntimeError("download looks truncated")

    part.replace(dest)

    return dest


def _enrol_from_microphone():
    import sounddevice as sd

    encoder = SpeakerEncoder()
    clips = []

    print("Read each line aloud in your normal voice, then wait for the next.\n")

    for phrase in PHRASES:
        input(f'  Press Enter, then say: "{phrase}"  ')
        audio = sd.rec(int(5 * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
        sd.wait()
        clips.append(audio[:, 0])

    profile = enrol(encoder, clips)
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.save(PROFILE_PATH, profile)

    print(f"\nSaved your voice print to {PROFILE_PATH}. Set voice_lock_enabled to true in config/settings.json.")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""

    try:
        if command == "download":
            print(f"Saved {download()}")
        elif command == "enroll":
            _enrol_from_microphone()
        else:
            print("usage: python -m torque.audio.speaker download | enroll")
            sys.exit(2)
    except Exception as error:  # noqa: BLE001
        print(f"Failed: {error}", file=sys.stderr)
        sys.exit(1)
