"""A pip-installed Mesh works out of the box: the wheel carries the engine's own bundled files (the allow-list in
pyproject.toml's [tool.setuptools.data-files], installed under <prefix>/share/mesh-engine), and only those; a new
project, the HD-2D RPG starter included, gets everything it uses from them, outside any checkout.

Replaces the original test (2026-01), which expected the engine's packs/ to load from the wheel without a project;
since 643970a (2026-06-30) a game's content resolves only inside its project (docs/packaging.md). The full
installed-engine acceptance (Mesh Studio, play, export) is tooling/hd2d_install_acceptance.py.

H5 (#422): the check itself is tooling/installed_product_check.py, and CI's ``installed (<os>, py3.11)`` jobs run
this file. CI's earlier installed-wheel canary ran ``python -m mesh_cli`` from the checkout, which imports the
checkout's engine instead of the wheel's; so this file also proves the check fails on broken wheels, including one
whose missing file the checkout still has, and on that leaky way of running it.

H7 (#422): no test ran a game exported from an installed Mesh (tests/test_export_bundle.py exports with the checkout's
engine and never plays the result). Here the installed Mesh makes, checks and exports a 2D and an HD-2D project, and
the export, copied elsewhere, is played by a Python holding only Mesh's declared dependencies, with the checkout off
limits; broken exports (a lost module, room, config or picture, content or an engine taken from the checkout) fail.
"""

from __future__ import annotations

import base64
import hashlib
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tooling import installed_product_check as ipc

REPO = Path(__file__).resolve().parent.parent
UNVERIFIED_SPRITES = {"assets/sprites/animated_player.png", "assets/sprites/shelltide.png",
                      "assets/sprites/sproutling.png"}  # provenance unverified: never bundled


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Path, Path, Path]]:
    """(wheel, venv, scratch): this checkout's wheel, installed with its declared dependencies into a fresh venv."""
    scratch = tmp_path_factory.mktemp("installed")
    wheel = ipc.build_wheel(scratch / "wheelhouse")
    venv = scratch / "venv"
    ipc.make_venv(venv)
    ipc.install(venv, wheel)
    _INSTALLED["wheel"] = wheel
    yield wheel, venv, scratch
    _INSTALLED.clear()


_INSTALLED: dict[str, Path] = {}  # the wheel the module's venv holds now


def _holding(venv: Path, wheel: Path) -> None:
    """Make ``venv`` hold ``wheel`` (a forced reinstall replaces every Mesh file; dependencies stay)."""
    if _INSTALLED.get("wheel") != wheel:
        ipc.install(venv, wheel, deps=False)
        _INSTALLED["wheel"] = wheel


def _defective(wheel: Path, dest: Path, *, drop: str = "", replace: tuple[str, bytes] | None = None) -> Path:
    """A copy of ``wheel`` without member ``drop`` or with ``replace``'s member rewritten, its RECORD kept valid."""
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / wheel.name
    with zipfile.ZipFile(wheel) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        names = src.namelist()
        assert drop in names or not drop, f"{drop} is not in the wheel"
        assert replace is None or replace[0] in names, "the member to replace is in the wheel"
        record = next(n for n in names if n.endswith(".dist-info/RECORD"))
        lines = []
        for line in src.read(record).decode("utf-8").splitlines():
            name = line.split(",", 1)[0]
            if name == drop:
                continue
            if replace and name == replace[0]:
                digest = base64.urlsafe_b64encode(hashlib.sha256(replace[1]).digest()).rstrip(b"=").decode()
                line = f"{name},sha256={digest},{len(replace[1])}"
            lines.append(line)
        for name in names:
            if name == drop:
                continue
            data = replace[1] if replace and name == replace[0] else src.read(name)
            dst.writestr(name, "\n".join(lines) + "\n" if name == record else data)
    return out


def test_the_wheel_bundles_exactly_the_allow_list(built: tuple[Path, Path, Path]) -> None:
    wheel = built[0]
    allowed = ipc.allow_list()
    assert allowed and not (set(allowed) & UNVERIFIED_SPRITES)
    assert all((REPO / f).is_file() for f in allowed), "every allow-listed file exists"
    with zipfile.ZipFile(wheel) as zf:
        names = [n.replace("\\", "/") for n in zf.namelist()]
    bundled = sorted(n.split("/data/share/mesh-engine/", 1)[1] for n in names if "/data/share/mesh-engine/" in n)
    assert bundled == allowed, "the wheel bundles exactly the allow-list"
    assert not any(n.startswith(("packs/", "tooling/", "tests/")) for n in names)
    schemas = sorted(p.relative_to(REPO).as_posix() for p in (REPO / "engine" / "schemas").glob("*.json"))
    assert schemas and set(schemas) <= set(names), "the engine's own schemas travel with the package"


def test_the_installed_product_works_with_nothing_from_the_checkout(built: tuple[Path, Path, Path]) -> None:
    wheel, venv, scratch = built
    _holding(venv, wheel)
    report, found = ipc.check(venv, scratch / "good")
    assert found == []
    probe = report["probe"]
    assert Path(probe["engine"]).resolve().is_relative_to(venv.resolve()), "the installed engine, not a checkout"
    assert probe["modules_outside_prefix"] == [] and probe["checkout_on_path"] == [] and not probe["tooling_importable"]
    assert {"assets/sprites/starter_hero.png", "assets/tilesets/starter.png", "assets/sprites/door.png"} <= set(probe["blank_files"])
    assert probe["blank_input_bindings"], "the engine's default input bindings"
    assert Path(probe["species_from"]).resolve().is_relative_to((venv / "share" / "mesh-engine").resolve())
    assert probe["species_loads"]
    village = set(probe["hd2d_rpg_files"])
    assert {"assets/sprites/hd2d_hero.png", "assets/sounds/ui_open.wav", "assets/hd2d_starter/textures/grass.png"} <= village
    assert len(probe["hd2d_rpg_models"]) == 14 and not village & UNVERIFIED_SPRITES
    assert {"config.json", "main.py", "assets"} <= set(report["cli"]["new_files"])


_ASSET = "assets/sprites/starter_hero.png"


@pytest.mark.parametrize(
    ("defect", "expected"),
    [
        ("missing module", "No module named 'engine.project_scaffold'"),
        ("broken module", "deliberately broken"),
        ("missing asset the checkout still has", f"bundled file not installed: {_ASSET}"),
    ],
)
def test_a_broken_wheel_fails_the_check(built: tuple[Path, Path, Path], defect: str, expected: str) -> None:
    wheel, venv, scratch = built
    data_dir = next(n for n in zipfile.ZipFile(wheel).namelist() if n.endswith(f"/data/share/mesh-engine/{_ASSET}"))
    assert (REPO / _ASSET).is_file() and (REPO / "engine" / "project_scaffold.py").is_file(), "the checkout is intact"
    dest = scratch / "defects" / defect.replace(" ", "_")
    if defect == "missing module":
        broken = _defective(wheel, dest, drop="engine/project_scaffold.py")
    elif defect == "broken module":
        broken = _defective(wheel, dest, replace=("engine/hd2d/catalog.py", b"raise ImportError('deliberately broken (H5)')\n"))
    else:
        broken = _defective(wheel, dest, drop=data_dir)
    _holding(venv, broken)
    _report, found = ipc.check(venv, scratch / defect.replace(" ", "_"))
    assert any(expected in line for line in found), found


def test_the_check_sees_the_old_canary_s_leak(built: tuple[Path, Path, Path]) -> None:
    """The old canary's way of running the product (from the checkout, not isolated): a wheel without a module still
    "works", because the checkout supplies it. The check names every module that came from outside the installation."""
    wheel, venv, scratch = built
    broken = _defective(wheel, scratch / "defects" / "leak", drop="engine/project_scaffold.py")
    _holding(venv, broken)
    leaky = ipc.run_probe(venv, scratch / "leak" / "work", leaky=True)
    isolated = ipc.run_probe(venv, scratch / "leak_isolated" / "work")
    assert "error" not in leaky, "run from the checkout, the broken wheel seems to work"
    found = ipc.problems(leaky, None)
    assert "engine.project_scaffold was imported from outside the installed environment" in found
    assert any(line.startswith("a checkout path is importable") for line in found)
    assert "No module named 'engine.project_scaffold'" in isolated["error"], "isolated, the same wheel fails"


# --------------------------------------------------------------------------- #
# H7 (#422): a game exported with the installed Mesh runs as its player runs it, without Mesh or the checkout.
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def exported(built: tuple[Path, Path, Path]) -> dict[str, dict[str, Any]]:
    """Each template of ``ipc.EXPORTS`` made (``mesh new``), checked (``mesh doctor``) and exported (``mesh export
    build``) by the installed Mesh of this checkout's wheel, run isolated from a scratch folder."""
    wheel, venv, scratch = built
    _holding(venv, wheel)
    return {template: ipc.export_game(venv, scratch / "export" / template, template) for template in ipc.EXPORTS}


@pytest.fixture(scope="module")
def player(built: tuple[Path, Path, Path]) -> Path:
    """A player's environment: what the wheel declares it needs (Requires-Dist), not Mesh."""
    wheel, _venv, scratch = built
    ipc.make_player_env(scratch / "player_env", wheel)
    return scratch / "player_env"


def _copy(exported: dict[str, dict[str, Any]], template: str, dest: Path) -> Path:
    import shutil

    assert not dest.exists()
    shutil.copytree(exported[template]["bundle"], dest)
    return dest


@pytest.mark.parametrize("template", sorted(ipc.EXPORTS))
def test_an_exported_game_runs_without_mesh_or_the_checkout(built: tuple[Path, Path, Path],
                                                            exported: dict[str, dict[str, Any]], player: Path,
                                                            template: str) -> None:
    scratch = built[2]
    export = exported[template]
    assert ipc.export_problems(export) == []
    for step in ("new", "doctor", "export"):  # the installed Mesh used the installation and the project, nothing else
        audit = export["steps"][step]["audit"]
        assert set(audit["read"]) <= {"environment", "python", "project"} and audit["modules"].keys() == {"environment"}
    game = _copy(exported, template, scratch / "played" / template / "game")
    run = ipc.play(player, game, scratch / "played" / template / "evidence")
    start, hd2d = ipc.EXPORTS[template]
    assert ipc.game_problems(game, run, start=start, hd2d=hd2d) == []
    assert ipc.bundle_problems(game) == [], "the game leaves its folder as exported"
    facts, audit = run["game"], run["audit"]
    assert Path(facts["engine"]).resolve().is_relative_to(game.resolve()) and not facts["mesh_installed"]
    assert audit["modules"].keys() == {"game"} and audit["denied"] == [] and audit["elsewhere"] == []
    assert audit["read"]["game"] > 0 and set(audit["read"]) <= {"game", "environment", "python", "user"}
    walk = facts["walk"]
    assert walk[2] - walk[0] > 32 and walk[3] == walk[1], "walked right, a fixed distance at fixed steps"
    assert facts["hd2d"] is hd2d and facts["sprites"] > 1 and facts["colours"] >= 16


_REMOVED = "engine/scene_loader.py"  # (the game imports it as it starts)


@pytest.mark.parametrize(
    ("defect", "expected"),
    [
        ("missing runtime module", f"No module named '{_REMOVED[:-3].replace('/', '.')}'"),
        ("missing start room", "Scene file not found: packs/core_regions/scenes/start.json"),
        ("missing config", "Scene file not found: scenes/cellar.json"),  # (the engine's default start room)
        ("missing picture", "Failed to load sprite sheet 'assets/sprites/starter_hero.png': file not found"),
        ("content resolved in the checkout", "tried to use the checkout"),
        ("engine imported from the checkout", "tried to use the checkout"),
    ],
)
def test_a_broken_export_fails_clearly(built: tuple[Path, Path, Path], exported: dict[str, dict[str, Any]],
                                       player: Path, defect: str, expected: str) -> None:
    import json
    import shutil

    scratch = built[2]
    folder = scratch / "broken" / defect.replace(" ", "_")
    game = _copy(exported, "adventure", folder / "game")
    lost = ("config.json", "assets/sprites/starter_hero.png", _REMOVED)
    assert all((REPO / rel).is_file() for rel in lost), "the checkout has what the export loses: only the guard hides it"
    if defect == "missing runtime module":
        (game / _REMOVED).unlink()
    elif defect == "missing start room":
        (game / "packs/core_regions/scenes/start.json").unlink()
    elif defect == "missing config":
        (game / "config.json").unlink()
    elif defect == "missing picture":
        (game / "assets/sprites/starter_hero.png").unlink()
    elif defect == "content resolved in the checkout":  # a developer's own path left in the game's config
        config = json.loads((game / "config.json").read_text(encoding="utf-8"))
        (game / "config.json").write_text(json.dumps({**config, "content_roots": [str(REPO)]}), encoding="utf-8")
    else:  # an export without its engine, played where the checkout is importable (a developer's own machine)
        shutil.rmtree(game / "engine")
    run = ipc.play(player, game, folder / "evidence", leaky=defect == "engine imported from the checkout")
    start, hd2d = ipc.EXPORTS["adventure"]
    found = ipc.game_problems(game, run, start=start, hd2d=hd2d)
    assert any(expected in line for line in found), found
    if defect == "missing config":
        assert "No config file at 'config.json'" in run["stdout"], "the game says why"
    if defect != "missing picture":
        assert run["code"] != 0, "the game stops: it doesn't carry on half-loaded"
