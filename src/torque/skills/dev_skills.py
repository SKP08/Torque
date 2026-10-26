"""Voice skills for the coding sidekick (see torque.dev.helper)."""

import re
import threading

from torque.alerts import bus
from torque.skills.base import CONFIRM, SAFE, Skill
from torque.system.system_commands import ActionResult


def build_dev_skills(helper, file_tools, announce=bus.announce, run_async=None):

    def start(fn):
        if run_async:
            run_async(fn)
        else:
            threading.Thread(target=fn, name="TorqueTests", daemon=True).start()

    def set_folder(m):
        raw = re.sub(r"^(?:my|the)\s+", "", m.group("folder").strip())

        try:
            path = file_tools.resolve(raw)
        except Exception:  # noqa: BLE001
            path = None

        if not path or not path.is_dir():
            return ActionResult(False, f"I can't find a folder called {raw}.")

        for blocked in file_tools.protected:
            if path == blocked or blocked in path.parents:
                return ActionResult(False, "I won't work in system folders.")

        helper.project.set(path)

        return ActionResult(True, f"Okay, your project is {path.name}.")

    def tests(_):
        if not helper.folder():
            return ActionResult(False, helper.NO_PROJECT)

        def job():
            ok, spoken, output = helper.run_tests()
            announce(spoken, "info" if ok else "warn", True)

            if not ok and output and helper.llm:
                announce("Say 'why did it fail' and I'll explain.", "info", False)
                helper.last_failure = output

        start(job)

        return ActionResult(True, "Running the tests. I'll tell you when they finish.")

    def why_failed(_):
        output = getattr(helper, "last_failure", "")

        if not output:
            return ActionResult(False, "I haven't seen a failing test run yet. Ask me to run the tests first.")

        return ActionResult(True, " ".join(helper.explain_failure(output)) or "I couldn't work out why it failed.")

    return [
        Skill("dev_set_project", SAFE,
              re.compile(r"(?:set|change|switch) (?:my |the )?(?:project|code|working) (?:folder|directory|repo|repository)(?: to)? (?P<folder>.{2,60})$"),
              set_folder),
        Skill("dev_changes", SAFE,
              re.compile(r"(?:what(?:'s| is| has) (?:changed|new)|which files (?:did i|have i) (?:change|changed|edit|edited)|git status)(?: in (?:my )?(?:project|code|repo))?$"),
              lambda _: ActionResult(True, helper.changes())),
        Skill("dev_explain_changes", SAFE,
              re.compile(r"(?:explain|summari[sz]e|describe|review) (?:my |the )?(?:changes|diff|uncommitted (?:changes|work)|work in progress)$|what did i (?:change|do|work on)(?: today| so far)?$"),
              lambda _: ActionResult(True, " ".join(helper.explain_changes()))),
        Skill("dev_run_tests", CONFIRM,
              re.compile(r"(?:run|start|do) (?:my |the |all )?(?:project |unit )?tests(?: now)?$|(?:do )?(?:my )?tests pass$"),
              tests, prompt="Run your project's tests?"),
        Skill("dev_why_failed", SAFE,
              re.compile(r"why (?:did|do) (?:it|they|the tests?) fail(?:ed)?$|explain (?:the )?(?:test )?failures?$"),
              why_failed),
    ]
