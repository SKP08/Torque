"""
Voice routines: a name for a list of things you'd normally say one by one.

    "create a routine called work mode that opens vscode and spotify and sets volume to 30"
    "start work mode"            "run the study routine"
    "what routines do I have"    "delete the study routine"

Each step is run exactly as if you had said it, through the same skills and app
commands, so every safety rule still applies (confirmations are never answered
for you: a step that would need one is skipped and reported).
"""

import json
import os
import re
import threading
import time
from pathlib import Path

from torque.skills.base import CONFIRM, SAFE, Skill
from torque.system.system_commands import ActionResult

MAX_STEPS = 12
MAX_ROUTINES = 30

_SPLIT = re.compile(r"\s*(?:,\s*then|,\s*and then|\band then\b|\bthen\b|,|\band\b)\s*")


def clean_name(name: str) -> str:
    name = re.sub(r"\b(?:the|my|a|routine|mode)\b", " ", (name or "").lower())

    return re.sub(r"\s+", " ", name).strip()


def split_steps(text: str) -> list:
    steps = [s.strip() for s in _SPLIT.split(text or "") if s.strip()]

    # "opens vscode" -> "open vscode": people describe, the skills expect commands
    return [re.sub(r"^(opens|closes|starts|launches|sets|plays|mutes|turns)\b",
                   lambda m: m.group(1)[:-1] if m.group(1) != "closes" else "close", s) for s in steps]


class RoutineStore:

    def __init__(self, path):
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self):
        if not self.path or not self.path.exists():
            return {}

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {k: [str(s) for s in v] for k, v in data.items() if isinstance(v, list)}
        except (OSError, ValueError, AttributeError):
            return {}

    def _save(self):
        if not self.path:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def names(self):
        with self._lock:
            return sorted(self._data)

    def get(self, name):
        with self._lock:
            return list(self._data.get(name, [])) or None

    def put(self, name, steps):
        with self._lock:
            if name not in self._data and len(self._data) >= MAX_ROUTINES:
                raise ValueError("too many routines")

            self._data[name] = list(steps)
            self._save()

    def delete(self, name) -> bool:
        with self._lock:
            removed = self._data.pop(name, None) is not None
            self._save()

        return removed


def build_routine_skills(store, runner, pause=0.4, sleep=time.sleep):
    """
    runner(step_text) -> reply string if some skill/command handled it, else None.
    """

    running = threading.Lock()

    def _is_routine_phrase(step):
        return any(p.match(step) for p in (_RUN_A, _RUN_B, _CREATE, _DELETE_A, _DELETE_B))

    def run(m):
        name = clean_name(m.group("name"))
        steps = store.get(name)

        if not steps:
            return ActionResult(False, f"I don't have a routine called {name}.") if name else None

        if not running.acquire(blocking=False):
            return ActionResult(False, "A routine is already running.")

        done, skipped = 0, []

        try:
            for step in steps:
                if _is_routine_phrase(step):
                    skipped.append(step)
                    continue

                reply = runner(step)

                if reply is None or reply == "That one needs you at the PC.":
                    skipped.append(step)
                else:
                    done += 1

                sleep(pause)

        finally:
            running.release()

        if not skipped:
            return ActionResult(True, f"{name.title()} is running. {done} step{'s' if done != 1 else ''} done.")

        return ActionResult(True, f"{done} of {len(steps)} steps done. "
                                  f"I couldn't do: {', '.join(skipped[:3])}.")

    def create(m):
        name = clean_name(m.group("name"))
        steps = split_steps(m.group("steps"))

        if not name:
            return ActionResult(False, "What should the routine be called?")

        if not steps:
            return ActionResult(False, "What should the routine do?")

        if len(steps) > MAX_STEPS:
            return ActionResult(False, f"That's too many steps. The limit is {MAX_STEPS}.")

        if any(_is_routine_phrase(s) for s in steps):
            return ActionResult(False, "A routine can't start other routines.")

        try:
            store.put(name, steps)
        except ValueError:
            return ActionResult(False, "You have too many routines already. Delete one first.")

        return ActionResult(True, f"Saved {name}: {len(steps)} step{'s' if len(steps) != 1 else ''}. "
                                  f"Say start {name} to run it.")

    def listing(_):
        names = store.names()

        if not names:
            return ActionResult(True, "You have no routines yet.")

        return ActionResult(True, "You have " + ", ".join(names[:6]) + ".")

    def delete(m):
        name = clean_name(m.group("name"))

        return ActionResult(True, f"Deleted {name}.") if store.delete(name) \
            else ActionResult(False, f"I don't have a routine called {name}.")

    return [
        Skill("routine_create", SAFE, _CREATE, create),
        Skill("routine_list", SAFE, re.compile(
            r"(?:what|which|list|show)(?: are)?(?: my| the)? routines?(?: do i have)?$|list (?:all )?(?:my )?routines$"), listing),
        Skill("routine_delete", CONFIRM, _DELETE_A, delete, prompt="Delete that routine?"),
        Skill("routine_delete_b", CONFIRM, _DELETE_B, delete, prompt="Delete that routine?"),
        Skill("routine_run", SAFE, _RUN_A, run),
        Skill("routine_run_b", SAFE, _RUN_B, run),
    ]


_NAME = r"(?P<name>[a-z0-9][a-z0-9 ]{0,30}?)"

_CREATE = re.compile(
    rf"(?:create|make|save|add|teach me|set up|define) (?:a |an |new )*(?:new )?routine (?:called |named |for )?{_NAME} "
    r"(?:that|which|to|with|where you)\s+(?P<steps>.+)$"
)

# The word "routine" (or "mode" for starting) is required, so "delete the report" is never a routine command.
_DELETE_A = re.compile(rf"(?:delete|remove|forget) (?:the |my )?routine {_NAME}$")
_DELETE_B = re.compile(rf"(?:delete|remove|forget) (?:the |my )?{_NAME} routine$")
_RUN_A = re.compile(rf"(?:start|run|activate|begin|launch|enable|go into|switch to) (?:the |my )?routine {_NAME}$")
_RUN_B = re.compile(rf"(?:start|run|activate|begin|launch|enable|go into|switch to) (?:the |my )?{_NAME} (?:routine|mode)$")

_RUN = _RUN_B                      # for the "is this a routine phrase?" check below
_DELETE = _DELETE_B
