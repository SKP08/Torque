import pytest

from torque.system.app_launcher import AppLauncher, PROTECTED_PROCESSES
from torque.system.app_matcher import AppMatcher
from torque.system.app_registry import AppRegistry
from torque.system.app_scanner import parse_start_apps

NAMES = [
    "7-Zip File Manager", "Audacity", "Calculator", "Discord", "File Explorer",
    "Git Bash", "Google Chrome", "Microsoft Edge", "Notepad", "Spotify",
    "Visual Studio 2022", "Visual Studio Code", "Windows PowerShell",
    "Windows Terminal", "Word",
]


class FakeScanner:
    def scan(self):
        return [{"name": n, "shortcut": "x"} for n in NAMES]


@pytest.fixture
def matcher():
    m = AppMatcher(AppRegistry(FakeScanner()))
    m.load()
    return m


def name(matcher, q):
    app = matcher.match(q)
    return app["name"] if app else None


@pytest.mark.parametrize("query,expected", [
    ("chrome", "Google Chrome"),
    ("Google Chrome", "Google Chrome"),
    ("edge", "Microsoft Edge"),
    ("code", "Visual Studio Code"),
    ("vs code", "Visual Studio Code"),
    ("visual studio", "Visual Studio 2022"),   # shortest prefix match
    ("power shell", "Windows PowerShell"),
    ("explorer", "File Explorer"),
    ("spotifi", "Spotify"),
    ("disc", "Discord"),
    ("calc", "Calculator"),
    ("notepad", "Notepad"),
])
def test_matches(matcher, query, expected):
    assert name(matcher, query) == expected


@pytest.mark.parametrize("query", ["it", "a", "e", "the", "typing", "the door",
                                   "talking to me", "nothing", "", "ab"])
def test_vague_queries_never_match(matcher, query):
    assert matcher.match(query) is None


def test_parse_start_apps():
    out = '[{"Name":"Calculator","AppID":"Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"},{"Name":"","AppID":"x"}]'
    assert parse_start_apps(out) == [
        {"name": "Calculator", "appid": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"}
    ]
    # PowerShell emits a bare object when there is exactly one app.
    assert parse_start_apps('{"Name":"A","AppID":"b"}') == [{"name": "A", "appid": "b"}]
    assert parse_start_apps("garbage") == []


def test_launch_not_found_message(matcher):
    result = AppLauncher(matcher).launch("the door")
    assert not result.success
    assert "couldn't find" in result.message


def test_close_refuses_to_kill_the_desktop(matcher):
    assert "explorer.exe" in PROTECTED_PROCESSES
    result = AppLauncher(matcher).close("file explorer")
    assert not result.success
    assert "won't close" in result.message
