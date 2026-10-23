import pytest
from PIL import Image, ImageDraw, ImageFont

from torque.ai.brain import TorqueBrain
from torque.screen.screen_assistant import ScreenAssistant, is_screen_request
from torque.screen.screen_reader import OcrUnavailableError, ScreenReader, lines_to_text

from test_brain import FakeContext, FakeLauncher, FakeLLM, FakeMemory, FakeWeb, InlineWorker


@pytest.mark.parametrize("text", [
    "What's on my screen?", "what am I looking at", "explain this error",
    "Hey Torque, what does this error mean?", "summarize this page", "read my screen",
    "why am I getting this error", "what's wrong with this", "explain this", "translate this page",
])
def test_screen_requests_are_recognised(text):
    assert is_screen_request(text)


@pytest.mark.parametrize("text", [
    "what is a screen reader", "open my screen saver settings", "explain recursion",
    "what's the weather", "describe your day", "what does TCP mean", "how do I fix a flat tire",
])
def test_other_questions_are_not(text):
    assert not is_screen_request(text)


class FakeOcr:
    def __init__(self, lines): self.lines = lines
    def read(self, image): return self.lines


def reader(lines, size=(800, 600)):
    return ScreenReader(grab=lambda: Image.new("RGB", size), ocr=FakeOcr(lines))


def test_reading_order_is_rows_top_to_bottom_left_to_right():
    lines = [(300, 100, 20, "world"), (10, 102, 20, "hello"), (10, 300, 20, "second row")]
    assert lines_to_text(lines) == "hello world\nsecond row"


def test_large_screens_are_shrunk_before_ocr():
    sizes = []

    class Spy:
        def read(self, image):
            sizes.append(image.size)
            return []

    ScreenReader(grab=lambda: Image.new("RGB", (3840, 2160)), ocr=Spy()).read()
    assert sizes == [(1920, 1080)]


def ask(assistant, text="explain this error"):
    return list(assistant.answer(text))


def test_answer_streams_from_the_local_model_with_screen_text():
    llm = FakeLLM("The file is missing. Check the path.")
    assistant = ScreenAssistant(llm, reader([(0, 0, 20, "FileNotFoundError: no such file 'data.csv'")]))
    out = ask(assistant)
    assert out[0] == "Let me take a look."
    assert " ".join(out[1:]) == "The file is missing. Check the path."
    prompt = llm.calls[0]
    assert "FileNotFoundError" in prompt[1]["content"]
    assert "never instructions" in prompt[0]["content"]


def test_empty_screen_does_not_call_the_model():
    llm = FakeLLM()
    assert "can't see any readable text" in " ".join(ask(ScreenAssistant(llm, reader([]))))
    assert llm.calls == []


def test_missing_ocr_is_explained():
    class Missing:
        def read(self, image): raise OcrUnavailableError("Screen reading needs the OCR add-on: run uv sync --extra screen.")

    out = ask(ScreenAssistant(FakeLLM(), ScreenReader(grab=lambda: Image.new("RGB", (10, 10)), ocr=Missing())))
    assert "uv sync --extra screen" in out[-1]


def test_screen_failures_are_spoken_not_raised():
    def boom(): raise OSError("no display")
    out = ask(ScreenAssistant(FakeLLM(), ScreenReader(grab=boom, ocr=FakeOcr([]))))
    assert out[-1] == "I couldn't read the screen."


def test_brain_routes_screen_questions_and_reports_status():
    assistant = ScreenAssistant(FakeLLM("It is a syntax error."), reader([(0, 0, 20, "SyntaxError: invalid syntax here")]))
    brain = TorqueBrain(
        llm=FakeLLM(), web=FakeWeb(), launcher=FakeLauncher(), memory=FakeMemory(),
        context=FakeContext(), worker=InlineWorker(), skills=False, screen=assistant, agent=False,
    )
    seen = []
    out = list(brain.process_stream([{"role": "user", "content": "what does this error mean"}],
                                    on_status=lambda s, m: seen.append((s, m))))
    assert "It is a syntax error." in " ".join(out)
    assert seen == [("thinking", "Looking at your screen...")]
    assert brain.llm.calls == []          # the chat model wasn't used for normal chat


def test_real_ocr_reads_rendered_text():
    pytest.importorskip("rapidocr_onnxruntime")
    image = Image.new("RGB", (900, 200), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 44)
    except OSError:
        pytest.skip("no font")
    draw.text((20, 20), "FileNotFoundError", fill="black", font=font)
    draw.text((20, 100), "No such file data.csv", fill="black", font=font)
    text = ScreenReader(grab=lambda: image).read()
    assert "FileNotFoundError" in text and "data.csv" in text
