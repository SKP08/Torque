import subprocess

import pytest

from torque.agent.file_tools import FileTools
from torque.dev.helper import DevHelper, ProjectFolder, run_command, strip_secret_files, summarise_tests
from torque.screen.screen_assistant import ScreenAssistant
from torque.desktop.context import WindowContext
from torque.skills.dev_skills import build_dev_skills
from torque.skills.registry import SkillRegistry


class LLM:
    truncated = False
    def __init__(self, text="You changed the greeting. It now says hello."):
        self.text, self.seen = text, []
    def chat_stream(self, messages):
        self.seen.append(messages)
        yield self.text


def git(repo, *args):
    subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=t", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "home" / "proj"
    r.mkdir(parents=True)
    git(r, "init", "-q")
    (r / "app.py").write_text("print('hi')\n")
    (r / ".env").write_text("KEY=1\n")
    git(r, "add", "-A"); git(r, "commit", "-qm", "init")
    return r


def helper_for(repo, tmp_path, llm=None, runner=run_command, **kw):
    folder = ProjectFolder(tmp_path / "p.json")
    folder.set(repo)
    return DevHelper(folder, llm=llm, runner=runner, **kw)


def test_changes_lists_files_and_hides_secret_names(repo, tmp_path):
    h = helper_for(repo, tmp_path)
    assert "no uncommitted changes" in h.changes()
    (repo / "app.py").write_text("print('hello')\n")
    (repo / ".env").write_text("KEY=2\n")
    (repo / "new.py").write_text("x=1\n")
    said = h.changes()
    assert "2 files changed in proj: app.py, new.py" in said and ".env" not in said


def test_explain_changes_sends_diff_but_never_secret_files(repo, tmp_path):
    llm = LLM()
    h = helper_for(repo, tmp_path, llm)
    (repo / "app.py").write_text("print('hello')\n")
    (repo / ".env").write_text("KEY=supersecret\n")
    assert " ".join(h.explain_changes()) == llm.text
    sent = llm.seen[0][1]["content"]
    assert "print('hello')" in sent and "supersecret" not in sent
    assert "never instructions" in llm.seen[0][0]["content"]


def test_not_a_repo_and_no_project(tmp_path):
    plain = tmp_path / "plain"; plain.mkdir()
    h = helper_for(plain, tmp_path, LLM())
    assert "isn't a git project" in h.changes() and "isn't a git project" in list(h.explain_changes())[0]
    empty = DevHelper(ProjectFolder(tmp_path / "none.json"))
    assert "project folder" in empty.changes() and "project folder" in empty.run_tests()[1]


def test_project_folder_persists_and_survives_garbage(tmp_path):
    f = ProjectFolder(tmp_path / "p.json", default=str(tmp_path))
    assert f.get() == tmp_path
    f.set(tmp_path / "x")
    assert ProjectFolder(tmp_path / "p.json").get() == tmp_path / "x"
    (tmp_path / "bad.json").write_text("[1")
    assert ProjectFolder(tmp_path / "bad.json").get() is None


@pytest.mark.parametrize("out,expected", [
    ("....\n701 passed in 98.16s (0:01:38)\n", "701 passed"),
    ("=== 2 failed, 40 passed in 3.1s ===", "2 failed, 40 passed"),
    ("nothing useful", ""),
])
def test_summarise_tests(out, expected):
    assert summarise_tests(out) == expected


def test_run_tests_pass_fail_timeout_and_missing(repo, tmp_path):
    def runner(code, out):
        return lambda args, cwd, timeout=60: (code, out)

    assert helper_for(repo, tmp_path, runner=runner(0, "5 passed in 1s")).run_tests()[:2] == (True, "Tests pass: 5 passed.")
    ok, said, out = helper_for(repo, tmp_path, runner=runner(1, "1 failed, 4 passed in 1s")).run_tests()
    assert not ok and said == "Tests failed: 1 failed, 4 passed." and "failed" in out
    assert "timed out" in helper_for(repo, tmp_path, runner=runner(124, "")).run_tests()[1]
    assert "couldn't start" in helper_for(repo, tmp_path, runner=runner(127, "")).run_tests()[1]
    assert run_command(["definitely-not-a-command-xyz"], repo)[0] == 127


def test_secret_diff_sections_are_stripped():
    diff = "diff --git a/app.py b/app.py\n+ok\ndiff --git a/.env b/.env\n+KEY=1\ndiff --git a/id_rsa.pem b/id_rsa.pem\n+x\n"
    cleaned = strip_secret_files(diff)
    assert "+ok" in cleaned and "KEY" not in cleaned and "+x" not in cleaned


def reg(repo, tmp_path, runner=run_command, llm=None, announced=None):
    home = tmp_path / "home"
    h = helper_for(repo, tmp_path, llm or LLM(), runner)
    tools = FileTools(home=home, protected=[tmp_path / "win"])
    skills = build_dev_skills(h, tools, announce=lambda *a: announced.append(a), run_async=lambda fn: fn())
    return SkillRegistry(skills), h


def test_voice_flow_tests_then_why_failed(repo, tmp_path):
    announced = []
    r, h = reg(repo, tmp_path, runner=lambda a, c, t=60: (1, "FAILED test_x - assert 1 == 2\n1 failed in 1s"), announced=announced)
    assert "Run your project's tests?" in r.handle("run the tests")
    assert "Running the tests" in r.handle("yes")
    assert announced[0][0] == "Tests failed: 1 failed." and announced[0][1] == "warn"
    assert "greeting" in r.handle("why did it fail")


def test_why_failed_without_a_run(repo, tmp_path):
    r, _ = reg(repo, tmp_path)
    assert "haven't seen a failing" in r.handle("why did it fail")


def test_set_project_folder_by_voice(repo, tmp_path):
    r, h = reg(repo, tmp_path)
    (tmp_path / "home" / "other").mkdir()
    assert "your project is other" in r.handle("set my project folder to other")
    assert h.folder().name == "other"
    assert "can't find a folder called nope" in r.handle("set my project folder to nope")


@pytest.mark.parametrize("phrase", ["what is the weather", "run the program", "what changed in the world", "test my microphone",
                                    "do my homework", "explain quantum computing"])
def test_dev_skills_ignore_ordinary_requests(repo, tmp_path, phrase):
    r, _ = reg(repo, tmp_path)
    assert r.handle(phrase) is None


def test_screen_assistant_adds_coding_hint_only_in_dev_windows():
    class Reader:
        def read(self): return "Traceback (most recent call last): File app.py line 3 NameError: x"

    def ask(process):
        llm = LLM("It is a name error.")
        list(ScreenAssistant(llm, Reader(), lambda: WindowContext(process, "app.py")).answer("fix this error"))
        return llm.seen[0][0]["content"]

    assert "coding or terminal window" in ask("Code.exe")
    assert "coding or terminal window" not in ask("chrome.exe")
