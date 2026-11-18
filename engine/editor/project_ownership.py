"""One writable owner of a project at a time, across processes (#462 R2).

A project open in Mesh Studio holds unsaved work that is in no file. Anything else that writes the project then (a
second Studio, an outside tool writing its files) writes behind it. So whoever writes a project **owns** it while it
does, and there is one owner at a time:

- Mesh Studio (or the legacy editor) owns the project from before it reads its files until it has closed;
- an outside tool writing the files directly (``engine.authoring_session.apply``) owns it for that one write.

**The mechanism** is an operating-system file lock on ``<project>/.mesh/owner.lock``, held on an open file for as
long as the owner lives: ``LockFileEx`` on Windows, ``flock`` elsewhere. Both belong to the open file, so:

- a second owner is refused whether it is another process or another part of this one;
- the lock is gone the moment its process is, however it ended (closed, crashed, killed): nothing is left to clean
  up, and no process id is ever trusted to say whether an owner is alive;
- nothing but the operating system decides it: no bridge, no HTTP, no record that can be overwritten.

The lock file is never deleted (deleting a lock file is itself a race); it stays, a few bytes, with the project.

**Asking** whether a project is owned (``owned``) takes the lock *shared* for an instant: several may ask at once,
and none of them is an owner. An owner being made at that instant would find it taken, so ``acquire`` can wait a
moment (``wait``) before it gives up.

**The note** the owner writes in the lock file (who it is, since when) is for messages only. It is never what
decides anything: an owner's note may be stale, missing or unreadable, and the lock still holds or doesn't.

The live-session record (``live_session_bridge``: ``.mesh/live_session.json``) is how outside tools *talk* to the
editor that owns a project. Only an owner writes or removes it (``EditorLiveSessionBridge.start`` owns the project
first), so a second editor can no longer replace or delete the first one's.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from engine.logging_tools import get_logger

LOCK_RELATIVE_PATH = Path(".mesh") / "owner.lock"
_LOCKED_AT = 1 << 30  # Windows locks a byte range: this byte, far past the note, so the note stays readable
STUDIO, EDITOR, AUTHORING = "mesh_studio", "legacy_editor", "authoring"
EXIT_OPEN_ELSEWHERE = 3  # ``mesh edit``'s exit code when another editor has the project (the launcher says so)
logger = get_logger(__name__)


class OwnedElsewhere(RuntimeError):
    """The project has another owner now. ``holder``: its note (``kind``, ``pid``, ``since``), or {} if unreadable."""

    def __init__(self, root: Path, holder: dict[str, Any]) -> None:
        self.root, self.holder = root, holder
        kind = holder.get("kind")
        if kind == AUTHORING:
            what = "An outside tool is writing this project's files right now. Try again in a moment."
        elif kind == EDITOR:
            what = ("This project is already open in another Mesh editor. Close that one first: a project can be open "
                    "for editing in one place at a time, so that neither overwrites the other's unsaved work.")
        else:
            what = ("This project is already open in Mesh Studio. Use the window that has it: a project can be open "
                    "in one Mesh Studio at a time, so that neither overwrites the other's unsaved work.")
        super().__init__(f"{what} ({root})")


class OwnershipUnavailable(RuntimeError):
    """Whether the project has an owner can't be established here (its ``.mesh`` folder can't be written, or the
    file system has no locks). Nothing is taken as free: the caller refuses."""


def lock_path(root: str | Path) -> Path:
    return Path(root).resolve() / LOCK_RELATIVE_PATH


def _lock(fd: int, *, exclusive: bool) -> bool:
    """Take the lock on ``fd`` now, or say it is taken (False). Never waits."""
    if sys.platform == "win32":
        import ctypes  # noqa: PLC0415
        import msvcrt  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415

        class Overlapped(ctypes.Structure):
            _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p), ("Offset", wintypes.DWORD),
                        ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                        ctypes.POINTER(Overlapped)]
        kernel32.LockFileEx.restype = wintypes.BOOL
        where = Overlapped(Offset=_LOCKED_AT)
        flags = 0x1 | (0x2 if exclusive else 0)  # LOCKFILE_FAIL_IMMEDIATELY | LOCKFILE_EXCLUSIVE_LOCK
        if kernel32.LockFileEx(msvcrt.get_osfhandle(fd), flags, 0, 1, 0, ctypes.byref(where)):
            return True
        code = ctypes.get_last_error()
        if code in (33, 997):  # ERROR_LOCK_VIOLATION, ERROR_IO_PENDING: another holds it
            return False
        raise OSError(code, f"LockFileEx failed (Windows error {code})")
    import fcntl  # noqa: PLC0415

    try:
        fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _note(fd: int) -> dict[str, Any]:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        loaded = json.loads(os.read(fd, 4096).decode("utf-8") or "{}")
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


class Ownership:
    """A project owned: held until ``release`` (or until this process ends, however it ends).

    ``project``: what the lock was the lock of when taken: ``root`` if it was a Mesh project then, else None (a
    folder in no project, or not a project's root). Never rediscovered: a ``config.json`` added or removed since
    doesn't change what this lock covers (``owns``)."""

    def __init__(self, root: Path, kind: str, fd: int, project: Path | None = None) -> None:
        self.root, self.kind, self._fd, self.project = root, kind, fd, project

    @property
    def held(self) -> bool:
        return self._fd >= 0

    def release(self) -> None:
        """Let the project go. Closing the file is what releases the lock; safe to call twice."""
        fd, self._fd = self._fd, -1
        if fd < 0:
            return
        try:
            os.ftruncate(fd, 0)  # (the note: nobody is the owner now)
        except OSError:
            pass  # (the lock is what matters, and closing releases it)
        try:
            os.close(fd)
        except OSError as exc:
            logger.warning("[Mesh][Ownership] closing the lock of %s failed: %s", self.root, exc)

    def owns(self, target: str | Path) -> bool:
        """Whether this lock, still held, covers ``target`` (``in_project`` against the identity captured when it was
        taken). A project that stopped being one, or became one, since: not covered (#462 R4/R5 remediation B)."""
        return self.held and in_project(self.root, target, self.project)

    def __enter__(self) -> Ownership:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def acquire(root: str | Path, kind: str, *, wait: float = 0.0) -> Ownership:
    """Own the project at ``root`` as ``kind`` (STUDIO, EDITOR or AUTHORING), or raise: ``OwnedElsewhere`` if another
    owner has it (after trying for ``wait`` seconds: someone only asking, or a tool's one write, is gone in a
    moment), ``OwnershipUnavailable`` if ownership can't be established here at all."""
    root = Path(root).resolve()
    path = lock_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0))
    except OSError as exc:
        raise OwnershipUnavailable(f"This project can't be opened for editing: its ownership file {path} can't be "
                                   f"made or opened ({exc}).") from exc
    deadline = time.monotonic() + max(0.0, wait)
    try:
        while not _lock(fd, exclusive=True):
            if time.monotonic() >= deadline:
                holder = _note(fd)
                os.close(fd)
                raise OwnedElsewhere(root, holder)
            time.sleep(0.02)
    except OSError as exc:
        os.close(fd)
        raise OwnershipUnavailable(f"This project can't be opened for editing: {path} can't be locked on this "
                                   f"file system ({exc}).") from exc
    try:
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, json.dumps({"kind": kind, "pid": os.getpid(), "since": time.time()}).encode("utf-8"))
    except OSError as exc:  # (the note is for messages: owning the project doesn't depend on it)
        logger.warning("[Mesh][Ownership] the note in %s couldn't be written: %s", path, exc)
    return Ownership(root, kind, fd, root if (root / PROJECT_MARKER).is_file() else None)


def owned(root: str | Path, *, wait: float = 0.25) -> dict[str, Any] | None:
    """Whether the project at ``root`` has an owner now: its note (``kind``, ``pid``, ``since``; {} if unreadable), or
    None if it has none. A project with no lock file has never had one. Raises ``OwnershipUnavailable`` if it can't
    be told. Asks with a shared lock, so it never refuses another asker; an owner being made just now waits for it."""
    path = lock_path(root)
    try:
        fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    except (FileNotFoundError, NotADirectoryError):  # (no lock file, or no folder for one: nothing has owned it)
        return None
    except OSError as exc:
        raise OwnershipUnavailable(f"{path} can't be opened ({exc}).") from exc
    try:
        deadline = time.monotonic() + max(0.0, wait)
        while True:
            try:
                if _lock(fd, exclusive=False):
                    return None  # (closing the file lets the shared lock go)
            except OSError as exc:
                raise OwnershipUnavailable(f"{path} can't be locked on this file system ({exc}).") from exc
            holder = _note(fd)
            if holder or time.monotonic() >= deadline:  # (an owner writes its note at once: no note yet, ask again)
                return holder
            time.sleep(0.02)
    finally:
        os.close(fd)


# ------------------------------------------------------------- whose project a file is (#462 R4/R5 remediation)
PROJECT_MARKER = "config.json"  # a Mesh project's root: what ``mesh edit`` and Mesh Studio open


def project_root(path: str | Path) -> Path | None:
    """The Mesh project ``path`` belongs to: the nearest folder, ``path`` itself or one above it, holding a
    ``config.json``, once ``..``, links and junctions are resolved (``Path.resolve``); None if it is in no project. A
    folder inside a project with a ``config.json`` of its own is a project of its own (nested), with its own owner; any
    other folder inside a project is that project's."""
    target = Path(path).expanduser().resolve()
    return next((folder for folder in (target, *target.parents) if (folder / PROJECT_MARKER).is_file()), None)


def ownership_root(start: str | Path) -> Path:
    """Whose lock a writer working from the folder ``start`` takes: the project ``start`` is in, wherever inside it the
    writer started, so every writer of one project takes one lock. Outside any project (no editor can open it):
    ``start`` itself."""
    folder = Path(start).expanduser().resolve()
    return project_root(folder) or folder


def in_project(root: str | Path, target: str | Path, project: Path | None) -> bool:
    """Whether ``target`` (resolved) is a file of what a lock on ``root`` covers: inside ``root``, and its project now
    (``project_root``) the one the lock was taken as (``project``: ``Ownership.project``, captured then; never
    rediscovered from ``root``). So not in a project nested in it, and not once ``root`` stopped being a project
    (its files are its parent's now) or became one. Writers ask ``Ownership.owns``."""
    owned, resolved = Path(root).resolve(), Path(target).expanduser().resolve()
    return resolved.is_relative_to(owned) and project_root(resolved) == (Path(project).resolve() if project else None)
