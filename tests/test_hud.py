import json
import urllib.error

import pytest

from torque.hud.entities import capitalised_phrases, extract_entities, is_info_question
from torque.hud.info import InfoService
from torque.hud.status import spoken_status, system_status
from torque.hud.wiki import WikiClient, first_sentences

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def summary(title, extract="A place. It is big. It is old.", **extra):
    data = {"type": "standard", "title": title, "description": f"About {title}", "extract": extract}
    data.update(extra)
    return json.dumps(data).encode()


class FakeWeb:
    """Canned Wikipedia: {url substring: bytes | HTTPError}."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, timeout=4.0, limit=2_000_000):
        self.calls.append(url)
        for fragment, result in self.routes.items():
            if fragment in url:
                if isinstance(result, Exception):
                    raise result
                if isinstance(result, tuple):
                    return result
                return result, "application/json"
        raise urllib.error.HTTPError(url, 404, "nf", {}, None)


def not_found(url="x"):
    return urllib.error.HTTPError(url, 404, "nf", {}, None)


DELHI = summary("New Delhi", "New Delhi is the capital of India. It is in the north.",
                thumbnail={"source": "https://upload.wikimedia.org/delhi.jpg"},
                coordinates={"lat": 28.61, "lon": 77.21},
                content_urls={"desktop": {"page": "https://en.wikipedia.org/wiki/New_Delhi"}})
INDIA = summary("India", thumbnail={"source": "https://upload.wikimedia.org/india.png"},
                coordinates={"lat": 21.0, "lon": 78.0})


@pytest.fixture
def web():
    return FakeWeb({
        "summary/New_Delhi": DELHI,
        "summary/India": INDIA,
        "upload.wikimedia.org/delhi.jpg": (PNG, "image/jpeg"),
        "upload.wikimedia.org/india.png": (PNG, "image/png"),
        "summary/Mercury": json.dumps({"type": "disambiguation", "title": "Mercury", "extract": "Mercury may refer to:"}).encode(),
        "summary/Nowhere_Land": not_found(),
        "search/title": json.dumps({"pages": []}).encode(),
    })


@pytest.fixture
def wiki(tmp_path, web):
    return WikiClient(tmp_path / "hud", fetch=web)


# ------------------------------------------------------------------ entities

@pytest.mark.parametrize("text", [
    "what is the capital of india", "who is Elon Musk", "where is the Taj Mahal", "tell me about Mars",
    "how tall is Mount Everest", "who invented the telephone", "what's the population of Canada",
])
def test_info_questions(text):
    assert is_info_question(text)


@pytest.mark.parametrize("text", [
    "what time is it", "what's the weather", "what is my ip", "what's using my cpu", "open chrome",
    "what does this error mean", "tell me a joke", "what is on my screen", "who am i",
])
def test_not_info_questions(text):
    assert not is_info_question(text)


def test_capitalised_phrases():
    assert capitalised_phrases("The capital of India is New Delhi.") == ["India", "New Delhi"]
    assert capitalised_phrases("It was built by Shah Jahan near the Yamuna River.") == ["Shah Jahan", "Yamuna River"]
    assert capitalised_phrases("The Republic of India is large.") == ["Republic of India"]
    assert capitalised_phrases("Sure, it's fine.") == []


def test_answer_entities_come_before_question_entities():
    names = extract_entities("What is the capital of India?", "The capital of India is New Delhi.")
    assert names[:2] == ["India", "New Delhi"] or names[:2] == ["New Delhi", "India"]
    assert set(names[:2]) == {"India", "New Delhi"}


def test_lowercase_question_subject_is_recovered():
    assert "Taj Mahal" in extract_entities("where is the taj mahal", "It is in Agra.")
    assert "Mars" in extract_entities("tell me about mars", "It is a planet.")


def test_filler_words_are_not_entities():
    names = extract_entities("who is he", "He is a famous singer. However it is unclear.")
    assert "He" not in names and "However" not in names


# --------------------------------------------------------------------- wiki

def test_summary_card_and_image_cache(wiki, tmp_path):
    card = wiki.summary("New Delhi")
    assert card["title"] == "New Delhi" and card["lat"] == 28.61
    assert card["image"].startswith("/cache/images/") and card["image"].endswith(".jpg")
    assert (tmp_path / "hud" / card["image"].replace("/cache/", "")).read_bytes() == PNG
    assert card["url"].endswith("New_Delhi")


def test_second_lookup_comes_from_the_cache_even_offline(tmp_path, web):
    WikiClient(tmp_path / "hud", fetch=web).summary("India")
    web.calls.clear()

    def offline(*a, **k): raise OSError("no internet")

    again = WikiClient(tmp_path / "hud", fetch=offline).summary("India")
    assert again["title"] == "India" and web.calls == []


def test_stale_cache_is_used_when_offline_but_refreshed_when_online(tmp_path, web):
    clock = [1000.0]
    client = WikiClient(tmp_path / "hud", fetch=web, clock=lambda: clock[0])
    client.summary("India")
    import os
    path = client._key("India"); os.utime(path, (1000, 1000))

    clock[0] = 1000 + 40 * 86400                                    # 40 days later
    web.calls.clear()
    client.summary("India")
    assert any("summary/India" in c for c in web.calls)             # refreshed

    def offline(*a, **k): raise OSError("down")
    clock[0] += 40 * 86400
    assert WikiClient(tmp_path / "hud", fetch=offline, clock=lambda: clock[0]).summary("India")["title"] == "India"


def test_disambiguation_and_missing_pages_give_nothing(wiki):
    assert wiki.summary("Mercury") is None
    assert wiki.summary("Nowhere Land") is None
    assert wiki.summary("") is None


def test_misses_are_remembered(wiki, web):
    wiki.summary("Nowhere Land")
    web.calls.clear()
    assert wiki.summary("Nowhere Land") is None and web.calls == []


def test_search_fallback_finds_the_right_page(tmp_path):
    web = FakeWeb({"summary/Taj_Mahal_Agra": not_found(),
                   "search/title": json.dumps({"pages": [{"key": "Taj_Mahal", "title": "Taj Mahal"}]}).encode(),
                   "summary/Taj_Mahal": summary("Taj Mahal")})
    assert WikiClient(tmp_path, fetch=web).summary("Taj Mahal Agra")["title"] == "Taj Mahal"


def test_only_wikimedia_images_are_downloaded(tmp_path):
    web = FakeWeb({"summary/Evil": summary("Evil", thumbnail={"source": "https://evil.example/x.png"})})
    card = WikiClient(tmp_path, fetch=web).summary("Evil")
    assert card["image"] is None and not any("evil.example" in c for c in web.calls)


def test_non_image_content_type_is_refused(tmp_path):
    web = FakeWeb({"summary/Page": summary("Page", thumbnail={"source": "https://upload.wikimedia.org/x.png"}),
                   "upload.wikimedia.org": (b"<html>", "text/html")})
    assert WikiClient(tmp_path, fetch=web).summary("Page")["image"] is None


def test_garbage_json_is_survivable(tmp_path):
    web = FakeWeb({"summary/Bad": b"{not json"})
    assert WikiClient(tmp_path, fetch=web).summary("Bad") is None


def test_first_sentences_never_cuts_mid_sentence():
    text = "One is here. Two is here as well. Three goes on for quite a while longer than the others do."
    assert first_sentences(text, 40) == "One is here. Two is here as well."
    assert first_sentences("short", 40) == "short"


# --------------------------------------------------------------------- info

def test_capital_of_india_end_to_end(wiki):
    payload = InfoService(wiki).build("What is the capital of India?", "The capital of India is New Delhi.")
    assert payload["kind"] == "info"
    assert {p["title"] for p in payload["panels"]} == {"India", "New Delhi"}
    assert payload["geo"]["lat"] in (28.61, 21.0)
    assert all(p["text"] for p in payload["panels"])


def test_unresolvable_entities_are_skipped(wiki):
    payload = InfoService(wiki).build("what is mercury", "Mercury is a planet. Nowhere Land is fiction. India is big.")
    assert [p["title"] for p in payload["panels"]] == ["India"]


def test_nothing_resolvable_means_no_hud(wiki):
    assert InfoService(wiki).build("what is it", "It is nice.") is None


def test_offline_with_empty_cache_means_no_hud_not_an_error(tmp_path):
    def offline(*a, **k): raise OSError("no internet")
    assert InfoService(WikiClient(tmp_path, fetch=offline)).build("where is India", "In Asia.") is None


def test_at_most_three_panels_and_no_duplicates(tmp_path):
    routes = {f"summary/{n}": summary(n) for n in ("Alpha", "Beta", "Gamma", "Delta")}
    payload = InfoService(WikiClient(tmp_path, fetch=FakeWeb(routes))).build("who is it", "Alpha, Beta, Gamma and Delta, also Alpha.")
    assert len(payload["panels"]) == 3 and len({p["title"] for p in payload["panels"]}) == 3


def test_prefetch_warms_the_cache(wiki, web):
    service = InfoService(wiki)
    service.prefetch("What is the capital of India?")
    web.calls.clear()
    service.build("What is the capital of India?", "It is New Delhi.")
    assert not any("summary/India" in c for c in web.calls)


# ------------------------------------------------------------------- status

class Probe:
    def top_processes(self, by="cpu", count=3): return [("chrome.exe", 31.0)]


def test_status_numbers_are_sane_on_this_machine():
    status = system_status(probe=Probe())
    assert status["kind"] == "status"
    assert 0 <= status["cpu"] <= 100 and 0 < status["memory"] <= 100
    assert status["top"] == [{"name": "chrome.exe", "cpu": 31}]
    assert status["uptime_hours"] >= 0


def test_spoken_status_wording():
    text = spoken_status({"cpu": 12, "memory": 48, "battery": {"percent": 80, "plugged": True}})
    assert text == "CPU at 12 percent, memory at 48 percent, battery at 80 percent and charging."
    assert "battery" not in spoken_status({"cpu": 1, "memory": 2, "battery": None})


# ------------------------------------------------------------ brain wiring

from torque.ai.brain import TorqueBrain
from torque.skills.hud_skills import build_hud_skills
from torque.skills.registry import SkillRegistry

from test_brain import FakeContext, FakeLauncher, FakeLLM, FakeMemory, FakeWeb as BrainWeb, InlineWorker


class FakeInfo:
    NOTHING = object()

    def __init__(self, payload=None):
        default = {"kind": "info", "title": "India", "panels": [], "geo": None}
        self.payload = None if payload is FakeInfo.NOTHING else (payload or default)
        self.built, self.prefetched = [], []

    def prefetch(self, question): self.prefetched.append(question)

    def build(self, question, answer):
        self.built.append((question, answer))
        return self.payload


def brain(info=None, llm_reply="The capital of India is New Delhi.", skills=False):
    return TorqueBrain(llm=FakeLLM(llm_reply), web=BrainWeb(), launcher=FakeLauncher(), memory=FakeMemory(),
                       context=FakeContext(), worker=InlineWorker(), skills=skills, screen=False, agent=False, info=info)


def run(b, text, **kw):
    huds = []
    out = list(b.process_stream([{"role": "user", "content": text}], on_hud=huds.append, **kw))
    return out, huds


def test_factual_answer_shows_panels_built_from_question_and_answer():
    info = FakeInfo()
    out, huds = run(brain(info), "what is the capital of india")
    assert " ".join(out) == "The capital of India is New Delhi."
    assert huds == [info.payload]
    assert info.built == [("what is the capital of india", "The capital of India is New Delhi.")]
    assert info.prefetched == ["what is the capital of india"]


def test_chit_chat_shows_nothing():
    info = FakeInfo()
    _, huds = run(brain(info, "Ha, good one."), "tell me a joke")
    assert huds == [] and info.built == []


def test_panels_never_delay_or_replace_speech():
    info = FakeInfo(FakeInfo.NOTHING)                     # nothing to show
    out, huds = run(brain(info), "where is the taj mahal")
    assert out and huds == []


def test_phone_requests_get_no_panels():
    info = FakeInfo()
    _, huds = run(brain(info), "what is the capital of india", remote=True)
    assert huds == [] and info.built == []


def test_hud_disabled_is_silent():
    _, huds = run(brain(info=False), "what is the capital of india")
    assert huds == []


def test_status_skill_speaks_and_shows_the_hud():
    data = {"kind": "status", "cpu": 12, "memory": 48, "battery": None}
    registry = SkillRegistry(build_hud_skills(status_fn=lambda: data))
    out, huds = run(brain(skills=registry), "status report")
    assert out == ["CPU at 12 percent, memory at 48 percent."] and huds == [data]
    for phrase in ("how's my pc doing", "run diagnostics", "system status"):
        assert run(brain(skills=registry), phrase)[1] == [data]


def test_dismiss_clears_the_hud():
    registry = SkillRegistry(build_hud_skills(status_fn=lambda: {}))
    for phrase in ("dismiss", "hide the panels", "clear the screen", "close the hud"):
        out, huds = run(brain(skills=registry), phrase)
        assert huds == [{"kind": "clear"}] and out == ["Of course."], phrase


def test_close_that_is_not_confused_with_closing_an_app():
    registry = SkillRegistry(build_hud_skills(status_fn=lambda: {}))
    assert registry.handle("close chrome") is None and registry.handle("close discord please") is None


# ------------------------------------------------------- controller + server

def test_controller_broadcasts_hud_and_clear():
    from test_controller import FakeBrain, FakeManager, FakeSpeech, FakeTTS
    from torque.core.assistant_controller import AssistantController
    from torque.core.conversation_manager import ConversationManager

    sent = []

    class WS:
        def set_message_handler(self, h): self.handler = h
        def send(self, data): sent.append(data)
        def send_level(self, x): pass

    class Manager:
        def get(self, _): return ws
    ws = WS()

    controller = AssistantController(Manager(), brain=FakeBrain(), tts=FakeTTS(),
                                     conversation=ConversationManager(speech=FakeSpeech([])))
    controller._send_hud({"kind": "info", "title": "India"})
    controller.handle_message({"type": "dismiss"})
    shown = [m["hud"] for m in sent if m.get("hud")]
    assert shown and shown[0]["title"] == "India" and 3 <= shown[0]["hold"] <= 60
    assert {"hud": None} in sent


def test_cache_mount_serves_images_and_blocks_traversal(tmp_path):
    import urllib.error, urllib.request
    from torque.ui.static_server import StaticServer

    (tmp_path / "dist").mkdir(); (tmp_path / "dist" / "index.html").write_text("ui")
    (tmp_path / "cache" / "images").mkdir(parents=True)
    (tmp_path / "cache" / "images" / "a.png").write_bytes(PNG)
    (tmp_path / "secret.txt").write_text("secret")

    server = StaticServer(tmp_path / "dist", 0, mounts={"/cache": tmp_path / "cache"})
    assert server.start()

    def get(path):
        try:
            with urllib.request.urlopen(server.url + path, timeout=3) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""

    try:
        assert get("/cache/images/a.png") == (200, PNG)
        assert get("/") == (200, b"ui")
        for evil in ("/cache/../secret.txt", "/cache/%2e%2e/secret.txt", "/cache/images/../../secret.txt", "/cache//etc/passwd"):
            status, body = get(evil)
            assert body != b"secret" and status in (404, 301, 403), evil
    finally:
        server.stop()


def test_status_hud_lists_running_timers():
    from torque.timers.store import TimerStore

    store = TimerStore(None, clock=lambda: 100.0)
    store.add(90, "pasta")
    registry = SkillRegistry(build_hud_skills(status_fn=lambda: {"kind": "status", "cpu": 1, "memory": 2,
                                                                  "battery": None, "disk": None}, timers=store))
    huds = []
    registry.handle("status report", hud=huds.append)
    assert huds[0]["timers"] == [{"label": "pasta", "seconds": 90}]
