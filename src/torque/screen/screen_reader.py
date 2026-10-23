import re

from loguru import logger

MAX_WIDTH = 1920          # larger screens are shrunk first: OCR time grows with pixels
MAX_CHARS = 3000          # what the small local model gets to read
MIN_CONFIDENCE = 0.5


class OcrUnavailableError(RuntimeError):
    """The OCR package isn't installed."""


class RapidOcrEngine:
    """Local OCR (onnxruntime). Imported lazily so Torque starts without it."""

    def __init__(self):
        self._engine = None

    def _load(self):

        if self._engine:
            return self._engine

        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            try:
                from rapidocr import RapidOCR
            except ImportError as error:
                raise OcrUnavailableError(
                    "Screen reading needs the OCR add-on: run uv sync --extra screen."
                ) from error

        self._engine = RapidOCR()

        return self._engine

    def read(self, image):
        """Returns [(x, y, height, text)] for each detected line of text."""

        import numpy as np

        result = self._load()(np.array(image.convert("RGB")))

        # rapidocr-onnxruntime returns (result, timing); rapidocr 3.x an object.
        boxes = result[0] if isinstance(result, tuple) else getattr(result, "boxes", None)
        texts = None if isinstance(result, tuple) else getattr(result, "txts", None)
        scores = None if isinstance(result, tuple) else getattr(result, "scores", None)

        lines = []

        if isinstance(result, tuple):

            for box, text, score in (boxes or []):

                if float(score) >= MIN_CONFIDENCE:
                    lines.append(self._line(box, text))

        elif boxes is not None and texts is not None:

            for box, text, score in zip(boxes, texts, scores):

                if float(score) >= MIN_CONFIDENCE:
                    lines.append(self._line(box, text))

        return lines

    @staticmethod
    def _line(box, text):

        xs = [p[0] for p in box]
        ys = [p[1] for p in box]

        return (min(xs), min(ys), max(ys) - min(ys), text)


def lines_to_text(lines) -> str:
    """Reading order: top to bottom, left to right within a row."""

    ordered = sorted(lines, key=lambda l: (round(l[1] / max(l[2], 1)), l[0]))

    rows = []
    last_y = None

    for x, y, h, text in ordered:

        if last_y is not None and abs(y - last_y) < max(h, 1) * 0.6:
            rows[-1].append(text)
        else:
            rows.append([text])

        last_y = y

    return "\n".join(" ".join(row) for row in rows)


class ScreenReader:
    """Takes a screenshot and returns the text on it. Nothing is saved."""

    def __init__(self, grab=None, ocr=None):

        self._grab = grab or self._default_grab
        self.ocr = ocr or RapidOcrEngine()

    @staticmethod
    def _default_grab():

        from PIL import ImageGrab

        return ImageGrab.grab()

    def read(self) -> str:

        image = self._grab()

        if image.width > MAX_WIDTH:

            height = round(image.height * MAX_WIDTH / image.width)
            image = image.resize((MAX_WIDTH, height))

        text = lines_to_text(self.ocr.read(image))

        text = re.sub(r"[ \t]+", " ", text).strip()

        logger.debug(f"Read {len(text)} characters from the screen.")

        return text[:MAX_CHARS]
