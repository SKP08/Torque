"""
File tools for the agent.

Rules baked in (the model can't talk its way around them):
  - nothing is ever deleted or overwritten; a taken name is an error
  - system folders are read-only
  - unzip refuses paths that escape the target folder ("zip slip") and
    absurdly large archives
  - copy/move/unzip need the destination folder to exist. If it doesn't, the
    error tells the agent to make it first, which is how it "decides" to.
"""

import os
import shutil
import sys
import zipfile
from pathlib import Path

MAX_RESULTS = 8
MAX_ENTRIES = 20_000
MAX_UNZIPPED_BYTES = 5 * 1024**3


class ToolError(Exception):
    """A problem the agent can read and react to."""


def default_protected() -> list[Path]:

    names = ["SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"]
    paths = [Path(os.environ[n]) for n in names if os.environ.get(n)]

    if sys.platform != "win32":
        paths += [Path(p) for p in ("/etc", "/usr", "/bin", "/sbin", "/boot", "/sys", "/proc", "/dev", "/var")]

    return paths


class FileTools:

    def __init__(self, home=None, protected=None):

        self.home = Path(home) if home else Path.home()
        self.protected = [p.resolve() for p in (protected if protected is not None else default_protected())]

    # ---- paths ---------------------------------------------------

    def resolve(self, raw: str) -> Path:
        """Turns "downloads/project.zip", "~/x" or "D:\\Projects" into a real path."""

        if not isinstance(raw, str) or not raw.strip():
            raise ToolError("A path is required.")

        text = os.path.expandvars(raw.strip().strip('"'))

        aliases = {"downloads": "Downloads", "desktop": "Desktop", "documents": "Documents",
                   "pictures": "Pictures", "music": "Music", "videos": "Videos"}

        parts = text.replace("\\", "/").split("/", 1)
        head = parts[0].lower()

        if head in aliases:
            text = str(self.home / aliases[head] / (parts[1] if len(parts) > 1 else ""))
        elif head in ("home", "~"):
            text = str(self.home / (parts[1] if len(parts) > 1 else ""))

        path = Path(text).expanduser()

        if not path.is_absolute():
            path = self.home / path

        return path.resolve()

    def _writable(self, path: Path):

        for blocked in self.protected:
            if path == blocked or blocked in path.parents:
                raise ToolError(f"{path} is a protected system folder. I won't change it.")

    def _existing_folder(self, raw: str, what: str) -> Path:

        path = self.resolve(raw)

        if not path.is_dir():
            raise ToolError(f"The {what} folder {path} doesn't exist. Call make_folder first.")

        self._writable(path)

        return path

    # ---- read-only ----------------------------------------------

    def find_files(self, name: str, folder: str = "") -> str:
        """Newest-first matches for a name fragment under a folder (default: Downloads, Desktop, Documents)."""

        needle = str(name).lower().strip()

        if not needle:
            raise ToolError("A name to look for is required.")

        roots = [self.resolve(folder)] if folder else [self.home / d for d in ("Downloads", "Desktop", "Documents")]

        found = []

        for root in roots:

            if not root.is_dir():
                continue

            for dirpath, dirnames, filenames in os.walk(root):

                dirnames[:] = [d for d in dirnames if not d.startswith(".") and d.lower() not in ("node_modules", "__pycache__")]

                for filename in filenames:

                    if needle in filename.lower():

                        full = Path(dirpath, filename)

                        try:
                            found.append((full.stat().st_mtime, full))
                        except OSError:
                            pass

                if len(found) > 500:
                    break

        if not found:
            return f"No files matching '{name}'."

        found.sort(reverse=True)

        return "\n".join(str(path) for _, path in found[:MAX_RESULTS])

    def list_folder(self, path: str) -> str:

        folder = self.resolve(path)

        if not folder.is_dir():
            raise ToolError(f"{folder} isn't a folder.")

        entries = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))

        if not entries:
            return f"{folder} is empty."

        lines = [f"{'[folder] ' if e.is_dir() else ''}{e.name}" for e in entries[:30]]

        if len(entries) > 30:
            lines.append(f"... and {len(entries) - 30} more")

        return "\n".join(lines)

    # ---- changes (never delete, never overwrite) -----------------

    def make_folder(self, path: str) -> str:

        folder = self.resolve(path)

        self._writable(folder)

        if folder.is_file():
            raise ToolError(f"{folder} is an existing file, not a folder.")

        existed = folder.is_dir()

        folder.mkdir(parents=True, exist_ok=True)

        return f"{folder} already exists." if existed else f"Created {folder}."

    def copy_file(self, source: str, destination_folder: str) -> str:

        src = self.resolve(source)

        if not src.exists():
            raise ToolError(f"{src} doesn't exist.")

        dest_dir = self._existing_folder(destination_folder, "destination")
        target = dest_dir / src.name

        if target.exists():
            raise ToolError(f"{target} already exists. I won't overwrite it.")

        if src.is_dir():
            shutil.copytree(src, target)
        else:
            shutil.copy2(src, target)

        return f"Copied {src.name} to {dest_dir}."

    def move_file(self, source: str, destination_folder: str) -> str:

        src = self.resolve(source)

        if not src.exists():
            raise ToolError(f"{src} doesn't exist.")

        self._writable(src)

        dest_dir = self._existing_folder(destination_folder, "destination")
        target = dest_dir / src.name

        if target.exists():
            raise ToolError(f"{target} already exists. I won't overwrite it.")

        shutil.move(str(src), str(target))

        return f"Moved {src.name} to {dest_dir}."

    def unzip(self, zip_path: str, destination_folder: str) -> str:

        archive = self.resolve(zip_path)

        if not archive.is_file() or archive.suffix.lower() != ".zip":
            raise ToolError(f"{archive} isn't a zip file.")

        dest_dir = self._existing_folder(destination_folder, "destination")

        try:
            with zipfile.ZipFile(archive) as zf:

                infos = zf.infolist()

                if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
                    raise ToolError("That archive is too large to unzip safely.")

                # Extract into a fresh folder named after the zip: no clobbering.
                target = dest_dir / archive.stem

                if target.exists():
                    raise ToolError(f"{target} already exists. I won't overwrite it.")

                for info in infos:

                    member = (target / info.filename).resolve()

                    if target.resolve() != member and target.resolve() not in member.parents:
                        raise ToolError("The archive contains unsafe paths, so I didn't unzip it.")

                zf.extractall(target)

        except zipfile.BadZipFile as error:
            raise ToolError(f"{archive.name} is not a valid zip file.") from error

        return f"Unzipped {archive.name} into {target}."


def build_file_tools(tools: FileTools):
    """The file tools as agent Tool objects (with which parameters are required)."""

    from torque.agent.agent import Tool

    return [
        Tool("find_files",
             "Find files by part of their name. Newest first. Searches Downloads, Desktop and Documents unless a folder is given.",
             {"name": "part of the file name", "folder": "optional folder to search in"},
             tools.find_files, required=("name",)),
        Tool("list_folder", "List what is inside a folder.",
             {"path": "folder path"}, tools.list_folder),
        Tool("make_folder", "Create a folder (and any missing parents).",
             {"path": "folder path to create"}, tools.make_folder),
        Tool("copy_file", "Copy a file or folder into an existing folder. Never overwrites.",
             {"source": "path of the file", "destination_folder": "existing folder to copy into"}, tools.copy_file),
        Tool("move_file", "Move a file or folder into an existing folder. Never overwrites.",
             {"source": "path of the file", "destination_folder": "existing folder to move into"}, tools.move_file),
        Tool("unzip", "Unzip a .zip file into a new folder inside an existing destination folder.",
             {"zip_path": "path of the .zip file", "destination_folder": "existing folder to unzip into"}, tools.unzip),
    ]
