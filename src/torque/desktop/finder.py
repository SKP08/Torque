"""
Find text on the screen (OCR) and say where to click.

Only looks: it takes a screenshot, reads it locally and returns coordinates in
real screen pixels. Nothing is saved or sent anywhere.
"""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

MAX_WIDTH = 1920            # screenshots are shrunk for OCR speed; results are scaled back
FUZZY = 82                  # tolerates one OCR slip in a word ("cancle")
MIN_FUZZY_CHARS = 5         # short labels must match exactly ("save" must not become "safe")


@dataclass
class Target:
    x: int
    y: int
    text: str           # the line it was found in
    score: float


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", (text or "").lower()).strip()


class ScreenFinder:

    def __init__(self, grab=None, ocr=None):
        self._grab = grab or self._default_grab
        self._ocr = ocr

    @staticmethod
    def _default_grab():
        from PIL import ImageGrab

        return ImageGrab.grab(all_screens=False)

    @property
    def ocr(self):
        if self._ocr is None:
            from torque.screen.screen_reader import RapidOcrEngine

            self._ocr = RapidOcrEngine()

        return self._ocr

    def boxes(self):
        """[(x, y, w, h, text)] in real screen pixels."""

        image = self._grab()
        scale = 1.0

        if image.width > MAX_WIDTH:
            scale = image.width / MAX_WIDTH
            image = image.resize((MAX_WIDTH, round(image.height / scale)))

        return [(x * scale, y * scale, w * scale, h * scale, text)
                for x, y, w, h, text in self.ocr.read_boxes(image)]

    def find(self, query: str, boxes=None) -> list:
        """Best matches first. Whole-line > a word inside a line > a fuzzy match."""

        wanted = _norm(query)

        if not wanted:
            return []

        found = []

        for x, y, w, h, text in (boxes if boxes is not None else self.boxes()):
            line = _norm(text)

            if not line:
                continue

            cy = int(y + h / 2)

            if line == wanted:
                found.append(Target(int(x + w / 2), cy, text, 100.0))
                continue

            index = _word_index(line, wanted)

            if index is not None:
                # place the click on the phrase, not the middle of the whole line
                centre = (index + len(wanted) / 2) / max(len(line), 1)
                found.append(Target(int(x + w * centre), cy, text, 95.0))
                continue

            score = fuzz.ratio(line, wanted) if len(wanted) >= MIN_FUZZY_CHARS else 0

            if score >= FUZZY:
                found.append(Target(int(x + w / 2), cy, text, float(score)))

        # best score first; among equals, top-left first (reading order)
        return sorted(found, key=lambda t: (-t.score, t.y, t.x))


def _word_index(line: str, wanted: str):
    """Index of `wanted` inside `line` when it starts and ends on word boundaries."""

    match = re.search(rf"(?<![a-z0-9]){re.escape(wanted)}(?![a-z0-9])", line)

    return match.start() if match else None
