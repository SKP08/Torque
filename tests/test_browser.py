import functools
import http.server
import threading
from pathlib import Path

import pytest

from torque.agent.agent import Agent
from torque.agent.browser_tools import BrowserTools, PlaywrightBackend, build_browser_tools, check_url
from torque.agent.file_tools import ToolError

SITE = Path(__file__).parent / "data" / "site"


# ---------------------------------------------------------------- URL rules

@pytest.mark.parametrize("url,expected", [
    ("example.com", "https://example.com"),
    ("http://example.com/a?b=1", "http://example.com/a?b=1"),
    ("https://8.8.8.8/x", "https://8.8.8.8/x"),
])
def test_good_urls(url, expected):
    assert check_url(url) == expected


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "javascript:alert(1)", "ftp://x.com", "http://localhost:8000",
    "http://127.0.0.1/", "http://192.168.1.1/admin", "http://10.0.0.5", "http://169.254.169.254/latest",
    "http://[::1]/", "http://printer.local", "http://nas.lan", "", "   ", "http://",
])
def test_refused_urls(url):
    with pytest.raises(ToolError):
        check_url(url)


# ---------------------------------------------------------------- fake backend (rules only)

class Fake:
    def __init__(self, elements):
        self._elements = elements
        self.log = []

    def goto(self, url): self.log.append(("goto", url))
    def title(self): return "Fake page"
    def url(self): return "https://fake.test/"
    def text(self): return "hello   world\n\nbody"
    def elements(self): return self._elements
    def click(self, i): self.log.append(("click", i))
    def fill(self, i, t): self.log.append(("fill", i, t))
    def press_enter(self, i): self.log.append(("enter", i))
    def scroll(self, dy): self.log.append(("scroll", dy))
    def back(self): self.log.append(("back",))


def element(kind, text, **extra):
    return {"id": str(len(text)), "kind": kind, "text": text, "hint": "", "secret": False, **extra}


def tools_with(*elements):
    fake = Fake(list(elements))
    tools = BrowserTools(fake)
    tools.read_page()
    return tools, fake


@pytest.mark.parametrize("label", ["Buy now", "Pay $20", "Place your order", "Delete account", "Send message",
                                   "Submit", "Sign out", "Confirm purchase", "Add to cart", "Donate", "Subscribe"])
def test_risky_clicks_are_refused(label):
    tools, fake = tools_with(element("button", label))
    with pytest.raises(ToolError, match="won't click"):
        tools.click("1")
    assert ("click", "1") not in fake.log and not any(entry[0] == "click" for entry in fake.log)


@pytest.mark.parametrize("label", ["About us", "Next page", "Read more", "Search", "Pricing", "Sender's guide"])
def test_normal_clicks_work(label):
    tools, fake = tools_with(element("link", label))
    assert "Clicked" in tools.click("1")
    assert any(entry[0] == "click" for entry in fake.log)


def test_secret_and_payment_fields_are_never_typed_into():
    tools, fake = tools_with(element("input", "Password", secret=True),
                             element("input", "Card number", hint="cc-number"),
                             element("input", "CVV"),
                             element("input", "Search"))
    for n in ("1", "2", "3"):
        with pytest.raises(ToolError, match="password or payment"):
            tools.type_text(n, "hunter2")
    assert "Typed" in tools.type_text("4", "cats")
    assert [e for e in fake.log if e[0] == "fill"] == [("fill", "6", "cats")]


def test_element_numbers_are_validated():
    tools = BrowserTools(Fake([element("link", "A")]))
    with pytest.raises(ToolError, match="read_page first"):
        tools.click("1")
    tools.read_page()
    for bad in ("0", "2", "x", ""):
        with pytest.raises(ToolError):
            tools.click(bad)
    assert "Clicked" in tools.click("[1]")


def test_numbers_expire_after_navigation():
    tools, _ = tools_with(element("link", "A"))
    tools.click("1")
    with pytest.raises(ToolError, match="read_page first"):
        tools.click("1")


def test_page_text_is_fenced_as_untrusted_and_bounded():
    tools, _ = tools_with(element("link", "A"))
    out = tools.read_page()
    assert "[untrusted page text begins]" in out and "hello world body" in out
    big = BrowserTools(type("Big", (Fake,), {"text": lambda s: "word " * 5000})([]))
    assert len(big.read_page()) < 2000


def test_type_into_a_non_field_is_an_error():
    tools, _ = tools_with(element("link", "A"))
    with pytest.raises(ToolError, match="not a text field"):
        tools.type_text("1", "x")
    with pytest.raises(ToolError, match="not a text field"):
        tools.press_enter("1")


def test_tools_register_with_the_agent():
    names = {t.name for t in build_browser_tools(BrowserTools(Fake([])))}
    assert names == {"open_url", "web_search", "read_page", "click", "type_text", "press_enter", "scroll", "go_back"}
    for tool in build_browser_tools(BrowserTools(Fake([]))):
        assert tool.schema()["function"]["name"] == tool.name


def test_agent_drives_browser_tools_and_survives_a_refusal():
    tools, fake = tools_with(element("button", "Buy now"))
    chat_steps = iter([
        {"content": "", "tool_calls": [{"function": {"name": "click", "arguments": {"element": "1"}}}]},
        {"content": "I couldn't buy it; that step is yours.", "tool_calls": []},
    ])
    agent = Agent(lambda messages, schema: next(chat_steps), build_browser_tools(tools))
    result = agent.run("buy it")
    assert result.steps[0][2] is False and "won't click" in result.steps[0][3]
    assert "yours" in result.reply and not any(e[0] == "click" for e in fake.log)


def test_redirect_to_a_private_address_is_abandoned():
    fake = Fake([element("link", "A")])
    tools = BrowserTools(fake)
    fake.url = lambda: "http://192.168.1.1/admin"
    with pytest.raises(ToolError, match="local or private"):
        tools.open_url("https://example.com")
    assert ("goto", "about:blank") in fake.log
    fake.log.clear()
    tools.read_page()
    with pytest.raises(ToolError, match="local or private"):
        tools.click("1")
    assert ("goto", "about:blank") in fake.log


# ---------------------------------------------------------------- real browser

@pytest.fixture(scope="module")
def site():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def browser(tmp_path_factory):
    pytest.importorskip("playwright")
    backend = PlaywrightBackend(tmp_path_factory.mktemp("profile"), channel=None, headless=True, timeout_ms=5000)
    try:
        backend.warm()
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"no browser available: {error}")
    yield backend
    backend.close()


def find(text, label):
    for line in text.splitlines():
        if line.startswith("[") and label.lower() in line.lower() and "]" in line[:5]:
            return line[1:line.index("]")]
    raise AssertionError(f"{label!r} not in:\n{text}")


def test_real_browsing_flow(browser, site):
    tools = BrowserTools(browser, allow_private=True)

    assert "Torque Test Home" in tools.open_url(site + "/index.html")
    page = tools.read_page()
    assert "home page of the test site" in page
    assert "About us" in page and "Pricing" in page and "Hidden link" not in page

    assert "About" in tools.click(find(page, "About us"))
    about = tools.read_page()
    assert "Founded in 2026" in about

    assert "Went back" in tools.go_back()
    page = tools.read_page()
    box = find(page, "Search the site")
    tools.type_text(box, "holographic cats")
    tools.press_enter(box)
    results = tools.read_page()
    assert "You searched for: holographic cats" in results
    # injected instructions are visible only as fenced page text
    assert "[untrusted page text begins]" in results


def test_real_page_blocks_risky_actions(browser, site):
    tools = BrowserTools(browser, allow_private=True)
    tools.open_url(site + "/index.html")
    page = tools.read_page()

    with pytest.raises(ToolError, match="won't click"):
        tools.click(find(page, "Buy now"))
    assert browser.title() == "Torque Test Home"                      # the onclick never ran

    with pytest.raises(ToolError):
        tools.type_text(find(page, "Password"), "secret")
    with pytest.raises(ToolError):
        tools.type_text(find(page, "Card number"), "4111111111111111")


def test_real_scroll_reveals_more(browser, site):
    tools = BrowserTools(browser, allow_private=True)
    tools.open_url(site + "/index.html")
    tools.scroll("down")
    assert "Bottom" in tools.read_page()


def test_real_default_blocks_local_addresses(browser, site):
    with pytest.raises(ToolError):
        BrowserTools(browser).open_url(site + "/index.html")


def test_browser_works_from_any_thread(browser, site):
    """Playwright is thread-bound; our backend must hide that."""

    results = []

    def work():
        tools = BrowserTools(browser, allow_private=True)
        tools.open_url(site + "/pricing.html")
        results.append("free" in tools.read_page())

    threads = [threading.Thread(target=work) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [True, True, True]


def test_routing_phrases():
    from torque.agent.router import wants_browser

    yes = ["go to wikipedia.org and read the first paragraph", "browse to github.com", "visit example.com",
           "open the website and click pricing", "use the browser to find the weather"]
    no = ["open spotify", "how do i browse files in python", "what is the capital of india", "close chrome",
          "search for pizza", "go to sleep", "what's in my downloads"]
    assert all(wants_browser(t) for t in yes)
    assert not any(wants_browser(t) for t in no)
