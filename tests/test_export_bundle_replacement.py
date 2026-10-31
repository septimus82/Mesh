"""F4 (#422): an export that fails never costs the creator their last good export.

``build_bundle`` builds the new bundle in ``.<name>~new`` beside the output folder, checks it, and only then swaps it
in (the earlier one to ``.<name>~old``, the new one to ``<name>``, the earlier one deleted). Every failure below must
leave either the earlier export where it was, or both copies kept and named; an export stopped between the two
renames is recovered by the next one. Only an empty folder or an earlier bundle is ever replaced.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from engine.tooling import export_bundle as eb
from engine.tooling.export_bundle import build_bundle

pytestmark = [pytest.mark.integration]

FIXTURE = Path(__file__).parent / "fixtures" / "export_bundle"
ROOT = Path(__file__).resolve().parents[1]


def _tree(folder: Path) -> dict[str, str]:
    """Every file under ``folder`` (relative path: sha256)."""
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A copy of the export fixture with a ``main.py`` (so the bundle ships Python source)."""
    root = tmp_path / "repo"
    shutil.copytree(FIXTURE, root)
    (root / "main.py").write_text("print('game')\n", encoding="utf-8")
    return root


@pytest.fixture
def previous(repo: Path, tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """An earlier, successful export (at ``out/bundle``) and its exact contents; the source then changes, so a
    replacement would differ from it."""
    out = tmp_path / "out" / "bundle"
    assert build_bundle(repo, out)[0] == 0
    (repo / "scenes" / "scene_a.json").write_text('{"changed": true}\n', encoding="utf-8")
    return out, _tree(out)


def _leftovers(out: Path) -> list[str]:
    """What an export left beside ``out`` (its ``.<name>~new``, ``.<name>~old``, ``.<name>~export.json``)."""
    return sorted(p.name for p in out.parent.iterdir() if p.name.startswith(f".{out.name}~"))


def _fail_on(monkeypatch: pytest.MonkeyPatch, name: str, *, after: int = 0,
             exc: BaseException | None = None) -> list[int]:
    """Make ``eb.<name>`` raise (OSError by default) from its ``after``-th call on; returns the call counter."""
    real: Callable[..., object] = getattr(eb, name)
    calls = [0]

    def failing(*args: object, **kwargs: object) -> object:
        calls[0] += 1
        if calls[0] > after:
            raise exc if exc is not None else OSError(f"injected failure in {name}")
        return real(*args, **kwargs)

    monkeypatch.setattr(eb, name, failing)
    return calls


# --------------------------------------------------------------------------- #
# 1-3: a failure while building the new bundle leaves the earlier one untouched
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("after", [0, 4], ids=["first file", "a later file after partial progress"])
def test_a_failed_copy_leaves_the_earlier_export_as_it_was(repo: Path, previous: tuple[Path, dict[str, str]],
                                                           monkeypatch: pytest.MonkeyPatch, after: int,
                                                           capsys: pytest.CaptureFixture[str]) -> None:
    out, before = previous
    calls = _fail_on(monkeypatch, "_copy_checked", after=after)
    assert build_bundle(repo, out) == (1, None)
    assert calls[0] == after + 1
    assert _tree(out) == before and _leftovers(out) == []
    assert "Failed to copy" in capsys.readouterr().out


@pytest.mark.parametrize("stage", ["writing the manifest", "reading it back", "a copied file's size"])
def test_a_failed_manifest_or_check_leaves_the_earlier_export_as_it_was(
        repo: Path, previous: tuple[Path, dict[str, str]], monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
    out, before = previous
    if stage == "writing the manifest":
        _fail_on(monkeypatch, "_write_manifest")
    elif stage == "reading it back":
        monkeypatch.setattr(eb, "load_bundle_manifest", lambda _folder: None)
    else:
        real = eb._write_manifest

        def truncate_then_write(path: Path, manifest: eb.BundleManifest) -> None:
            (path.parent / "main.py").write_text("", encoding="utf-8")
            real(path, manifest)

        monkeypatch.setattr(eb, "_write_manifest", truncate_then_write)
    assert build_bundle(repo, out) == (1, None)
    assert _tree(out) == before and _leftovers(out) == []


def test_a_source_file_changed_mid_export_stops_it(repo: Path, previous: tuple[Path, dict[str, str]],
                                                   monkeypatch: pytest.MonkeyPatch,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    out, before = previous
    real = eb.compute_export_plan

    def plan_then_edit(*args: Any, **kwargs: Any) -> eb.ExportPlan:
        plan = real(*args, **kwargs)
        (repo / "scenes" / "scene_b.json").write_text('{"saved": "mid-export"}\n', encoding="utf-8")
        return plan

    monkeypatch.setattr(eb, "compute_export_plan", plan_then_edit)
    assert build_bundle(repo, out) == (1, None)
    assert _tree(out) == before and _leftovers(out) == []
    assert "scenes/scene_b.json changed while it was exported" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# 4-5: publication, rollback and cleanup
# --------------------------------------------------------------------------- #

def _label(path: str | Path) -> str:
    """A folder's name, or ``<working folder>/b`` for the bundle inside one."""
    path = Path(path)
    return f"{path.parent.name}/b" if path.name == "b" else path.name


def _rename_failing(monkeypatch: pytest.MonkeyPatch, *fail: tuple[str, str], exc: BaseException | None = None) -> None:
    """``os.rename`` failing for the (source, destination) pairs given (as ``_label`` names them), each every time."""
    real = os.rename

    def rename(src: str | Path, dst: str | Path) -> None:
        if (_label(src), _label(dst)) in fail:
            raise exc if exc is not None else PermissionError(13, "injected: in use", str(src))
        real(src, dst)

    monkeypatch.setattr(os, "rename", rename)
    monkeypatch.setattr(eb.time, "sleep", lambda _s: None)


def test_moving_the_earlier_export_aside_fails_and_it_stays(repo: Path, previous: tuple[Path, dict[str, str]],
                                                           monkeypatch: pytest.MonkeyPatch,
                                                           capsys: pytest.CaptureFixture[str]) -> None:
    out, before = previous
    _rename_failing(monkeypatch, ("bundle", ".bundle~old/b"))
    assert build_bundle(repo, out) == (1, None)
    assert _tree(out) == before and _leftovers(out) == []
    assert "is the game running from" in capsys.readouterr().out


def test_a_failed_handover_puts_the_earlier_export_back(repo: Path, previous: tuple[Path, dict[str, str]],
                                                        monkeypatch: pytest.MonkeyPatch,
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    out, before = previous
    _rename_failing(monkeypatch, (".bundle~new/b", "bundle"))
    assert build_bundle(repo, out) == (1, None)
    assert _tree(out) == before and _leftovers(out) == []
    assert f"the earlier export is back in {out}" in capsys.readouterr().out


def test_when_the_rollback_fails_too_both_copies_are_kept_and_named(
        repo: Path, previous: tuple[Path, dict[str, str]], monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    out, before = previous
    _rename_failing(monkeypatch, (".bundle~new/b", "bundle"), (".bundle~old/b", "bundle"))
    assert build_bundle(repo, out) == (1, None)
    staging, backup = out.with_name(".bundle~new") / "b", out.with_name(".bundle~old") / "b"
    message = capsys.readouterr().out
    assert f"the earlier export is in {backup}, the new one in {staging}" in message
    assert not out.exists() and _tree(backup) == before, "the earlier export, whole, where the message says"
    assert eb.load_bundle_manifest(staging) is not None and not eb._bundle_problems(staging), "the new one, complete"
    # The next export puts the earlier one back first, then replaces it as usual.
    monkeypatch.undo()
    assert build_bundle(repo, out)[0] == 0
    assert "restored the previous export" in capsys.readouterr().out
    assert _leftovers(out) == [] and _tree(out)["scenes/scene_a.json"] != before["scenes/scene_a.json"]


def test_a_failed_cleanup_keeps_the_new_export_and_names_the_old_one(
        repo: Path, previous: tuple[Path, dict[str, str]], monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    out, before = previous
    real = eb._remove_tree

    def remove(path: Path) -> None:
        if path.name == ".bundle~old":
            raise PermissionError(13, "injected: in use", str(path))
        real(path)

    monkeypatch.setattr(eb, "_remove_tree", remove)
    assert build_bundle(repo, out)[0] == 0
    backup = out.with_name(".bundle~old")
    assert f"the next export to this folder deletes it ({backup})" in capsys.readouterr().out
    assert _tree(backup / "b") == before and _tree(out) != before
    monkeypatch.undo()
    assert build_bundle(repo, out)[0] == 0 and _leftovers(out) == [], "the next export removes the superseded copy"


def test_windows_retries_a_folder_briefly_in_use(repo: Path, previous: tuple[Path, dict[str, str]],
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    out, before = previous
    real, busy = os.rename, [2]

    def rename(src: str | Path, dst: str | Path) -> None:
        if busy[0]:
            busy[0] -= 1
            raise PermissionError(13, "injected: in use for a moment", str(src))
        real(src, dst)

    monkeypatch.setattr(os, "rename", rename)
    monkeypatch.setattr(eb.time, "sleep", lambda _s: None)
    monkeypatch.setattr(eb.sys, "platform", "win32")
    assert build_bundle(repo, out)[0] == 0 and busy == [0]
    assert _tree(out) != before and _leftovers(out) == []


# --------------------------------------------------------------------------- #
# Interrupted between the two renames: the next export recovers
# --------------------------------------------------------------------------- #

def test_an_interrupt_during_the_handover_puts_the_earlier_export_back(
        repo: Path, previous: tuple[Path, dict[str, str]], monkeypatch: pytest.MonkeyPatch) -> None:
    out, before = previous
    _rename_failing(monkeypatch, (".bundle~new/b", "bundle"), exc=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        build_bundle(repo, out)
    assert _tree(out) == before and _leftovers(out) == []


def _kill_during_handover(repo: Path, out: Path) -> None:
    """Export in a child process that dies (``os._exit``) between the two renames: what a killed export leaves, no
    bundle, the earlier one in ``.bundle~old/b``, the finished new one in ``.bundle~new/b``, and the journal."""
    code = ("import os, sys\nfrom pathlib import Path\nfrom engine.tooling import export_bundle as eb\n"
            "real = os.rename\n\n"
            "def rename(src, dst):\n"
            "    if Path(src).parent.name == '.bundle~new' and Path(dst).name == 'bundle':\n"
            "        os._exit(9)\n"
            "    real(src, dst)\n\n"
            "os.rename = rename\n"
            "eb.build_bundle(Path(sys.argv[1]), Path(sys.argv[2]))\n")
    proc = subprocess.run([sys.executable, "-c", code, str(repo), str(out)], cwd=ROOT, capture_output=True, text=True,
                          timeout=120, check=False)
    assert proc.returncode == 9, proc.stdout + proc.stderr
    assert not out.exists() and _leftovers(out) == [".bundle~export.json", ".bundle~new", ".bundle~old"]


def test_an_export_killed_between_the_renames_is_recovered_by_the_next(
        repo: Path, previous: tuple[Path, dict[str, str]], capsys: pytest.CaptureFixture[str]) -> None:
    out, before = previous
    _kill_during_handover(repo, out)
    assert _tree(out.with_name(".bundle~old") / "b") == before, "the earlier export, whole, aside"
    assert build_bundle(repo, out)[0] == 0
    assert "restored the previous export" in capsys.readouterr().out
    assert _leftovers(out) == [] and _tree(out) != before and eb.load_bundle_manifest(out) is not None


@pytest.mark.parametrize("output", ["empty folder", "other files"])
def test_a_kept_earlier_export_is_never_deleted_for_a_folder_that_is_not_a_finished_one(
        repo: Path, previous: tuple[Path, dict[str, str]], output: str) -> None:
    out, before = previous
    _kill_during_handover(repo, out)
    out.mkdir()
    if output == "other files":
        (out / "notes.txt").write_text("mine", encoding="utf-8")
    assert build_bundle(repo, out) == (1, None)
    assert _tree(out.with_name(".bundle~old") / "b") == before, "the only copy of the earlier export stays"
    assert _tree(out) == ({"notes.txt": hashlib.sha256(b"mine").hexdigest()} if output == "other files" else {})


def test_a_changed_backup_is_never_deleted_as_superseded(repo: Path, previous: tuple[Path, dict[str, str]],
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    out, _ = previous
    real = eb._remove_tree

    def remove(path: Path) -> None:
        if path.name == ".bundle~old":
            raise PermissionError(13, "injected: in use", str(path))
        real(path)

    monkeypatch.setattr(eb, "_remove_tree", remove)
    assert build_bundle(repo, out)[0] == 0  # (the earlier export kept in .bundle~old, recorded in the journal)
    monkeypatch.undo()
    backup = out.with_name(".bundle~old") / "b"
    (backup / "scenes" / "scene_b.json").write_text('{"edited": "in the backup"}\n', encoding="utf-8")
    kept = _tree(backup)
    assert build_bundle(repo, out) == (1, None)
    assert _tree(backup) == kept


# --------------------------------------------------------------------------- #
# Folders no export of this output recorded making are never deleted
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", [".bundle~new", ".bundle~old"])
@pytest.mark.parametrize("bundle", ["present", "absent"])
def test_a_folder_named_like_an_exports_but_not_recorded_is_left_untouched(
        repo: Path, previous: tuple[Path, dict[str, str]], name: str, bundle: str,
        capsys: pytest.CaptureFixture[str]) -> None:
    out, before = previous
    if bundle == "absent":
        shutil.rmtree(out)
    other = out.with_name(name)
    other.mkdir()
    (other / "valuable.txt").write_text("irreplaceable", encoding="utf-8")
    assert build_bundle(repo, out) == (1, None)
    assert (other / "valuable.txt").read_text(encoding="utf-8") == "irreplaceable" and len(list(other.iterdir())) == 1
    assert (_tree(out) == before) if bundle == "present" else not out.exists()
    assert "left untouched" in capsys.readouterr().out


def test_a_folder_put_where_a_killed_exports_was_is_not_its_own(repo: Path, previous: tuple[Path, dict[str, str]]) -> None:
    out, before = previous
    _kill_during_handover(repo, out)
    staging = out.with_name(".bundle~new")
    shutil.rmtree(staging)
    staging.mkdir()  # (a new folder of the same name, which on Linux gets the deleted one's inode back)
    (staging / "valuable.txt").write_text("irreplaceable", encoding="utf-8")
    assert build_bundle(repo, out) == (1, None)
    assert (staging / "valuable.txt").read_text(encoding="utf-8") == "irreplaceable"
    assert _tree(out) == before, "the recorded earlier export is put back; the unrecorded folder is not touched"


def test_the_same_folder_without_its_owner_file_is_not_the_exports(
        repo: Path, previous: tuple[Path, dict[str, str]]) -> None:
    """Ownership is the owner file, not the folder's identity (which Linux hands to a new folder at once)."""
    out, _ = previous
    _kill_during_handover(repo, out)
    staging = out.with_name(".bundle~new")
    for entry in list(staging.iterdir()):
        shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    (staging / "valuable.txt").write_text("irreplaceable", encoding="utf-8")
    assert build_bundle(repo, out) == (1, None)
    assert (staging / "valuable.txt").read_text(encoding="utf-8") == "irreplaceable"


def test_a_working_folder_holding_anything_else_is_left_untouched(
        repo: Path, previous: tuple[Path, dict[str, str]]) -> None:
    out, before = previous
    _kill_during_handover(repo, out)
    staging = out.with_name(".bundle~new")
    (staging / "valuable.txt").write_text("irreplaceable", encoding="utf-8")
    assert build_bundle(repo, out) == (1, None)
    assert (staging / "valuable.txt").read_text(encoding="utf-8") == "irreplaceable" and (staging / "b").is_dir()
    assert _tree(out) == before


def test_an_empty_working_folder_of_an_export_stopped_as_it_began_is_removed(
        repo: Path, previous: tuple[Path, dict[str, str]]) -> None:
    out, _ = previous
    eb._write_journal(out, "ab" * 16)  # (what an export stopped right after making its first folder leaves)
    out.with_name(".bundle~new").mkdir()
    assert build_bundle(repo, out)[0] == 0 and _leftovers(out) == []


def test_an_unreadable_journal_stops_the_export_and_touches_nothing(
        repo: Path, previous: tuple[Path, dict[str, str]]) -> None:
    out, before = previous
    _kill_during_handover(repo, out)
    journal = out.with_name(".bundle~export.json")
    journal.write_text("{garbled", encoding="utf-8")
    kept = {name: _tree(out.with_name(name)) for name in (".bundle~new", ".bundle~old")}
    assert build_bundle(repo, out) == (1, None)
    assert {name: _tree(out.with_name(name)) for name in kept} == kept and not out.exists()
    assert journal.read_text(encoding="utf-8") == "{garbled"


# --------------------------------------------------------------------------- #
# 6-7: what may be replaced
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("state", ["absent (and its parent)", "empty folder", "earlier export"])
def test_an_export_succeeds_into_an_absent_or_empty_folder_or_over_an_earlier_export(
        repo: Path, tmp_path: Path, state: str) -> None:
    out = tmp_path / "new parent" / "bundle"
    if state == "empty folder":
        out.mkdir(parents=True)
    elif state == "earlier export":
        assert build_bundle(repo, out)[0] == 0
        (repo / "scenes" / "scene_a.json").write_text('{"changed": true}\n', encoding="utf-8")
    code, manifest = build_bundle(repo, out)
    assert code == 0 and manifest is not None and _leftovers(out) == []
    assert set(_tree(out)) == {f["path"] for f in manifest.files} | {"bundle_manifest.json"}
    assert (out / "scenes" / "scene_a.json").read_bytes() == (repo / "scenes" / "scene_a.json").read_bytes()


@pytest.mark.parametrize("extra", [
    "a manifest beside the user's files",
    "an older game's saves",
    "unlisted bytecode",
    "a manifest listing paths outside",
    "an unreadable manifest",
])
def test_a_folder_with_anything_but_an_earlier_bundle_is_never_replaced(
        repo: Path, previous: tuple[Path, dict[str, str]], tmp_path: Path, extra: str,
        capsys: pytest.CaptureFixture[str]) -> None:
    out, _ = previous
    if extra == "a manifest beside the user's files":
        out = tmp_path / "Documents"
        out.mkdir()
        (out / "letter.txt").write_text("mine", encoding="utf-8")
        shutil.copy2(previous[0] / "bundle_manifest.json", out / "bundle_manifest.json")
    elif extra == "an older game's saves":
        (out / "saves").mkdir()
        (out / "saves" / "slot_1.json").write_text('{"hp": 3}', encoding="utf-8")
    elif extra == "unlisted bytecode":
        (out / "__pycache__").mkdir()
        (out / "__pycache__" / "notlisted.cpython-311.pyc").write_bytes(b"\0")
    elif extra == "a manifest listing paths outside":
        data = json.loads((out / "bundle_manifest.json").read_text(encoding="utf-8"))
        data["files"].append({"path": "../elsewhere/x.txt", "sha256": "0", "size": 0, "category": "asset"})
        (out / "bundle_manifest.json").write_text(json.dumps(data), encoding="utf-8")
    else:
        (out / "bundle_manifest.json").write_text("{not json", encoding="utf-8")
    before = _tree(out)
    assert build_bundle(repo, out) == (1, None)
    assert _tree(out) == before and _leftovers(out) == []
    assert "is not an earlier bundle" in capsys.readouterr().out


@pytest.mark.parametrize("change", [
    "a listed file's contents (same length)",
    "a listed file missing",
    "a listed file truncated",
    "a malformed manifest entry",
    "a duplicate manifest entry",
    "a manifest entry without a hash",
])
def test_an_earlier_export_that_was_changed_is_never_replaced(
        repo: Path, previous: tuple[Path, dict[str, str]], change: str, capsys: pytest.CaptureFixture[str]) -> None:
    out, _ = previous
    scene = out / "scenes" / "scene_b.json"
    manifest_path = out / "bundle_manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if change == "a listed file's contents (same length)":
        text = scene.read_bytes()
        scene.write_bytes(text[:-2] + (b"X" if text[-2:-1] != b"X" else b"Y") + text[-1:])
        assert len(scene.read_bytes()) == len(text)
    elif change == "a listed file missing":
        scene.unlink()
    elif change == "a listed file truncated":
        scene.write_bytes(scene.read_bytes()[:3])
    elif change == "a malformed manifest entry":
        data["files"][0]["size"] = "12"
    elif change == "a duplicate manifest entry":
        data["files"].append(dict(data["files"][0]))
    else:
        del data["files"][0]["sha256"]
    if "manifest" in change:
        manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    before = _tree(out)
    assert build_bundle(repo, out) == (1, None)
    assert _tree(out) == before and _leftovers(out) == []
    message = capsys.readouterr().out
    assert "is not an earlier bundle as Mesh exported it" in message and "nothing was changed" in message
    if "listed file" in change:
        assert "scenes/scene_b.json" in message


def test_bytecode_python_wrote_beside_the_bundles_source_does_not_stop_a_replacement(
        repo: Path, previous: tuple[Path, dict[str, str]]) -> None:
    out, _ = previous
    (out / "__pycache__").mkdir()
    (out / "__pycache__" / "main.cpython-311.pyc").write_bytes(b"\0")  # (the game was run from its folder)
    assert build_bundle(repo, out)[0] == 0
    assert not (out / "__pycache__").exists() and _leftovers(out) == []


def _link(target: Path, link: Path) -> None:
    """A directory link: a junction on Windows (no privilege needed), a symlink elsewhere."""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


@pytest.mark.parametrize("where", ["inside the earlier export", "the output folder itself"])
def test_a_link_or_junction_is_never_followed_or_replaced(repo: Path, previous: tuple[Path, dict[str, str]],
                                                          tmp_path: Path, where: str) -> None:
    out, _ = previous
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "precious.txt").write_text("keep", encoding="utf-8")
    if where == "inside the earlier export":
        _link(elsewhere, out / "linked")
    else:
        shutil.rmtree(out)
        _link(elsewhere, out)
    assert build_bundle(repo, out) == (1, None)
    assert (elsewhere / "precious.txt").read_text(encoding="utf-8") == "keep" and len(list(elsewhere.iterdir())) == 1


# --------------------------------------------------------------------------- #
# 8: same output as before
# --------------------------------------------------------------------------- #

def test_a_replacement_is_byte_for_byte_a_fresh_export(repo: Path, previous: tuple[Path, dict[str, str]],
                                                       tmp_path: Path) -> None:
    out, _ = previous
    fresh = tmp_path / "fresh"
    assert build_bundle(repo, out, deterministic=True)[0] == 0
    assert build_bundle(repo, fresh, deterministic=True)[0] == 0
    assert _tree(out) == _tree(fresh)
    replaced, made = eb.load_bundle_manifest(out), eb.load_bundle_manifest(fresh)
    assert replaced is not None and made is not None and replaced.to_dict() == made.to_dict()
    assert {p.name for p in (tmp_path / "out").iterdir()} == {"bundle"}


def test_copies_keep_the_source_files_times_as_before(repo: Path, tmp_path: Path) -> None:
    src = repo / "scenes" / "scene_b.json"
    os.utime(src, (1_000_000_000, 1_000_000_000))
    out = tmp_path / "b"
    assert build_bundle(repo, out)[0] == 0
    assert int((out / "scenes" / "scene_b.json").stat().st_mtime) == 1_000_000_000
