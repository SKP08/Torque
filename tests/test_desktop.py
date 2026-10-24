import time

import pytest
from PIL import Image, ImageDraw, ImageFont

from torque.desktop.finder import ScreenFinder
from torque.skills.desktop_skills import build_desktop_skills
from torque.skills.registry import SkillRegistry


class FakeOcr:
    def __init__(self, boxes): self.boxes = boxes
    def read_boxes(self, image): return self.boxes


def finder_with(boxes, size=(1920, 1080)):
    return ScreenFinder(grab=lambda: Image.new("RGB", size), ocr=FakeOcr(boxes))


BOXES = [
    (100, 50, 300, 20, "File Edit View Help"),
    (800, 500, 120, 30, "Save"),
    (800, 600, 120, 30, "Save As"),
    (900, 700, 100, 30, "Delete"),
    (50, 900, 200, 20, "Search or type a URL"),
    (400, 400, 100, 30, "Cancle"),
]


def test_exact_line_beats_partial():
    (best, *rest) = finder_with(BOXES).find("save")
    assert (best.x, best.y) == (860, 515) and best.text == "Save"
    assert rest and rest[0].text == "Save As"


def test_word_inside_a_line_is_clicked_where_the_word_is():
    edit = finder_with(BOXES).find("edit")[0]
    file_ = finder_with(BOXES).find("file")[0]
    view = finder_with(BOXES).find("view")[0]
    assert file_.x < edit.x < view.x < 400 and edit.y == 60


def test_fuzzy_match_tolerates_ocr_slips_but_not_short_labels():
    assert finder_with(BOXES).find("cancel")[0].text == "Cancle"
    assert finder_with([(0, 0, 50, 20, "Safe")]).find("save") == []


def test_no_match_and_empty_query():
    assert finder_with(BOXES).find("banana") == []
    assert finder_with(BOXES).find("") == [] and finder_with(BOXES).find("!!!") == []


def test_big_screens_are_scaled_back_to_real_pixels():
    big = ScreenFinder(grab=lambda: Image.new("RGB", (3840, 2160)),
                       ocr=FakeOcr([(960, 540, 100, 40, "OK")]))
    target = big.find("ok")[0]
    assert (target.x, target.y) == (2 * (960 + 50), 2 * (540 + 20))


# ------------------------------------------------------------------ skills

class Desktop:
    def __init__(self): self.log = []
    def click(self, x, y, button="left", double=False): self.log.append(("click", x, y, button, double))
    def type_text(self, t): self.log.append(("type", t))
    def press(self, k): self.log.append(("press", k))
    def scroll(self, a): self.log.append(("scroll", a))


def registry(boxes=BOXES):
    desktop = Desktop()
    return SkillRegistry(build_desktop_skills(finder_with(boxes), desktop)), desktop


def test_click_by_voice():
    reg, desk = registry()
    assert reg.handle("click on the save button") == "Done."
    assert desk.log == [("click", 860, 515, "left", False)]
    reg.handle("double click save as")
    reg.handle("right click save")
    assert desk.log[1][3:] == ("left", True) and desk.log[2][3:] == ("right", False)


def test_click_something_that_is_not_there():
    reg, desk = registry()
    assert "can't see 'banana'" in reg.handle("click banana")
    assert desk.log == []


def test_risky_click_needs_a_yes():
    reg, desk = registry()
    prompt = reg.handle("click delete")
    assert "Should I click it" in prompt and desk.log == []
    assert reg.awaiting_confirmation
    assert reg.handle("yes") == "Done." and desk.log[0][1:3] == (950, 715)


def test_risky_click_cancelled_by_anything_else():
    reg, desk = registry()
    reg.handle("click delete")
    reg.handle("no")
    reg.handle("yes")
    assert desk.log == []


def test_typing_always_needs_a_yes():
    reg, desk = registry()
    assert "Go ahead" in reg.handle("type hello world")
    assert desk.log == []
    assert reg.handle("yes") == "Typed." and desk.log == [("type", "hello world")]


def test_keys_are_whitelisted():
    reg, desk = registry()
    assert reg.handle("press enter") == "Done."
    assert reg.handle("press page down key") == "Done."
    assert desk.log == [("press", "enter"), ("press", "page down")]
    for phrase in ("press alt f4", "press the windows key", "press ctrl w"):
        reg.handle(phrase)                                    # treated as "click that word": nothing to see
    assert desk.log == [("press", "enter"), ("press", "page down")]


def test_scroll():
    reg, desk = registry()
    reg.handle("scroll down")
    reg.handle("scroll up")
    assert desk.log == [("scroll", -5), ("scroll", 5)]


def test_all_desktop_control_is_refused_from_the_phone():
    reg, desk = registry()
    for phrase in ("click save", "click delete", "type hi", "press enter", "scroll down", "double click save"):
        assert reg.handle(phrase, allow_confirm=False) == reg.REMOTE_REFUSAL, phrase
    assert desk.log == []


def test_unrelated_phrases_pass_through():
    reg, _ = registry()
    for phrase in ("open spotify", "what is the capital of india", "pressure in the cabin", "typewriter history"):
        assert reg.handle(phrase) is None, phrase


# ------------------------------------------------------------------ real OCR

def _find_font():
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(path, 28)
        except OSError:
            continue
    return None


@pytest.mark.skipif(_find_font() is None, reason="no TTF font here")
def test_real_ocr_finds_where_buttons_are():
    pytest.importorskip("rapidocr_onnxruntime")

    image = Image.new("RGB", (1280, 720), "white")
    draw = ImageDraw.Draw(image)
    font = _find_font()
    draw.text((100, 80), "Downloads folder", fill="black", font=font)
    draw.text((900, 600), "Install", fill="black", font=font)
    draw.text((200, 400), "Settings", fill="black", font=font)

    finder = ScreenFinder(grab=lambda: image)
    started = time.perf_counter()
    boxes = finder.boxes()
    elapsed = time.perf_counter() - started
    print(f"\nreal OCR on 1280x720: {elapsed:.2f}s, {len(boxes)} lines")

    install = finder.find("install", boxes)[0]
    assert abs(install.x - 940) < 40 and abs(install.y - 618) < 30
    settings = finder.find("settings", boxes)[0]
    assert abs(settings.x - 270) < 40 and abs(settings.y - 418) < 30
    downloads = finder.find("downloads", boxes)[0]
    assert downloads.x < 250                       # the word "Downloads", not the centre of the line
