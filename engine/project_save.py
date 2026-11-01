"""F3: a Studio project's save as one recoverable transaction (``Project.save`` is its only user).

A save changes several files: an HD-2D room's map file, the changed rooms, the world file and the prefab catalogue
holding the shared player. Each used to be written in turn, so a failure part way left some new and some old. Now:

1. **Serialised first.** Every document is turned into its bytes before any file is touched.
2. **Staged beside each file.** The new bytes go to ``<name>.save-<id>.new``; a file already there is kept as
   ``<name>.save-<id>.original`` (a hard link, or a copy with its time where there are none), checked against it. A file something else changed since
   Studio read it is also kept as ``<name>.outside-change.bak`` (never replacing an earlier, different one). Every
   one of these is created exclusively, never over an existing file (``<id>`` is 128 random bits, but a name already
   taken stops the save, ``temporary_file_exists``, and that file is left alone), and only files this save created
   are ever moved or deleted. A failure here deletes what was staged: no project file was changed.
3. **Committed in order.** Each staged file replaces its target (``os.replace``), after checking the target is still
   the file that was copied (or still absent). If one fails, the ones already replaced are put back from their
   ``.original`` copies (a file that wasn't there before is deleted), and the save fails: the project on disk is as
   it was.
4. **Rollback that can't finish** keeps the ``.original`` copy of each document it couldn't put back and the save
   fails, naming each: ``needs_recovery`` in the report. A file something else changed after this save wrote it
   (its bytes no longer what was written) is never put back over or deleted: it stays as that program wrote it, its
   ``.original`` is kept, and it is a ``needs_recovery`` with ``problem: "changed_after_save"``.

Only once every document is committed is the save a success; then the copies are deleted. Every outcome is a report
(``SaveError.report`` on failure): stage, reason code, message, and what happened to each document.

This recovers from failures Mesh sees (an error, a full disk, a locked file). It is not atomic across a power loss or
a killed process: files are replaced one at a time and nothing is fsynced, so a crash can still leave a mix, with
``.new``/``.original`` files beside them (an ``.original`` is the previous version: keep it until checked).
"""

from __future__ import annotations

import contextlib
import os
import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Callable

from engine import project_ops as ops
from engine.json_io import dumps_stable

Doc = dict[str, Any]


class SaveError(ops.OpError):
    """A save that didn't happen (or only partly: ``report["recovery_required"]``). ``report`` says what and why."""

    def __init__(self, report: Doc) -> None:
        super().__init__(str(report["message"]))
        self.report = report


@dataclass
class _Target:
    rel: str
    kind: str  # map | room | world | prefabs
    data: bytes = b""
    existed: bool = False
    stamp: tuple[int, int] | None = None  # (mtime_ns, size) of the file copied to ``original``
    staged: Path | None = None  # (set only once this save has created it, cleared once it is moved: never another's)
    original: Path | None = None  # (likewise)
    result: str = "not_written"  # not_written | saved | restored | needs_recovery
    problem: str | None = None  # needs_recovery: put_back_failed | changed_after_save
    made_dirs: list[Path] = field(default_factory=list)


def report(stage: str | None, reason: str | None, message: str, targets: list[_Target], root: Path, *,
           backups: list[str] | None = None, leftovers: list[str] | None = None) -> Doc:
    """The save's outcome, for Studio, ``mesh author`` and MCP clients alike (``ok`` when every document saved)."""
    def rel(path: Path) -> str:
        return path.relative_to(root).as_posix()

    recovery = [{"path": t.rel, "problem": t.problem, "original": rel(t.original) if t.existed and t.original else None,
                 "action": _action(t, rel(t.original) if t.existed and t.original else None)}
                for t in targets if t.result == "needs_recovery"]
    return {"ok": stage is None, "stage": stage, "reason": reason, "message": message,
            "documents": [{"path": t.rel, "kind": t.kind, "existed": t.existed, "result": t.result} for t in targets],
            "committed": [t.rel for t in targets if t.result == "saved" or t.problem == "put_back_failed"],
            "restored": [t.rel for t in targets if t.result == "restored"],
            "needs_recovery": recovery, "recovery_required": bool(recovery),
            "outside_change_backups": list(backups or []), "leftovers": list(leftovers or []), "unsaved_edits_kept": True}


def _action(t: _Target, original: str | None) -> str:
    if t.problem == "changed_after_save":
        before = f"the version before this save is in {original}" if original else "it didn't exist before this save"
        return (f"{t.rel} was changed by something else after Mesh wrote it, so it was left as that program wrote "
                f"it; {before}. Keep the one you want")
    return f"copy {original} back over {t.rel}" if original else f"delete {t.rel} (it didn't exist before)"


def refused(reason: str, message: str, documents: list[tuple[str, str]], root: Path) -> SaveError:
    """A save refused before anything was written: a document that can't be saved as it is."""
    targets = [_Target(rel, kind, existed=os.path.lexists(root / rel)) for rel, kind in documents]
    return SaveError(report("validate", reason, message, targets, root))


# --- the file steps (one function each, so tests can make any of them fail) ----------------------------------------
def _create(path: Path, write: Callable[[BinaryIO], object]) -> None:
    """Make ``path``, which must not exist (FileExistsError: someone else's file, untouched), and fill it; a failure
    part way deletes what this call made, and only that."""
    handle = path.open("xb")
    try:
        with handle:
            write(handle)
    except BaseException:
        with contextlib.suppress(OSError):
            path.unlink()
        raise


def _write_new(path: Path, data: bytes) -> None:
    _create(path, lambda handle: handle.write(data))


def _preserve(src: Path, dst: Path) -> None:
    """Keep ``src`` as a new ``dst`` (never over one), with its time: put back, it is the file Studio last saw. A hard
    link (the same file under a second name: nothing copied, and replacing ``src`` leaves it as it is), or on a file
    system without them a copy."""
    try:
        os.link(src, dst)
        return
    except FileExistsError:
        raise
    except OSError:
        pass
    with src.open("rb") as source:
        _create(dst, lambda handle: shutil.copyfileobj(source, handle, 1 << 20))
    shutil.copystat(src, dst)


def _replace(src: Path, dst: Path) -> None:
    os.replace(src, dst)


def _unlink(path: Path) -> None:
    path.unlink()


def _stamp(path: Path) -> tuple[int, int]:
    st = path.stat()
    return st.st_mtime_ns, st.st_size


def _keep_outside_change(target: Path, seen: float | None) -> Path | None:
    """A file something else changed since Studio read it is kept beside it before it is replaced: as
    ``<name>.outside-change.bak``, or ``-2``, ``-3``... when an earlier, different backup is already there."""
    if seen is None or not target.is_file() or target.stat().st_mtime == seen:
        return None
    data, n = target.read_bytes(), 1
    while True:
        backup = target.with_name(f"{target.name}.outside-change{'' if n == 1 else f'-{n}'}.bak")
        try:
            _create(backup, lambda handle: handle.write(data))  # (never over an earlier one)
            return backup
        except FileExistsError:
            if backup.is_file() and not backup.is_symlink() and backup.read_bytes() == data:
                return backup  # (kept already, by a save that didn't finish)
        n += 1


def _discard(path: Path | None, leftovers: list[str], root: Path) -> None:
    if path is None or not os.path.lexists(path):
        return
    try:
        _unlink(path)
    except OSError:
        leftovers.append(path.relative_to(root).as_posix())


def save_documents(root: Path, documents: list[tuple[str, str, Any]], seen: dict[str, float]) -> Doc:
    """Write ``documents`` (``(project-relative path, kind, JSON data)``) as one save; ``seen`` (path -> the mtime Studio
    last read or wrote) is updated for what ends up written. Returns the report; raises SaveError (nothing written,
    or everything put back, or ``recovery_required``)."""
    targets = [_Target(rel, kind) for rel, kind, _doc in documents]
    backups: list[str] = []

    def fail(stage: str, reason: str, message: str, leftovers: list[str] | None = None) -> SaveError:
        return SaveError(report(stage, reason, message, targets, root, backups=backups, leftovers=leftovers))

    for target, (_rel, _kind, doc) in zip(targets, documents):
        try:
            text = dumps_stable(doc)
        except (TypeError, ValueError) as err:
            raise fail("serialize", "serialize_failed", f"{target.rel} couldn't be turned into JSON ({err}); nothing "
                       "was written.") from err
        target.data = (text if text.endswith("\n") else text + "\n").encode("utf-8")

    # Working files are named with 128 random bits, but that isn't what makes them this save's: each is created
    # exclusively (a file already at that name is someone else's, and stops the save untouched) and recorded only
    # once created. Only recorded files are ever moved or deleted.
    token = secrets.token_hex(16)
    leftovers: list[str] = []
    try:
        for target in targets:
            path = root / target.rel
            missing = [p for p in [path.parent, *path.parent.parents] if not p.exists()]
            for folder in reversed(missing):
                folder.mkdir()
                target.made_dirs.append(folder)
            if os.path.lexists(path):
                target.existed, target.stamp = True, _stamp(path)
                backup = _keep_outside_change(path, seen.get(target.rel))
                if backup is not None:
                    backups.append(backup.relative_to(root).as_posix())
                original = path.with_name(f"{path.name}.save-{token}.original")
                _preserve(path, original)
                target.original = original
                if original.stat().st_size != target.stamp[1] or _stamp(path) != target.stamp:
                    raise OSError(f"{target.rel} changed while it was being copied")
            staged = path.with_name(f"{path.name}.save-{token}.new")
            _write_new(staged, target.data)
            target.staged = staged
    except BaseException as err:  # (an interrupt too: what this save made is deleted)
        for each in targets:
            _discard(each.staged, leftovers, root)
            _discard(each.original, leftovers, root)
        _remove_made_dirs(targets)
        if not isinstance(err, Exception):
            raise
        if isinstance(err, FileExistsError):
            taken = err.filename2 or err.filename  # (os.link names the source first)
            raise fail("stage", "temporary_file_exists", f"Preparing {target.rel} failed: {taken} is already "
                       "there and isn't this save's, so it was left as it is; no project file was changed.",
                       leftovers) from err
        raise fail("stage", "stage_failed", f"Preparing {target.rel} failed ({err}); no project file was changed.",
                   leftovers) from err

    failed = targets[0] if targets else None
    try:
        for target in targets:
            failed = target
            path = root / target.rel
            now = _stamp(path) if os.path.lexists(path) else None
            if now != target.stamp:
                raise _Changed(f"{target.rel} was changed by something else during the save")
            assert target.staged is not None
            _replace(target.staged, path)
            target.result, target.staged = "saved", None
    except BaseException as err:  # (an interrupt too: never leave a mix behind silently)
        assert failed is not None
        if failed.result == "not_written" and failed.staged and not os.path.lexists(failed.staged):
            failed.result, failed.staged = "saved", None  # (replaced before the error arrived: put back too)
        _rollback(root, targets, seen)
        for target in targets:
            _discard(target.staged, leftovers, root)
            if target.result == "not_written":
                _discard(target.original, leftovers, root)
        _remove_made_dirs([t for t in targets if t.result in ("not_written", "restored")])
        if not isinstance(err, Exception):
            raise
        reason = "changed_during_save" if isinstance(err, _Changed) else "commit_failed"
        stuck = [t for t in targets if t.result == "needs_recovery"]
        if stuck:
            conflict = any(t.problem == "changed_after_save" for t in stuck)
            raise fail("rollback", "rollback_conflict" if conflict else "rollback_incomplete",
                       _stuck_message(failed.rel, err, targets, stuck, root), leftovers) from err
        done = sum(t.result == "restored" for t in targets)
        raise fail("commit", reason, f"Writing {failed.rel} failed ({err}). Nothing was saved: "
                   + (f"the {done} file(s) already written were put back as they were, so " if done else "")
                   + "the project on disk is as it was before this save.", leftovers) from err

    for target in targets:
        seen[target.rel] = (root / target.rel).stat().st_mtime
        _discard(target.original, leftovers, root)
    return report(None, None, f"Saved {len(targets)} file(s).", targets, root, backups=backups, leftovers=leftovers)


class _Changed(OSError):
    pass


def _holds(path: Path, data: bytes) -> bool:
    """Whether ``path`` is still exactly what this save wrote to it."""
    try:
        return path.is_file() and not path.is_symlink() and path.read_bytes() == data
    except OSError:
        return False


def _rollback(root: Path, targets: list[_Target], seen: dict[str, float]) -> None:
    """Put back each committed document, last first: its ``.original`` copy, or no file if there wasn't one. One that
    something else changed (or removed) after this save wrote it is left as it is, with its ``.original`` kept
    (``changed_after_save``); one that can't be put back is left as written, its copy kept (``put_back_failed``)."""
    for target in reversed(targets):
        if target.result != "saved":
            continue
        path = root / target.rel
        if not _holds(path, target.data):
            if not target.existed and not os.path.lexists(path):
                target.result = "restored"  # (gone again, as it was before this save)
            else:
                target.result, target.problem = "needs_recovery", "changed_after_save"
            continue
        try:
            if target.existed:
                assert target.original is not None
                _replace(target.original, path)
                target.original = None
            else:
                _unlink(path)
            target.result = "restored"
        except OSError:
            target.result, target.problem = "needs_recovery", "put_back_failed"
            if path.is_file():
                seen[target.rel] = path.stat().st_mtime  # (what is there is Studio's own: not an outside change)


def _remove_made_dirs(targets: list[_Target]) -> None:
    for target in targets:
        for folder in reversed(target.made_dirs):
            try:
                folder.rmdir()
            except OSError:
                break


def _stuck_message(rel: str, err: BaseException, targets: list[_Target], stuck: list[_Target], root: Path) -> str:
    restored = [t.rel for t in targets if t.result == "restored"]

    def step(t: _Target) -> str:
        original = t.original.relative_to(root).as_posix() if t.existed and t.original else None
        if t.problem == "changed_after_save":
            return (f"{t.rel} was changed by something else after Mesh wrote it and was left as it is ("
                    + (f"its version before this save is in {original})" if original else "it didn't exist before)"))
        return (f"{t.rel} holds the new version, its previous version is in {original}" if original
                else f"{t.rel} is new (delete it to go back)")

    steps = "; ".join(step(t) for t in stuck)
    return (f"Writing {rel} failed ({err}), and not every file already written could be put back, so the project on "
            f"disk is a mix of old and new files. RECOVERY NEEDED: {steps}."
            + (f" Put back as they were: {', '.join(restored)}." if restored else "")
            + " Saving again once the problem is fixed writes everything.")
