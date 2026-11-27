"""#749: ``package-player --out`` and ``dist --out`` never delete a folder they didn't make.

Both build beside the output folder and swap the result in only when complete (``export_bundle.build_into``, F4). An
output folder is replaced only when absent, empty or an earlier output exactly as built; one that is, or holds, the
project, the home folder or a drive root, or lies inside the packaged sources, is refused before any work starts.
Every refusal below leaves every file under ``tmp_path`` exactly as it was. Disposable folders only.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from engine.runtime_only import DEFAULT_SMOKE_SCENE
from engine.tooling import dist_command
from engine.tooling import export_bundle as eb
from mesh_cli import player_package as pp
from tooling import build_web

pytestmark = [pytest.mark.integration]


def _tree(folder: Path) -> dict[str, str]:
    """Every file, folder and link under ``folder`` (relative path: sha256, "dir" or "link"; links not followed)."""
    found: dict[str, str] = {}
    for root, dirs, files in os.walk(folder):  # (os.walk follows no symlink; junctions are listed, not entered, below)
        for name in sorted(dirs + files):
            path = Path(root) / name
            rel = path.relative_to(folder).as_posix()
            if eb._is_link(path):  # (a symlink or a junction)
                found[rel] = "link"
            else:
                found[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if name in files else "dir"
        dirs[:] = [d for d in dirs if found[(Path(root) / d).relative_to(folder).as_posix()] == "dir"]
    return found


def _link(link: Path, target: Path) -> None:
    """A link to the folder ``target``: a junction on Windows (no privilege needed), a symlink elsewhere."""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tiny repository to package (``tmp_path/work/repo``, the working directory), with a creator's file."""
    root = tmp_path / "work" / "repo"
    for rel, text in {"engine/__init__.py": "", "engine/runtime.py": "A = 1\n", "engine/editor/tool.py": "",
                      "mesh_cli/__init__.py": "", DEFAULT_SMOKE_SCENE: "{}\n", "my_notes.txt": "precious\n"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    monkeypatch.chdir(root)
    monkeypatch.setattr(pp, "_resolve_repo_root", lambda start: root)
    return root


@pytest.fixture
def builds(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Where each package build started (a refusal must come before any)."""
    started: list[Path] = []
    real = pp._build_package

    def recording(stage: Path, *args: object, **kwargs: object) -> int:
        started.append(stage)
        return real(stage, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pp, "_build_package", recording)
    return started


def _package(out: str | Path) -> int:
    return pp.package_player_bundle(out_dir=str(out))


def _unrelated(tmp_path: Path) -> Path:
    folder = tmp_path / "photos"
    (folder / "2026").mkdir(parents=True)
    (folder / "2026" / "beach.jpg").write_bytes(b"\xff\xd8 not really a jpeg")
    return folder


@pytest.mark.parametrize("where", ["project", "dot", "ancestor", "unrelated", "home", "traversal to home",
                                   "inside sources"])
def test_package_player_refuses_a_folder_it_did_not_make_and_touches_nothing(
        where: str, project: Path, builds: list[Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()  # (empty: only the home rule refuses it)
    monkeypatch.setattr(Path, "home", lambda: home)
    out = {"project": project, "dot": ".", "ancestor": tmp_path / "work", "unrelated": _unrelated(tmp_path),
           "home": home, "traversal to home": os.path.join("..", "..", "home"),
           "inside sources": project / "engine" / "pkg"}[where]
    before = _tree(tmp_path)
    assert _package(out) == 1
    assert _tree(tmp_path) == before
    assert builds == []


@pytest.mark.parametrize("case", ["link to it", "link inside it", "edited", "made by dist"])
def test_package_player_never_replaces_anything_but_its_own_package_as_built(
        case: str, project: Path, steps: list[str], builds: list[Path], tmp_path: Path) -> None:
    """Replacing needs both the marker naming package-player and exactly the files it wrote; a link is never followed."""
    out = tmp_path / "out" / "pkg"
    assert (_dist(out) if case == "made by dist" else _package(out)) == 0
    victim = _unrelated(tmp_path)
    target = out
    if case == "link to it":
        target = tmp_path / "out" / "via_link"
        _link(target, out)
    elif case == "link inside it":
        _link(out / "engine" / "photos", victim)
    elif case == "edited":
        (out / "engine" / "runtime.py").write_text("A = 'mine'\n", encoding="utf-8")
    before, started = _tree(tmp_path), len(builds)
    assert _package(target) == 1
    assert _tree(tmp_path) == before
    assert len(builds) == started


def test_package_player_replaces_its_own_earlier_package(project: Path, tmp_path: Path) -> None:
    out = tmp_path / "out" / "pkg"
    assert _package(out) == 0
    assert (out / "engine" / "runtime.py").read_text(encoding="utf-8") == "A = 1\n"
    assert not (out / "engine" / "editor").exists()
    (project / "engine" / "runtime.py").write_text("A = 2\n", encoding="utf-8")
    assert _package(out) == 0
    assert (out / "engine" / "runtime.py").read_text(encoding="utf-8") == "A = 2\n"
    assert sorted(p.name for p in out.parent.iterdir()) == ["pkg"]  # (no working folder or journal left)


def test_a_package_that_fails_midway_leaves_the_earlier_one_intact(project: Path, tmp_path: Path,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "out" / "pkg"
    assert _package(out) == 0
    before = _tree(out)
    real, calls = pp.shutil.copy2, [0]

    def failing(*args: object, **kwargs: object) -> object:
        calls[0] += 1
        if calls[0] > 1:
            raise OSError("disk full (injected)")
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pp.shutil, "copy2", failing)
    assert _package(out) == 1
    assert calls[0] == 2
    assert _tree(out) == before
    assert sorted(p.name for p in out.parent.iterdir()) == ["pkg"]


# --------------------------------------------------------------------------- #
# mesh dist
# --------------------------------------------------------------------------- #

@pytest.fixture
def steps(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """dist's steps, stubbed (each records itself); build-demo's outcome is ``steps_result['build']``."""
    ran: list[str] = []
    monkeypatch.setattr(dist_command.check, "run_check", lambda **kw: ran.append("check") or True)
    monkeypatch.setattr(dist_command.release_command, "release_check_command", lambda a: ran.append("release"))
    monkeypatch.setattr(dist_command.build_demo_command, "handle_build_demo", lambda a: ran.append("build") or 0)
    monkeypatch.setattr(dist_command.cli_snapshot_command, "cli_snapshot_command", lambda a: ran.append("cli"))
    monkeypatch.setattr(dist_command.plan_schema_command, "plan_schema_command", lambda a: ran.append("schema"))
    return ran


def _dist(out: str | Path, world: str = "worlds/main.json") -> int:
    return dist_command.handle_dist(argparse.Namespace(profile="dev", world=world, out=str(out)))


@pytest.mark.parametrize("where", ["project", "dot", "ancestor", "unrelated", "home", "traversal to home",
                                   "demo content"])
def test_dist_refuses_a_folder_it_did_not_make_and_touches_nothing(
        where: str, project: Path, steps: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    out = {"project": project, "dot": ".", "ancestor": tmp_path / "work", "unrelated": _unrelated(tmp_path),
           "home": home, "traversal to home": os.path.join("..", "..", "home"), "demo content": project / "dist"}[where]
    before = _tree(tmp_path)
    assert _dist(out) == 1
    assert _tree(tmp_path) == before
    assert steps == []


def test_dist_replaces_its_own_earlier_distribution(project: Path, steps: list[str], tmp_path: Path) -> None:
    out = tmp_path / "out" / "dist"
    assert _dist(out) == 0
    assert '"worlds/main.json"' in (out / "dist_manifest.json").read_text(encoding="utf-8")
    assert _dist(out, world="worlds/other.json") == 0
    assert '"worlds/other.json"' in (out / "dist_manifest.json").read_text(encoding="utf-8")
    assert sorted(p.name for p in out.parent.iterdir()) == ["dist"]


def test_a_dist_that_fails_midway_leaves_the_earlier_one_intact(project: Path, steps: list[str], tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "out" / "dist"
    assert _dist(out) == 0
    before = _tree(out)
    monkeypatch.setattr(dist_command.build_demo_command, "handle_build_demo", lambda a: 1)
    assert _dist(out, world="worlds/other.json") == 1
    assert _tree(out) == before
    assert sorted(p.name for p in out.parent.iterdir()) == ["dist"]


# --------------------------------------------------------------------------- #
# build-web (tooling/build_web.py)
# --------------------------------------------------------------------------- #

@pytest.fixture
def web(project: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """build_web with pygbag stubbed: it "builds" ``index.html`` holding ``web['page']``; ``web['runs']`` counts runs."""
    state: dict[str, Any] = {"page": "v1", "runs": 0}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd: list[str], *, capture_output: bool, text: bool, cwd: str) -> _Result:
        state["runs"] += 1
        built = Path(cwd) / "build" / "web"
        built.mkdir(parents=True)
        (built / "index.html").write_text(state["page"], encoding="utf-8")
        return _Result()

    monkeypatch.setattr(build_web, "_copy_stage_tree", lambda **kw: kw["stage_root"].mkdir(parents=True))
    monkeypatch.setattr(build_web.subprocess, "run", fake_run)
    return state


def _web(out: str | Path) -> int:
    return build_web.main(["web_main.py", "--out-dir", str(out)])


@pytest.mark.parametrize("where", ["project", "dot", "ancestor", "unrelated", "home", "traversal to home",
                                   "inside the stage", "link to its own output"])
def test_build_web_refuses_a_folder_it_did_not_make_and_touches_nothing(
        where: str, project: Path, web: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    out: str | Path
    if where == "link to its own output":
        assert _web(tmp_path / "site") == 0
        out = tmp_path / "via_link"
        _link(out, tmp_path / "site")
        web["runs"] = 0
    else:
        out = {"project": project, "dot": ".", "ancestor": tmp_path / "work", "unrelated": _unrelated(tmp_path),
               "home": home, "traversal to home": os.path.join("..", "..", "home"),
               "inside the stage": project / "artifacts" / "_web_build_stage" / "site"}[where]
    before = _tree(tmp_path)
    assert _web(out) == 1
    assert _tree(tmp_path) == before
    assert web["runs"] == 0


def test_build_web_replaces_its_own_earlier_output(project: Path, web: dict[str, Any], tmp_path: Path) -> None:
    out = tmp_path / "site"
    assert _web(out) == 0
    web["page"] = "v2"
    assert _web(out) == 0
    assert (out / "index.html").read_text(encoding="utf-8") == "v2"
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith(".site")) == []


def test_a_web_publish_that_fails_leaves_the_earlier_output_intact(project: Path, web: dict[str, Any], tmp_path: Path,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "site"
    assert _web(out) == 0
    before = _tree(out)
    web["page"] = "v2"

    def failing(*args: object, **kwargs: object) -> object:
        raise OSError("disk full (injected)")

    monkeypatch.setattr(build_web.shutil, "copytree", failing)
    assert _web(out) == 1
    assert _tree(out) == before
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith(".site")) == []


def test_a_manifest_path_inside_the_output_is_written_with_the_new_package(project: Path, tmp_path: Path) -> None:
    """verify-all passes ``--manifest <out>/manifest.json``: it goes into the new package, never into the earlier one."""
    out = tmp_path / "out" / "pkg"
    for _ in range(2):
        assert pp.package_player_bundle(out_dir=str(out), manifest_path=str(out / "manifest.json")) == 0
    assert '"mesh_cli package-player"' in (out / "manifest.json").read_text(encoding="utf-8")
    assert sorted(p.name for p in out.parent.iterdir()) == ["pkg"]
