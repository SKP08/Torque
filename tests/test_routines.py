import pytest

from torque.skills.registry import SkillRegistry
from torque.skills.routine_skills import RoutineStore, build_routine_skills, clean_name, split_steps


def make(tmp_path=None, known=("open vscode", "open spotify", "set volume to 30", "close discord")):
    ran = []

    def runner(step):
        ran.append(step)
        return "ok" if step in known else None

    store = RoutineStore(tmp_path / "r.json" if tmp_path else None)
    registry = SkillRegistry(build_routine_skills(store, runner, pause=0, sleep=lambda s: None))
    return registry, store, ran


def test_split_steps_and_normalisation():
    assert split_steps("opens vscode, then opens spotify and sets volume to 30") == \
        ["open vscode", "open spotify", "set volume to 30"]
    assert split_steps("") == []


def test_clean_name():
    assert clean_name("the work mode") == "work" and clean_name("my study routine") == "study"
    assert clean_name("deep focus") == "deep focus"


def test_create_run_list_delete_by_voice(tmp_path):
    reg, store, ran = make(tmp_path)

    said = reg.handle("create a routine called work mode that opens vscode and opens spotify and sets volume to 30")
    assert said.startswith("Saved work: 3 steps") and store.get("work") == ["open vscode", "open spotify", "set volume to 30"]

    assert "3 steps done" in reg.handle("start work mode")
    assert ran == ["open vscode", "open spotify", "set volume to 30"]

    assert "work" in reg.handle("what routines do I have")

    assert reg.handle("delete the work routine") == "Delete that routine?"
    assert reg.handle("yes") == "Deleted work." and store.get("work") is None
    assert "don't have a routine called work" in reg.handle("run the work routine")


def test_routines_survive_a_restart(tmp_path):
    reg, _, _ = make(tmp_path)
    reg.handle("make a routine called study that opens vscode")
    again, store, ran = make(tmp_path)
    assert store.get("study") == ["open vscode"]
    again.handle("run the study routine")
    assert ran == ["open vscode"]


def test_unknown_steps_are_reported_not_hidden():
    reg, store, ran = make()
    reg.handle("create a routine called focus that opens vscode and does a barrel roll and closes discord")
    said = reg.handle("start focus mode")
    assert said.startswith("2 of 3 steps done") and "does a barrel roll" in said
    assert ran == ["open vscode", "does a barrel roll", "close discord"]


def test_a_step_needing_confirmation_is_skipped_for_phone_style_refusal():
    store = RoutineStore(None)
    store.put("night", ["shut down", "open vscode"])
    reg = SkillRegistry(build_routine_skills(
        store, lambda s: "That one needs you at the PC." if s == "shut down" else "ok", pause=0, sleep=lambda x: None))
    assert reg.handle("start night mode").startswith("1 of 2 steps done")


def test_routines_cannot_nest_or_loop():
    reg, store, _ = make()
    assert "can't start other routines" in reg.handle("create a routine called loop that starts work mode")
    store.put("sneaky", ["start sneaky mode", "open vscode"])
    said = reg.handle("start sneaky mode")
    assert "1 of 2 steps done" in said


def test_limits():
    reg, store, _ = make()
    steps = " and ".join(f"open app{i}" for i in range(13))
    assert "too many steps" in reg.handle(f"create a routine called big that does {steps}")
    for i in range(30):
        store.put(f"r{i}", ["x"])
    assert "too many routines" in reg.handle("create a routine called one more that opens vscode")


def test_ordinary_requests_are_not_hijacked():
    reg, _, _ = make()
    for phrase in ("delete the report", "start spotify", "run chrome", "open work mode folder",
                   "delete my files", "what time is it", "go into the settings"):
        assert reg.handle(phrase) is None, phrase


def test_corrupt_file_is_ignored(tmp_path):
    (tmp_path / "r.json").write_text("{nope")
    assert RoutineStore(tmp_path / "r.json").names() == []
