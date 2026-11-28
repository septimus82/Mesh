"""#651, owner decision D12: files Mesh's tools wrote before the fix keep their explicit Health ``hp: 1`` (and the
player's ``max_hp: 1``, Combat ``damage: 1``). ``mesh doctor`` warns; ``mesh doctor --fix-health-defaults`` drops them,
only when asked, with a backup. Never a silent rewrite. The signature: engine/tooling/health_defaults.py."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration  # (a generated project in a temporary folder)

ROOM = "packs/core_regions/scenes/start.json"
OLD_COMBAT = {"damage": 1.0, "cooldown": 1.0, "range": 32.0, "hitbox_size": 32.0, "target_tag": "enemy",
              "attack_anim": "attack", "attack_sound": "assets/sounds/attack.wav"}  # what add_behaviour wrote


def _doctor(root: Path, monkeypatch: pytest.MonkeyPatch, *extra: str) -> tuple[int, str]:
    from mesh_cli.main import main as mesh

    monkeypatch.chdir(root)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = mesh(["doctor", *extra])
    return code, out.getvalue()


def _enemy(eid: str, health: dict) -> dict:
    return {"id": eid, "name": eid, "x": 300, "y": 200, "tag": "enemy", "behaviours": ["Health"],
            "behaviour_config": {"Health": health}}


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A new project with what the old tools wrote, and a creator's own configs that must never be flagged."""
    from engine import project_ops as ops
    from engine.project_scaffold import create_project

    root = tmp_path / "game"
    create_project(root, "game")
    doc = json.loads((root / ROOM).read_text(encoding="utf-8"))
    doc["entities"] += [
        _enemy("tool_wolf", {"max_hp": 50.0, "hp": 1.0, "invulnerable": False}),  # flagged: "Health 50", hp left at 1
        _enemy("tool_rat", {"max_hp": 1.0, "hp": 1.0, "invulnerable": False}),  # not: 1 of 1 plays the same
        _enemy("own_one", {"hp": 1}),  # not: a creator's own (the tool always wrote all three)
        _enemy("own_low", {"hp": 1, "max_hp": 50}),  # not: a creator's own start
        _enemy("own_partial", {"max_hp": 50}),  # not: starts full anyway
    ]
    (root / ROOM).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    prefabs = json.loads((root / "assets/prefabs.json").read_text(encoding="utf-8"))
    player = next(p["entity"] for p in prefabs if p.get("id") == ops.PLAYER_PREFAB)
    player["behaviours"] += ["Health", "Combat"]
    player["behaviour_config"].update({"Health": {"max_hp": 1.0, "hp": 1.0, "invulnerable": False},  # flagged
                                       "Combat": dict(OLD_COMBAT)})  # flagged
    (root / "assets/prefabs.json").write_text(json.dumps(prefabs, indent=2), encoding="utf-8")
    return root


def _files(root: Path) -> dict[str, bytes]:
    return {rel: (root / rel).read_bytes() for rel in (ROOM, "assets/prefabs.json")}


def test_doctor_warns_and_changes_nothing_until_asked(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = _files(project)
    code, out = _doctor(project, monkeypatch)
    assert code == 0, out
    flagged = [line for line in out.splitlines() if "before #651" in line]
    assert len(flagged) == 3, out
    assert any("tool_wolf's Health starts at 1 of 50 HP" in line for line in flagged), out
    assert any("Player's Health has 1 of 1 HP" in line for line in flagged), out
    assert any("Player's Combat deals 1 damage" in line for line in flagged), out
    assert not any(name in out for name in ("tool_rat", "own_one", "own_low", "own_partial")), out
    assert "mesh doctor --fix-health-defaults" in out
    assert _files(project) == before, "doctor alone never rewrites"
    assert not (project / ".mesh" / "backups").exists()


def test_the_opt_in_fix_drops_only_the_tool_written_settings_with_a_backup(project: Path,
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import project_ops as ops

    before = _files(project)
    code, out = _doctor(project, monkeypatch, "--fix-health-defaults")
    assert code == 0 and "3 setting(s) fixed" in out, out
    room = {e["id"]: e for e in json.loads((project / ROOM).read_text(encoding="utf-8"))["entities"]}
    assert room["tool_wolf"]["behaviour_config"]["Health"] == {"max_hp": 50.0, "invulnerable": False}
    for eid, health in (("tool_rat", {"max_hp": 1.0, "hp": 1.0, "invulnerable": False}), ("own_one", {"hp": 1}),
                        ("own_low", {"hp": 1, "max_hp": 50}), ("own_partial", {"max_hp": 50})):
        assert room[eid]["behaviour_config"]["Health"] == health, eid
    prefabs = json.loads((project / "assets/prefabs.json").read_text(encoding="utf-8"))
    player = next(p["entity"] for p in prefabs if p.get("id") == ops.PLAYER_PREFAB)["behaviour_config"]
    assert player["Health"] == {"invulnerable": False}
    assert player["Combat"] == {k: v for k, v in OLD_COMBAT.items() if k != "damage"}
    backups = list((project / ".mesh" / "backups").glob("health-defaults-*"))
    assert len(backups) == 1 and {rel: (backups[0] / rel).read_bytes() for rel in before} == before

    code, out = _doctor(project, monkeypatch)
    assert "before #651" not in out, out


def test_the_fix_writes_nothing_while_studio_has_the_project(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.editor import project_ownership

    before = _files(project)
    with project_ownership.acquire(project, project_ownership.STUDIO):
        code, out = _doctor(project, monkeypatch, "--fix-health-defaults")
    assert code == 1 and "nothing was changed" in out, out
    assert _files(project) == before
