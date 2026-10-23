"""
Download the Kokoro voice files (about 120 MB, one time):

    uv run python -m torque.audio.voice_download

Files land in models/kokoro/. Torque then uses Kokoro automatically if it
runs fast enough on your PC (tts_engine = "auto").
"""

import sys
import urllib.request
from pathlib import Path

from torque.paths import MODELS_DIR

BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

FILES = {
    "kokoro-v1.0.int8.onnx": 80_000_000,        # minimum plausible size in bytes
    "voices-v1.0.bin": 20_000_000,
}


def download(name: str, minimum: int, folder: Path, base: str = BASE, progress=True) -> Path:
    """Download atomically: a half-finished file is never left looking complete."""

    target = folder / name

    if target.exists() and target.stat().st_size >= minimum:
        print(f"{name}: already downloaded")
        return target

    folder.mkdir(parents=True, exist_ok=True)

    temporary = target.with_suffix(target.suffix + ".part")

    with urllib.request.urlopen(f"{base}/{name}", timeout=30) as response, open(temporary, "wb") as out:

        total = int(response.headers.get("Content-Length") or 0)
        done = 0

        while chunk := response.read(1 << 20):

            out.write(chunk)
            done += len(chunk)

            if progress and total:
                print(f"\r{name}: {done * 100 // total}%", end="", flush=True)

    if temporary.stat().st_size < minimum:
        temporary.unlink()
        raise RuntimeError(f"{name} downloaded incompletely; try again.")

    temporary.replace(target)

    if progress:
        print(f"\r{name}: done      ")

    return target


def main() -> int:

    folder = MODELS_DIR / "kokoro"

    try:
        for name, minimum in FILES.items():
            download(name, minimum, folder)

    except Exception as error:  # noqa: BLE001
        print(f"\nDownload failed: {error}\nCheck your internet connection and run it again.")
        return 1

    print(f"\nVoice installed in {folder}. Restart Torque to use it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
