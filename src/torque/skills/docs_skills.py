import json
import re
import threading
from pathlib import Path

from torque.alerts import bus
from torque.skills.base import CONFIRM, SAFE, Skill
from torque.system.system_commands import ActionResult


class FolderList:
    """The folders you asked Torque to read (saved in data/docs_folders.json)."""

    def __init__(self, path):
        self.path = Path(path) if path else None
        self._folders = self._load()

    def _load(self):
        try:
            return [str(f) for f in json.loads(self.path.read_text(encoding="utf-8"))] if self.path else []
        except (OSError, ValueError, AttributeError):
            return []

    def all(self):
        return list(self._folders)

    def add(self, folder):
        folder = str(folder)

        if folder not in self._folders:
            self._folders.append(folder)
            self._save()

    def remove(self, folder):
        if str(folder) in self._folders:
            self._folders.remove(str(folder))
            self._save()

    def _save(self):
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._folders), encoding="utf-8")


def build_docs_skills(index, folders, file_tools, announce=bus.announce, run_async=None):
    """
    index        DocIndex
    folders      FolderList
    file_tools   agent FileTools (path aliases + protected-folder rules)
    run_async    callable(fn) -> starts fn in the background (a thread by default)
    """

    def start(fn):
        if run_async:
            run_async(fn)
        else:
            threading.Thread(target=fn, name="TorqueIndexer", daemon=True).start()

    def resolve(raw):
        raw = re.sub(r"^(?:my|the)\s+", "", raw.strip())
        raw = re.sub(r"\s+folder$", "", raw)

        path = file_tools.resolve(raw)

        for blocked in file_tools.protected:
            if path == blocked or blocked in path.parents:
                raise ValueError("protected")

        if not path.is_dir():
            raise ValueError("missing")

        return path

    def index_job(path):
        try:
            stats = index.index_folder(path)
            total = index.stats()
            announce(f"Finished reading {path.name}. {total['files']} documents are searchable.", "info", True)
        except Exception:  # noqa: BLE001
            announce(f"I couldn't finish reading {path.name}.", "warn", True)

    def index_folder(m):
        try:
            path = resolve(m.group("folder"))
        except ValueError as error:
            return ActionResult(False, "I won't read system folders." if str(error) == "protected"
                                else "I can't find a folder called %s." % re.sub(r"^(?:my|the)\s+", "", m.group("folder").strip()))

        folders.add(path)
        start(lambda: index_job(path))

        return ActionResult(True, f"Reading {path.name} in the background. I'll tell you when it's done.")

    def status(_):
        stats = index.stats()

        if not stats["files"]:
            return ActionResult(True, "I haven't indexed any documents yet.")

        names = ", ".join(Path(f).name for f in folders.all()[:3])

        return ActionResult(True, f"I can search {stats['files']} documents" + (f" from {names}." if names else "."))

    def forget(_):
        index.clear()

        for folder in folders.all():
            folders.remove(folder)

        return ActionResult(True, "Done. I've forgotten all the documents I had read.")

    return [
        # Only clear folder requests: "index my documents", "scan the thesis folder". Never "read my email".
        Skill("docs_index", SAFE, re.compile(
            r"(?:index|scan|read through|study) (?:all )?(?:of )?(?P<folder>(?:my |the )?(?:documents|downloads|desktop|notes))"
            r"(?: folder| directory)?(?: so (?:you can|i can) (?:search|ask)[\w ]*)?$"), index_folder),
        Skill("docs_index_named", SAFE, re.compile(
            r"(?:index|scan|read through|study) (?:all )?(?:of )?(?P<folder>(?:my |the )?[\w .\\/:~-]{2,60}?) (?:folder|directory)$"),
            index_folder),
        Skill("docs_status", SAFE, re.compile(
            r"(?:how many|what) (?:documents?|files?|notes?) (?:have you |did you |are )?(?:indexed|read|searchable)(?: so far)?$|"
            r"what (?:documents?|files?) can you (?:search|read)$"), status),
        Skill("docs_forget", CONFIRM, re.compile(
            r"(?:forget|clear|delete|wipe|erase) (?:all )?(?:my |the )?(?:indexed )?(?:documents?|document index|notes index|index)$"),
            forget, prompt="That makes me forget everything I read from your folders. Are you sure?"),
    ]
