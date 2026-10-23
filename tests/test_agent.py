import json
import zipfile

import pytest

from torque.agent.agent import Agent, Tool
from torque.agent.file_tools import FileTools, ToolError, build_file_tools
from torque.agent.model import AgentModel
from torque.agent.router import wants_agent
from torque.ai.brain import TorqueBrain
from torque.ai.ollama_service import OllamaUnavailableError

from test_brain import FakeContext, FakeLauncher, FakeLLM, FakeMemory, FakeWeb, InlineWorker


# ----------------------------------------------------------------- routing

@pytest.mark.parametrize("text", [
    "unzip my latest download and copy it to D drive in a folder called projects",
    "find the report pdf in my downloads", "move that file to my documents folder",
    "make a folder called school on my desktop", "copy the zip file to the hard disk",
    "where is my resume file",
])
def test_file_tasks_go_to_the_agent(text):
    assert wants_agent(text)


@pytest.mark.parametrize("text", [
    "how do I copy a file in python", "explain what a zip file is", "open my downloads folder",
    "what is the best way to move files in linux", "copy that", "tell me a joke",
    "find me a good restaurant", "move the volume up", "what's the weather",
])
def test_everything_else_is_not(text):
    assert not wants_agent(text)


# ---------------------------------------------------------------- file tools

@pytest.fixture
def home(tmp_path):
    for d in ("Downloads", "Desktop", "Documents"):
        (tmp_path / d).mkdir()
    return tmp_path


@pytest.fixture
def files(home):
    return FileTools(home=home, protected=[home / "Windows"])


def make_zip(path, members):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)


def test_find_files_newest_first_and_aliases(files, home):
    import os, time
    old, new = home / "Downloads" / "report-old.pdf", home / "Documents" / "report-new.pdf"
    old.write_text("a"); new.write_text("b")
    os.utime(old, (time.time() - 1000,) * 2)
    lines = files.find_files("report").splitlines()
    assert lines == [str(new), str(old)]
    assert "No files" in files.find_files("zzz")


def test_resolve_understands_names_the_model_will_use(files, home):
    assert files.resolve("Downloads/a.zip") == home / "Downloads" / "a.zip"
    assert files.resolve("desktop") == home / "Desktop"
    assert files.resolve("~/x") == (home / "x") or files.resolve("~/x").name == "x"


def test_copy_needs_the_destination_to_exist(files, home):
    (home / "Downloads" / "a.txt").write_text("hi")
    with pytest.raises(ToolError, match="Call make_folder first"):
        files.copy_file("Downloads/a.txt", "Documents/Projects")
    files.make_folder("Documents/Projects")
    assert "Copied" in files.copy_file("Downloads/a.txt", "Documents/Projects")
    assert (home / "Documents/Projects/a.txt").read_text() == "hi"
    assert (home / "Downloads/a.txt").exists()          # copy keeps the original


def test_nothing_is_ever_overwritten(files, home):
    (home / "Downloads" / "a.txt").write_text("new")
    (home / "Documents" / "a.txt").write_text("precious")
    with pytest.raises(ToolError, match="won't overwrite"):
        files.copy_file("Downloads/a.txt", "Documents")
    with pytest.raises(ToolError, match="won't overwrite"):
        files.move_file("Downloads/a.txt", "Documents")
    assert (home / "Documents" / "a.txt").read_text() == "precious"
    assert (home / "Downloads" / "a.txt").exists()


def test_move_removes_the_original(files, home):
    (home / "Downloads" / "a.txt").write_text("x")
    files.move_file("Downloads/a.txt", "Desktop")
    assert not (home / "Downloads/a.txt").exists() and (home / "Desktop/a.txt").exists()


def test_protected_folders_are_read_only(files, home):
    (home / "Windows").mkdir()
    (home / "Downloads" / "a.txt").write_text("x")
    for call in (lambda: files.make_folder("Windows/evil"), lambda: files.copy_file("Downloads/a.txt", "Windows")):
        with pytest.raises(ToolError, match="protected"):
            call()


def test_unzip_extracts_into_a_new_folder(files, home):
    make_zip(home / "Downloads" / "proj.zip", {"src/main.py": "print(1)", "README": "hi"})
    files.make_folder("Documents/Projects")
    assert "Unzipped" in files.unzip("Downloads/proj.zip", "Documents/Projects")
    assert (home / "Documents/Projects/proj/src/main.py").read_text() == "print(1)"
    with pytest.raises(ToolError, match="won't overwrite"):
        files.unzip("Downloads/proj.zip", "Documents/Projects")


def test_zip_slip_is_blocked(files, home):
    make_zip(home / "Downloads" / "evil.zip", {"../../escaped.txt": "pwned", "ok.txt": "x"})
    files.make_folder("Documents/Out")
    with pytest.raises(ToolError, match="unsafe paths"):
        files.unzip("Downloads/evil.zip", "Documents/Out")
    assert not (home / "escaped.txt").exists() and not (home.parent / "escaped.txt").exists()
    assert not (home / "Documents/Out/evil").exists()       # nothing extracted at all


def test_non_zip_and_corrupt_zip_are_explained(files, home):
    (home / "Downloads" / "a.txt").write_text("x")
    (home / "Downloads" / "bad.zip").write_text("not a zip")
    files.make_folder("Documents/Out")
    with pytest.raises(ToolError, match="isn't a zip"):
        files.unzip("Downloads/a.txt", "Documents/Out")
    with pytest.raises(ToolError, match="not a valid zip"):
        files.unzip("Downloads/bad.zip", "Documents/Out")


# --------------------------------------------------------------- agent loop

def tools_for(files):
    return build_file_tools(files)


def scripted(*replies):
    """A fake model that returns the given replies in order."""
    queue = list(replies)
    seen = []

    def chat(messages, tools):
        seen.append(messages)
        return queue.pop(0)

    chat.seen = seen
    return chat


def call(tool, /, **args):
    return {"content": "", "tool_calls": [{"function": {"name": tool, "arguments": args}}]}


def say(text):
    return {"content": text, "tool_calls": []}


def test_the_unzip_and_copy_task_with_a_missing_folder(files, home):
    """The headline case: it hits 'folder doesn't exist', makes it, and retries."""
    make_zip(home / "Downloads" / "project.zip", {"a.txt": "hi"})
    chat = scripted(
        call("find_files", name="project"),
        call("unzip", zip_path=str(home / "Downloads/project.zip"), destination_folder="Documents/Projects"),
        call("make_folder", path="Documents/Projects"),
        call("unzip", zip_path=str(home / "Downloads/project.zip"), destination_folder="Documents/Projects"),
        say("I unzipped project.zip into a new Projects folder in Documents."),
    )
    result = Agent(chat, tools_for(files)).run("unzip project into a projects folder")
    assert result.finished and "Projects folder" in result.reply
    assert [(s[0], s[2]) for s in result.steps] == [
        ("find_files", True), ("unzip", False), ("make_folder", True), ("unzip", True)]
    assert (home / "Documents/Projects/project/a.txt").exists()
    # The model was shown the error text so it could adapt.
    assert any("Call make_folder first" in m["content"] for m in chat.seen[2] if m["role"] == "tool")


def test_unknown_tool_and_bad_arguments_are_reported_not_run(files):
    chat = scripted(call("format_disk", drive="C"), call("copy_file", source="x"), say("I couldn't."))
    result = Agent(chat, tools_for(files)).run("do it")
    assert [s[2] for s in result.steps] == [False, False]
    assert "no tool called" in result.steps[0][3] and "Missing argument" in result.steps[1][3]


def test_the_same_failing_call_twice_stops_the_run(files):
    bad = call("copy_file", source="nope.txt", destination_folder="Documents")
    chat = scripted(bad, bad, say("never reached"))
    result = Agent(chat, tools_for(files)).run("copy nope")
    assert not result.finished and result.reply.startswith("I got stuck")
    assert len(chat.seen) == 2


def test_step_limit(files):
    chat = scripted(*[call("list_folder", path="Documents")] * 5)
    result = Agent(chat, tools_for(files), max_steps=3).run("loop forever")
    assert not result.finished and "ran out of steps" in result.reply and len(result.steps) == 3


def test_tool_output_is_truncated_for_the_model(files, home):
    for i in range(200):
        (home / "Documents" / f"{'long' * 20}{i}.txt").write_text("x")
    chat = scripted(call("find_files", name="long", folder="Documents"), say("ok"))
    Agent(chat, tools_for(files)).run("x")
    assert all(len(m["content"]) <= 1500 for m in chat.seen[1] if m["role"] == "tool")


def test_arguments_may_arrive_as_a_json_string(files, home):
    chat = scripted({"content": "", "tool_calls": [{"function": {"name": "list_folder", "arguments": json.dumps({"path": "Documents"})}}]}, say("done"))
    assert Agent(chat, tools_for(files)).run("x").steps[0][2]


def test_empty_final_answer_falls_back_to_the_last_result(files):
    chat = scripted(call("make_folder", path="Desktop/New"), say(""))
    assert "Created" in Agent(chat, tools_for(files)).run("x").reply


def test_progress_callback(files):
    seen = []
    chat = scripted(call("list_folder", path="Desktop"), say("ok"))
    Agent(chat, tools_for(files)).run("x", on_step=seen.append)
    assert seen == ["List what is inside a folder"]


# ------------------------------------------------------------- model adapter

def test_agent_model_normalises_ollama_responses():
    class Fn:  name = "list_folder"; arguments = {"path": "Desktop"}
    class Call: function = Fn()
    class Msg:  content = ""; tool_calls = [Call()]
    class Resp: message = Msg()

    seen = {}
    def chat(**kw):
        seen.update(kw)
        return Resp()

    out = AgentModel("qwen3:4b", chat=chat)([], [])
    assert out == {"content": "", "tool_calls": [{"function": {"name": "list_folder", "arguments": {"path": "Desktop"}}}]}
    assert seen["think"] is False and seen["model"] == "qwen3:4b"


def test_agent_model_failure_becomes_unavailable():
    def chat(**kw): raise ConnectionError("down")
    with pytest.raises(OllamaUnavailableError):
        AgentModel("x", chat=chat)([], [])


# ---------------------------------------------------------------- in the brain

class FakeAgent:
    def __init__(self, reply="Done. I copied it.", error=None):
        self.reply, self.error, self.requests = reply, error, []

    def run(self, request, on_step=None):
        self.requests.append(request)
        if on_step: on_step("Copy a file")
        if self.error: raise self.error
        from torque.agent.agent import AgentResult
        return AgentResult(self.reply)


def brain_with(agent):
    return TorqueBrain(llm=FakeLLM(), web=FakeWeb(), launcher=FakeLauncher(), memory=FakeMemory(),
                       context=FakeContext(), worker=InlineWorker(), skills=False, screen=False, agent=agent)


def test_brain_sends_file_tasks_to_the_agent():
    agent = FakeAgent()
    brain, seen = brain_with(agent), []
    out = list(brain.process_stream([{"role": "user", "content": "copy the zip file to the hard disk"}],
                                    on_status=lambda s, m: seen.append((s, m))))
    assert out[0] == "On it." and "I copied it." in " ".join(out)
    assert seen == [("thinking", "Copy a file...")] and brain.llm.calls == []


def test_brain_chats_normally_when_it_is_not_a_task():
    agent = FakeAgent()
    out = list(brain_with(agent).process_stream([{"role": "user", "content": "how do I copy a file in python"}]))
    assert out == ["LLM reply"] and agent.requests == []


def test_missing_agent_model_gives_a_helpful_message():
    out = " ".join(brain_with(FakeAgent(error=OllamaUnavailableError("model not found"))).process_stream(
        [{"role": "user", "content": "unzip the file in my downloads"}]))
    assert "ollama pull qwen3:4b" in out
