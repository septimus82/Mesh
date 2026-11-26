"""S1 5.7 (exit criterion E3): the creator workflow, end to end, through the real entry points.

``mesh new`` makes a game; it is authored only through the supported tools (Mesh Studio's project model and ops,
``mesh author apply``, ``mesh new-quest`` and MCP); it is played through its own ``main.py`` in a hidden, silent window
with keys sent to the window's own key handler (tests/_e2e_creator_driver.py, in a child process); F5 saves; a NEW
process starts the game again and F9 loads; then ``mesh export build`` and the exported game, run on its bundled engine
with no PYTHONPATH, plays, saves into the player's own folder and loads it back in another new process.

The game (the ``starter`` template's room, walled, with an inner wall whose gap a gate fills):
- the Elder: an "Only once" conversation whose "Thank you" is a "Choice once" reward (+25 gold, a flag);
- a potion to pick up; a Shopkeeper selling potions;
- the Wolf: an enemy with Health (3) that drops 5 gold;
- a Button ("Only once") that unlocks the gate (a "Locked until an event" door) and starts a cutscene (MCP; a flag
  and a counter); behind the gate a treasure chest (+10 gold) and a "React when someone comes near" zone whose event
  sets the flag that completes the quest;
- the quest (MCP): started by the Elder's choice, its first stage done when the gate opens, its last by the flag;
- a door to a second 2D room (the Shed) and back.
After re-entry, and after F9 in the new process, nothing pays twice and the gate stays open. The game also counts
what must happen exactly once or never: ``entered_zone`` and the zone's event per entry (#640), and a Bell (a button
used any number of times) heard by the Potion and the Wolf only until they are picked up / defeated (#637). The player
gets Health and Combat with no numbers authored: both come from its stats (#651). The game started again for F9 runs
from another folder and still saves in its project (#623). The exported bundle's files are hashed before and after
its runs: it writes nothing into its own folder.

Every step is its own test, on one game made and played once (module fixtures; the children run one at a time). A step
that fails because of an open defect is ``xfail(strict=True)`` with the issue's number (none today). (i) the chain and
(iii) the template smoke (every ``mesh new --template`` id starts with a player that walks; a 2D start room draws) run
in Extended's ``extended`` lane (``e2e``, no GL marker: each game runs in its own process). (ii) the HD-2D leg (a door
into an HD-2D room, walk, draw, return) and the ``hd2d_rpg`` template's draw are ``gl`` tests, for the gpu lane. Every
child process gets its own APPDATA / XDG folders inside the test's temporary folder, removed at the end.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.project_templates import list_templates

pytestmark = [pytest.mark.e2e,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

REPO = Path(__file__).resolve().parents[1]
DRIVER = Path(__file__).resolve().parent / "_e2e_creator_driver.py"
HIDDEN = REPO / "tooling" / "hidden_windows.py"
SIGN = "assets/sprites/starter_sign.png"
_GL = pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                         reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)")


# ----------------------------------------------------------------------------------------------------- helpers
def _mesh(*argv: str) -> tuple[int, str]:
    from mesh_cli.main import main as mesh

    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = mesh(list(argv))
    return code, out.getvalue()


@contextlib.contextmanager
def _in_folder(folder: Path) -> Iterator[None]:
    """A creator's shell in ``folder``: no project pinned by another test, the path caches fresh."""
    from engine.paths import reset_path_caches

    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("MESH_REPO_ROOT", raising=False)
        mp.chdir(folder)
        reset_path_caches()
        try:
            yield
        finally:
            reset_path_caches()


def _child(mode: str, game: Path, base: Path, *, exported: bool = False, cwd: str = "elsewhere") -> dict[str, Any]:
    """The driver in a new process, one at a time. Its per-user folders (saves, settings, the projects list) are
    ``base/home``; an exported game runs isolated (``-I``: no PYTHONPATH, no user site) from another folder."""
    home = base / "home"
    env = {k: v for k, v in os.environ.items() if not k.startswith("MESH_")}
    for var in ("APPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
        env[var] = str(home)
    if exported:
        env.pop("PYTHONPATH", None)
    else:
        env["PYTHONPATH"] = os.pathsep.join([str(REPO), *filter(None, [os.environ.get("PYTHONPATH")])])
        env["MESH_RUNTIME_SETTINGS_PATH"] = str(home / "user_settings.json")
    (base / cwd).mkdir(exist_ok=True)
    # (-B: Python writes no bytecode cache, so the bundle's own files can be compared before and after)
    args = [sys.executable, *(["-I", "-B"] if exported else []), str(DRIVER), mode, str(game), str(HIDDEN)]
    proc = subprocess.run(args, cwd=base / cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=420)
    line = next((x for x in reversed(proc.stdout.splitlines()) if x.startswith("MESH-E2E ")), None)
    assert line is not None, f"{mode}: the game crashed (exit {proc.returncode}):\n{(proc.stdout + proc.stderr)[-4000:]}"
    facts: dict[str, Any] = json.loads(line[len("MESH-E2E "):])
    assert "error" not in facts, f"{mode}: {facts['error']}\n{(proc.stdout + proc.stderr)[-3000:]}"
    return facts


def _files(folder: Path) -> dict[str, str]:
    """Every file under ``folder``, by its relative path, with its SHA-256."""
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def _step(facts: dict[str, Any], name: str) -> dict[str, Any]:
    step = facts["steps"].get(name)
    assert step is not None, f"step {name} never ran: {sorted(facts['steps'])}"
    return step


def _ok(facts: dict[str, Any], name: str) -> None:
    step = _step(facts, name)
    assert step["ok"], json.dumps(step, indent=1, default=str)


# --------------------------------------------------------------------------------------------------- authoring
def _author(root: Path) -> dict[str, Any]:
    """The game, through Studio's project model and ops, ``mesh author apply``, ``mesh new-quest`` and MCP."""
    from engine import project_ops as ops
    from engine.editor import project_ownership
    from engine.mcp_server import tools
    from engine.studio_project import Project

    world = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    # Studio: the Elder's conversation, and a second 2D room.
    with project_ownership.acquire(root, project_ownership.STUDIO) as held:
        project = Project.open(root, world)
        assert project is not None and project.current == "start"

        def elder(scene: dict[str, Any]) -> dict[str, Any]:
            scene, ident = ops.place_blank(scene, "start", "Elder", 200.0, 320.0)
            scene = ops.set_picture(scene, ident, SIGN)
            scene = ops.set_dialogue_text(scene, ident, "Help us, and take this.")
            scene = ops.set_conversation(scene, ident, once=True)  # "Only once"
            scene = ops.add_choice(scene, ident, "root", "Thank you")
            return ops.set_choice(scene, ident, "root", 0, once=True, add_counters="gold+25",  # "Choice once"
                                  set_flags="elder_thanked")

        project.edit_scene(elder)
        shed = project.add_room("Shed")
        written = project.save(owner=held)

    # mesh author apply: walls, the shop, the puzzle, the chest, the zone, the enemy, the doors, the player's combat.
    border = [(c, r) for c in range(24) for r in range(16) if c in (0, 23) or r in (0, 15)]
    inner = [(14, r) for r in range(1, 15) if r not in (7, 8)]  # a wall with a two-tile gap (y 224-288) the gate fills
    changes: list[dict[str, Any]] = [
        {"op": "paint_tiles", "room": "start", "layer": "walls", "cells": border + inner, "tile": 9}]

    def thing(name: str, x: float, y: float, *behaviours: tuple[str, dict[str, Any]], **fields: Any) -> None:
        ref = f"@{len(changes)}"
        changes.extend([{"op": "place_blank", "room": "start", "name": name, "x": x, "y": y},
                        {"op": "set_picture", "room": "start", "entity_id": ref,
                         "sprite": fields.pop("sprite", SIGN)}])
        if fields:
            changes.append({"op": "set_entity_fields", "room": "start", "entity_id": ref, "fields": fields})
        for behaviour, params in behaviours:
            changes.append({"op": "add_behaviour", "room": "start", "entity_id": ref, "behaviour": behaviour})
            changes.extend({"op": "set_behaviour_param", "room": "start", "entity_id": ref, "behaviour": behaviour,
                            "param": k, "value": v} for k, v in params.items())

    # The Potion and the Wolf also answer the Bell (a button used any number of times) with a counter: once they are
    # gone (picked up; defeated) the Bell must reach neither (#637).
    thing("Bell", 90, 330, ("SwitchInteract", {"event_id": "bell_rung"}))
    thing("Potion", 150, 220, ("PickupCollectible", {"item_id": "healing_potion", "item_amount": 1}),
          ("SetGameStateOnEvent", {"event_type": "bell_rung", "inc_counters": {"potion_hears": 1}}))
    thing("Merchant", 300, 420, ("Vendor", {"stock": [{"item_id": "healing_potion", "price": 5, "quantity": 3}]}))
    thing("Wolf", 330, 250, ("Health", {"max_hp": 3}), ("DropTable", {"drops": [{"gold": 5, "chance": 1.0}]}),
          ("SetGameStateOnEvent", {"event_type": "bell_rung", "inc_counters": {"howls": 1}}), tag="enemy")
    thing("Lever", 400, 160, ("SwitchInteract", {"event_id": "gate_open", "one_shot": True}),
          ("CutsceneTrigger", {"listen_event": "gate_open", "cutscene_id": "gate_opens"}))
    thing("Gate", 464, 256, ("DoorLock", {"unlock_event": "gate_open"}), sprite="assets/sprites/door.png", solid=True)
    thing("Chest", 600, 320, ("RewardChest", {"unlock_event": "gate_open", "gold": 10}))
    thing("VaultZone", 620, 160, ("TriggerZone", {"trigger_radius": 40, "trigger_target": "Player",
                                                  "on_trigger": "vault_reached"}),
          ("SetGameStateOnEvent", {"event_type": "vault_reached", "set_flags": {"reached_vault": True},
                                   "inc_counters": {"vault_events": 1}}))
    thing("ZoneTally", 700, 450, ("IncrementCounterOnEvent", {"event_type": "entered_zone", "counter": "zone_entries"}))
    changes += [
        {"op": "link_rooms", "key_a": "start", "at_a": [80, 440], "key_b": shed, "at_b": [320, 240]},
        {"op": "add_behaviour", "room": "start", "entity_id": "Player", "behaviour": "Combat"},
        {"op": "add_behaviour", "room": "start", "entity_id": "Player", "behaviour": "Health"},  # (its stats: #651)
    ]
    plan = root.parent / "changes.json"
    plan.write_text(json.dumps(changes), encoding="utf-8")
    code, out = _mesh("author", "apply", str(plan), "--project", str(root))
    authored = json.loads(out or "{}")

    # Quests: the CLI (a side errand), then MCP (the vault quest the game plays).
    with _in_folder(root):
        cli_quest = _mesh("new-quest", "Side Errand")[0]
    quest = {"title": "The Elder's Vault", "stages": [
        {"id": "open_gate", "title": "Open the vault gate",
         "start_on_event": {"type": "dialogue_choice", "payload": {"entity": "Elder"}},
         "complete_on": {"type": "door_unlocked"}},
        {"id": "enter_vault", "title": "Enter the vault", "requirements": {"flags": {"reached_vault": True}}}],
        "reward": {"inc_counters": {"vault_badge": 1}}}
    cutscene = [{"type": "set_flag", "flag": "gate_scene_seen"}, {"type": "add_counter", "counter": "renown", "delta": 1}]
    mcp = tools.apply_ops(operations=[{"type": "add_quest_definition", "quest_id": "vault_quest", "quest": quest},
                                      {"type": "add_cutscene", "id": "gate_opens", "steps": cutscene}], root=str(root))
    return {"studio_wrote": written, "shed": shed, "author_exit": code, "author": authored,
            "new_quest_exit": cli_quest, "mcp": mcp}


# ---------------------------------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    folder = tmp_path_factory.mktemp("e2e")
    yield folder
    shutil.rmtree(folder, ignore_errors=True)  # (the game, its export, and every child's per-user folders)


@pytest.fixture(scope="module")
def game(base: Path) -> dict[str, Any]:
    code, _ = _mesh("new", "game", "--template", "starter", "--dest", str(base))
    root = base / "game"
    made = {"root": root, "new_exit": code}
    if code == 0:
        made["authoring"] = _author(root)
    return made


@pytest.fixture(scope="module")
def played(game: dict[str, Any], base: Path) -> dict[str, Any]:
    """Process 1 plays and quicksaves (F5); process 2, a new one, quickloads (F9) and revisits."""
    play = _child("play", game["root"], base)
    return {"play": play, "resume": _child("resume", game["root"], base, cwd="another_folder")}  # (#623)


@pytest.fixture(scope="module")
def exported(game: dict[str, Any], base: Path) -> dict[str, Any]:
    with _in_folder(game["root"]):
        code, _ = _mesh("export", "build", "--deterministic")
    bundle = game["root"] / "dist" / "bundle"
    out: dict[str, Any] = {"exit": code, "bundle": bundle}
    if code == 0:
        out["files_before"] = _files(bundle)
        out["play"] = _child("export_play", bundle, base, exported=True)
        out["resume"] = _child("export_resume", bundle, base, exported=True)
        out["files_after"] = _files(bundle)
    return out


# ------------------------------------------------------------------------------------------- (i) the non-GL chain
def test_mesh_new_makes_the_game(game: dict[str, Any]) -> None:
    assert game["new_exit"] == 0 and (game["root"] / "config.json").is_file()


def test_every_feature_is_authored_through_the_supported_tools(game: dict[str, Any]) -> None:
    made = game["authoring"]
    assert made["shed"] == "shed" and made["studio_wrote"], made
    assert made["author_exit"] == 0 and made["author"].get("ok"), made["author"]
    assert made["new_quest_exit"] == 0
    assert made["mcp"].get("ok"), made["mcp"]


def test_play_dialogue_once_reward(played: dict[str, Any]) -> None:
    _ok(played["play"], "dialogue_once_reward")


def test_play_quest_starts_advances_and_completes(played: dict[str, Any]) -> None:
    for name in ("quest_started", "quest_stage_advances", "quest_completed"):
        _ok(played["play"], name)


def test_play_pickup(played: dict[str, Any]) -> None:
    _ok(played["play"], "pickup")


def test_play_shop_purchase(played: dict[str, Any]) -> None:
    _ok(played["play"], "shop_purchase")


def test_play_the_player_uses_its_stats(played: dict[str, Any]) -> None:
    """#651: the player's Health (no max_hp authored) and Combat take max_hp and attack from the player's stats."""
    start = played["play"]["start"]
    stats_hp, stats_attack = float(start["player_stats"]["max_hp"]), float(start["player_stats"]["attack"])
    assert stats_hp > 1 and stats_attack > 1, start["player_stats"]
    assert start["player_hp"] == [stats_hp, stats_hp], start
    assert start["player_damage"] == stats_attack, start


def test_play_removed_entities_stop_listening(played: dict[str, Any]) -> None:
    """#637: the Bell reaches the Potion and the Wolf while they are there, and neither once picked up / defeated."""
    _ok(played["play"], "removed_entities_stop_listening")


def test_play_enemy_with_health_is_defeated(played: dict[str, Any]) -> None:
    assert played["play"]["start"]["wolf_hp"] == [3.0, 3.0], "Health starts full (#651)"
    _ok(played["play"], "enemy_defeated")


def test_play_button_unlocks_the_gate_and_the_player_walks_through(played: dict[str, Any]) -> None:
    _ok(played["play"], "lever_unlocks_gate_and_walk_through")


def test_play_cutscene_started_by_the_button(played: dict[str, Any]) -> None:
    _ok(played["play"], "cutscene_plays")
    assert played["resume"]["after_load"]["renown"] == 1, "the cutscene played once, not again on re-entry or load"


def test_play_chest(played: dict[str, Any]) -> None:
    _ok(played["play"], "chest_opens")


def test_play_trigger_zone_event(played: dict[str, Any]) -> None:
    """#640: the zone sends its event and ``entered_zone`` exactly once for the one entry (counted by the game)."""
    _ok(played["play"], "zone_event")
    counts = {k: played["play"]["before_save"][k] for k in ("zone_entries", "vault_events")}
    assert counts == {"zone_entries": 1.0, "vault_events": 1.0}, counts


def test_play_door_to_another_room_and_back(played: dict[str, Any]) -> None:
    _ok(played["play"], "door_to_2d_room_and_back")


def test_play_nothing_repeats_on_reentry(played: dict[str, Any]) -> None:
    _ok(played["play"], "reentry_nothing_repeats")


def test_f5_then_a_new_process_f9_keeps_the_game(played: dict[str, Any], game: dict[str, Any]) -> None:
    before, after = played["play"]["before_save"], played["resume"]["after_load"]
    assert "quicksave" in played["play"]["saves"] and "quicksave" in played["resume"]["slots_at_start"]
    root = game["root"].resolve()
    for facts in (played["play"], played["resume"]):  # (#623: in the project, wherever the game was started from)
        assert Path(facts["save_dir"]).is_absolute() and Path(facts["save_dir"]).resolve() == root / "saves", facts
    fresh = played["resume"]["before_load"]  # (the new process starts a new game: F9 is what brings it back)
    assert (fresh["gold"], fresh["elder_thanked"], fresh["gate_locked"]) == (0.0, False, True), fresh
    assert after == before, json.dumps({"before": before, "after": after}, indent=1)
    assert after["gate_locked"] is False and after["gate_solid"] is False and after["chest_looted"] is True


def test_after_f9_nothing_repeats_on_revisit(played: dict[str, Any]) -> None:
    _ok(played["resume"], "after_load_nothing_repeats")
    _ok(played["resume"], "after_load_reentry_nothing_repeats")


def test_export_build(exported: dict[str, Any]) -> None:
    assert exported["exit"] == 0 and (exported["bundle"] / "main.py").is_file()


def test_exported_game_plays_on_its_own_engine(exported: dict[str, Any]) -> None:
    play = exported["play"]
    assert Path(play["engine"]).resolve().is_relative_to(exported["bundle"].resolve()), play["engine"]
    _ok(play, "exported_walks")
    _ok(play, "exported_reward")


def test_exported_game_saves_per_player_and_reloads(exported: dict[str, Any], base: Path) -> None:
    play, resume = exported["play"], exported["resume"]
    assert Path(play["save_dir"]).resolve().is_relative_to((base / "home").resolve()), play["save_dir"]
    assert play["slots_at_start"] == [] and "quicksave" in play["saves"]
    assert "quicksave" in resume["slots_at_start"] and resume["save_dir"] == play["save_dir"]
    assert resume["before_load"]["gold"] == 0.0
    assert resume["after_load"] == play["before_save"] and play["before_save"]["gold"] == 25.0


def test_exported_game_writes_nothing_into_its_own_folder(exported: dict[str, Any]) -> None:
    """Every file of the bundle, hashed after the build and after both runs: none added, changed or removed."""
    before, after = exported["files_before"], exported["files_after"]
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    assert before and not changed, f"the exported game changed its own folder: {changed}"


# ----------------------------------------------------------------------------------------- (iii) template smoke
@pytest.mark.parametrize("template", [t.id for t in list_templates()])
def test_template_starts_with_a_walkable_player(template: str, tmp_path: Path) -> None:
    """E4: every id ``mesh new --template`` accepts makes a game whose start room loads with a player that walks."""
    facts = _template(template, tmp_path, "smoke")
    assert facts["player"] and facts["moved"] > 10, facts
    assert facts["hd2d"] == (template == "hd2d_rpg"), facts
    if not facts["hd2d"]:  # (an HD-2D frame is drawn in the gpu lane: the test below)
        assert facts["colours"] > 1, f"a 2D start room draws a picture: {facts}"


def _template(template: str, folder: Path, mode: str) -> dict[str, Any]:
    code, _ = _mesh("new", "game", "--template", template, "--dest", str(folder))
    assert code == 0
    try:
        return _child(mode, folder / "game", folder)
    finally:
        for made in ("game", "home", "elsewhere"):
            shutil.rmtree(folder / made, ignore_errors=True)


# --------------------------------------------------------------------------- (ii) the HD-2D leg and draw (gpu lane)
@_GL
def test_hd2d_template_starts_walks_and_draws(tmp_path: Path) -> None:
    facts = _template("hd2d_rpg", tmp_path, "smoke_draw")
    assert facts["player"] and facts["moved"] > 10 and facts["hd2d"], facts
    assert facts["colours"] > 16, f"the HD-2D village draws a picture: {facts}"


@_GL
def test_door_into_an_hd2d_room_walk_draw_and_return(tmp_path: Path) -> None:
    """A 2D game (``mesh new``) gets an HD-2D room through Studio and a door to it through ``mesh author``; through the
    door the room renders, the player walks, a frame draws, and its door leads back to the 2D room, which draws."""
    from engine.editor import project_ownership
    from engine.studio_project import Project

    assert _mesh("new", "game", "--template", "starter", "--dest", str(tmp_path))[0] == 0
    root = tmp_path / "game"
    try:
        world = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
        with project_ownership.acquire(root, project_ownership.STUDIO) as held:
            project = Project.open(root, world)
            assert project is not None
            glade, _kit = project.add_hd2d_room("Glade", 16, 12)
            project.save(owner=held)
        plan = tmp_path / "changes.json"
        plan.write_text(json.dumps([{"op": "link_rooms", "key_a": "start", "at_a": [400, 300], "key_b": glade,
                                     "at_b": [256, 192]}]), encoding="utf-8")
        code, out = _mesh("author", "apply", str(plan), "--project", str(root))
        assert code == 0 and json.loads(out)["ok"], out
        trip = _child("hd2d", root, tmp_path)["hd2d"]
    finally:
        for made in ("game", "home", "elsewhere"):
            shutil.rmtree(tmp_path / made, ignore_errors=True)
        (tmp_path / "changes.json").unlink(missing_ok=True)
    assert trip["room"] == "glade" and trip["renderer"] and trip["error"] is None, trip
    assert trip["moved"] > 20, f"the player walks in the HD-2D room: {trip}"
    assert trip["colours"] > 16, f"the HD-2D room draws a picture: {trip}"
    assert trip["room_back"] == "start" and trip["colours_back"] > 1, f"back through its door: {trip}"
