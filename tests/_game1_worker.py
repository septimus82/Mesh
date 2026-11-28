"""GAME-1 worker: ONE step of a player's session, run as its own process (``python -m tests._game1_worker``).

    python -m tests._game1_worker WORKDIR [--load SLOT] [--respawn] [--mutate NAME] [--save SLOT]

A hidden GameWindow (MESH_GL_SMOKE=1), the production SaveManager, a real room file in WORKDIR. The process starts a
fresh game (the pristine room), optionally loads a slot as Continue does, optionally changes the game, optionally
saves, prints ONE JSON line (the game's state, and what the slot holds) and exits. tests/test_game1_persistence_gpu.py
(the acceptance test) and tooling/game1_measure.py drive it; nothing here stubs the save path.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from tests._b01_arena import PIC, Arena, close_window, goblin, hero, hp_of, make_window, set_hp

QUEST = "gate_quest"
STAGES = ("s1", "s2", "s3")
RUNTIME = {"name": "Scout_7", "x": 30, "y": 30, "sprite": PIC, "layer": "entities",
           "behaviours": ["Health"], "behaviour_config": {"Health": {"max_hp": 9, "hp": 9}}}


def run_step(workdir: Path, *args: str) -> dict[str, Any]:
    """Start a fresh Python process for one session step; returns its result (it has exited when this returns)."""
    env = {**os.environ, "MESH_GL_SMOKE": "1"}
    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, "-m", "tests._game1_worker", str(workdir), *args], cwd=repo, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("GAME1_RESULT ")]
    assert proc.returncode == 0 and len(lines) == 1, (proc.returncode, proc.stdout[-1500:], proc.stderr[-1500:])
    result: dict[str, Any] = json.loads(lines[0][len("GAME1_RESULT "):])
    return result


def room_entities(kind: str = "main") -> list[dict[str, Any]]:
    if kind == "dup":  # two entities with ONE authored id, standing in the same place
        return [hero(), goblin("gob_a", 100, 100), goblin("gob_a", 100, 100), goblin("gob_b", 300, 300)]
    player = hero()
    player["tags"] = ["friendly"]
    elder = {"id": "elder", "name": "Elder", "tag": "guard", "tags": ["zeta", "alpha"], "x": 90, "y": 90, "sprite": PIC}
    return [player, goblin("gob_a", 100, 100), goblin("twin_a", 420, 200, name="Twin"),
            goblin("twin_b", 520, 200, name="Twin"), elder]


def install_quest(window: Any) -> None:
    qm = window.game_state_controller.quests
    normalized = qm._normalize_quest({"id": QUEST, "title": "Gate", "description": "Open the gate.",
                                      "stages": [{"id": s, "title": s, "text": s} for s in STAGES],
                                      "reward": {"set_flags": {}, "inc_counters": {}}})
    assert normalized is not None
    qm._definitions = {QUEST: normalized}
    qm._rebuild_stage_lookup()
    qm.reload_from_state()


def spawn_runtime(arena: Arena, name: str = "Scout_7", x: float = 30, hp: float = 9) -> Any:
    return arena.spawn(dict(RUNTIME, name=name, x=x), hp=hp)


def mutate(arena: Arena, name: str) -> None:
    from engine.inventory import get_or_create_inventory

    state = arena.window.game_state_controller
    if name == "first":
        set_hp(arena.by_id("hero"), 4)
        state.quests.start_quest(QUEST)
        state.quests.complete_stage(QUEST, "s1")
        inv = get_or_create_inventory(state.state.values)
        assert inv.add_item("healing_potion", 3) and inv.add_item("rusty_sword", 1)
        state.set_flag("met_elder", True)
        state.set_var("coins", 7)
        set_hp(arena.by_id("gob_a"), 6)
        arena.place(arena.by_id("gob_a"), 140, 160)
        elder = arena.by_id("elder")
        elder.mesh_tag = "merchant"
        elder.mesh_tags = ["merchant", "zeta", "alpha", "vip"]
        set_hp(arena.by_id("twin_a"), 3)
        set_hp(arena.by_id("twin_b"), 17)
        arena.place(spawn_runtime(arena), 33, 31, hp=5)
    elif name == "second":
        set_hp(arena.by_id("hero"), 2)
        state.quests.complete_stage(QUEST, "s2")
        assert get_or_create_inventory(state.state.values).add_item("healing_potion", 1)
        arena.place(arena.by_id("gob_a"), 150, 170, hp=1)
        set_hp(arena.by_id("twin_b"), 11)
        arena.place(arena.named("Scout_7")[0], 35, 32, hp=2)
    elif name == "dup":
        twins = sorted((x for x in arena.sprites() if getattr(x, "mesh_id", None) == "gob_a"), key=id)
        assert len(twins) == 2
        set_hp(twins[0], 5)
        set_hp(twins[1], 11)
    elif name.startswith("spawn:"):  # id-less runtime entities, as a shooter's projectiles: spawn:COUNT[:SALT]
        count, _, salt = name.split(":", 1)[1].partition(":")
        for n in range(int(count)):
            spawn_runtime(arena, name=f"proj_{salt}_{n}", x=200 + n + 7 * int(salt or 0), hp=1 + n)
    elif name == "expire":  # the projectiles hit something or time out: gone before the next save
        for sprite in [x for x in arena.sprites() if x.mesh_name.startswith("proj_")]:
            sprite.remove_from_sprite_lists()
    else:
        raise SystemExit(f"unknown mutation {name}")


def snapshot(arena: Arena) -> dict[str, Any]:
    from engine.inventory import get_or_create_inventory

    state = arena.window.game_state_controller
    quest = json.loads(json.dumps(state.state.values.get("quests", {}).get(QUEST, {})))
    sprites = [{"id": getattr(s, "mesh_id", None), "name": s.mesh_name, "x": round(s.center_x, 3),
                "y": round(s.center_y, 3), "hp": hp_of(s), "tag": s.mesh_tag, "tags": sorted(s.mesh_tags)}
               for s in arena.sprites()]
    sprites.sort(key=lambda r: (str(r["id"]), r["name"], r["x"], r["y"], r["hp"] or 0))
    return {"sprites": sprites, "quest": quest,
            "inventory": dict(get_or_create_inventory(state.state.values).list_items()),
            "flags": {"met_elder": state.get_flag("met_elder")}, "coins": state.get_var("coins"),
            "toasts": arena.toasts(), "held_unresolved": len(arena.held())}


def slot_facts(arena: Arena, slot: str) -> dict[str, Any]:
    path = arena.slot(slot)
    data = json.loads(path.read_text(encoding="utf-8"))
    saved = data["saved_entities"]
    return {"size": path.stat().st_size, "scene_entities": len(data["entities"]), "records": len(saved["entities"]), "unresolved": len(saved["unresolved"]),
            "entities": saved["entities"], "unresolved_records": saved["unresolved"]}


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "saved_world"


def prepare_v2_idless(workdir: Path, slot: str = "slot1") -> Path:
    """The real v2 save with id-less, same-named and same-id entities, over the room it was written from."""
    (workdir / "saves").mkdir(parents=True, exist_ok=True)
    room = workdir / "arena.json"
    room.write_text(json.dumps({"name": "Arena", "schema_version": 1, "version": 1, "layers": [], "entities": [
        hero(), goblin("gob_a", 100, 100), goblin("gob_b", 300, 300)]}), encoding="utf-8")
    save = json.loads((FIXTURES / "v2_idless_dupname_dupid.json").read_text(encoding="utf-8"))
    save["meta"]["scene_path"] = str(room)  # (the fixture's own is scrubbed)
    path = workdir / "saves" / f"{slot}.json"
    path.write_text(json.dumps(save, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def project_step(project: Path, load: bool, save: bool) -> dict[str, Any]:
    """A template project (the pre-#390 fixtures' room), played as the player does: Continue, then save."""
    from hd2d_demo import HiddenGame
    from saved_world_fixtures import ROOM, player_of

    from engine.save_runtime.entity_state import held_unresolved

    game = HiddenGame(project)
    try:
        game.load(ROOM)
        game.step(2)
        if load:
            assert game.window.save_manager.load_game("slot1")
            game.step(4)
        state = game.window.game_state_controller
        player = player_of(game)
        out: dict[str, Any] = {"player": [round(player.center_x), round(player.center_y)],
                               "flag": state.get_flag("met_the_elder"), "coins": state.get_var("coins"),
                               "held_unresolved": len(held_unresolved(game.window.scene_controller)),
                               "ids": sorted(str(getattr(s, "mesh_id", None)) for s in game.window.scene_controller.all_sprites)}
        if save:
            assert game.window.save_manager.save_game("slot1")
            block = json.loads((project / "saves" / "slot1.json").read_text(encoding="utf-8"))
            out["unresolved"] = len(block["saved_entities"]["unresolved"])
            out["schema"] = block["save_schema_version"]
        return out
    finally:
        game.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workdir", type=Path)
    parser.add_argument("--load")
    parser.add_argument("--room", default="main", choices=["main", "dup"])
    parser.add_argument("--mutate", action="append", default=[])
    parser.add_argument("--save")
    parser.add_argument("--project", action="store_true", help="WORKDIR is a template project (HiddenGame)")
    args = parser.parse_args(argv)
    if args.project:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tooling"))
        print("GAME1_RESULT " + json.dumps(project_step(args.workdir, bool(args.load), bool(args.save)), sort_keys=True))
        return 0
    window = make_window()
    try:
        arena = Arena(window, args.workdir)
        arena.saves.mkdir(parents=True, exist_ok=True)
        if not arena.room.exists():
            arena.write_room(*room_entities(args.room))
        arena.enter()
        install_quest(window)
        out: dict[str, Any] = {"loaded": None}
        if args.load:
            out["loaded"] = arena.load(args.load)
            out["after_load"] = snapshot(arena)
        for name in args.mutate:
            mutate(arena, name)
        if args.save:
            assert arena.manager.save_game(args.save), "the save was refused"
            out["slot"] = slot_facts(arena, args.save)
        out["state"] = snapshot(arena)
        print("GAME1_RESULT " + json.dumps(out, sort_keys=True))
        sys.stdout.flush()
    finally:
        close_window(window)
    return 0


if __name__ == "__main__":
    sys.exit(main())
