"""The player half of tests/test_e2e_creator_workflow.py: run in a child process, as ``GameWindow.run``.

    python tests/_e2e_creator_driver.py MODE GAME_FOLDER HIDDEN_WINDOWS_PY

Runs the game's own ``main.py`` (a dev project, or an exported bundle with its bundled engine) with pyglet's loop
replaced by a player: keys through the window's own key handler (``dispatch_event("on_key_press"/"on_key_release")``)
and frames through ``on_update``, in a hidden, never-activated, silent window. Reads what happened from the running
game and prints it as one ``MESH-E2E <json>`` line. Nothing here changes the game's state except through keys.

Self-contained on purpose (no ``tests``/``tooling`` imports): for an exported game this must import only the bundle's
engine, never this checkout's. The hidden-window helper is loaded from the path it is given.
"""

import copy
import importlib.util
import json
import runpy
import sys
import traceback
from pathlib import Path
from typing import Any

MODE, GAME, HIDDEN = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
if MODE.startswith("export"):
    sys.path.insert(0, str(GAME))  # (as ``python <game>/main.py`` does: the game's own folder, so its own engine)

import pyglet  # noqa: E402

pyglet.options["audio"] = ("silent",)  # (never a sound: before anything loads pyglet.media)
_spec = importlib.util.spec_from_file_location("hidden_windows", HIDDEN)
assert _spec is not None and _spec.loader is not None
_hidden = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hidden)
_hidden.no_activate()
import pyglet.window  # noqa: E402

_shown = pyglet.window.Window.__init__


def _never_shown(self: Any, *args: Any, **kwargs: Any) -> None:
    kwargs["visible"] = False
    _shown(self, *args, **kwargs)


pyglet.window.Window.__init__ = _never_shown  # type: ignore[method-assign]

import engine  # noqa: E402
import engine.optional_arcade as optional_arcade  # noqa: E402
from engine.game import GameWindow  # noqa: E402

K = optional_arcade.arcade.key
facts: dict[str, Any] = {"mode": MODE, "engine": engine.__file__, "steps": {}}


class Player:
    """A person playing: arrow keys, E, SPACE, F5/F9, one frame at a time."""

    def __init__(self, window: Any) -> None:
        self.window = window
        self.sc = window.scene_controller
        self.gs = window.game_state_controller
        self.held: set[int] = set()
        window._allow_dispatch_event = True  # (pyglet queues a hidden window's events outside its own loop otherwise)
        window.audio.set_master_volume(0.0)

    # ------------------------------------------------------------------------------------------------- input
    def step(self, frames: int = 1) -> None:
        for _ in range(frames):
            self.window.dispatch_event("on_update", 1 / 60)

    def press(self, symbol: int, frames: int = 3) -> None:
        self.window.dispatch_event("on_key_press", symbol, 0)
        self.step(1)
        self.window.dispatch_event("on_key_release", symbol, 0)
        self.step(frames)

    def hold(self, keys: set[int]) -> None:
        for k in self.held - keys:
            self.window.dispatch_event("on_key_release", k, 0)
        for k in keys - self.held:
            self.window.dispatch_event("on_key_press", k, 0)
        self.held = set(keys)

    def walk_to(self, x: float, y: float, tol: float = 8.0, frames: int = 900) -> str:
        """Arrow keys toward (x, y) until there, blocked, or the room changes."""
        start_room, last, still = self.room(), None, 0
        for _ in range(frames):
            hero = self.hero()
            if hero is None or self.room() != start_room:
                self.hold(set())
                self.step(2)
                return "left_room"
            dx, dy = x - hero.center_x, y - hero.center_y
            if abs(dx) <= tol and abs(dy) <= tol:
                self.hold(set())
                self.step(1)
                return "arrived"
            keys = set()
            if dx > tol:
                keys.add(K.RIGHT)
            if dx < -tol:
                keys.add(K.LEFT)
            if dy > tol:
                keys.add(K.UP)
            if dy < -tol:
                keys.add(K.DOWN)
            self.hold(keys)
            self.step(1)
            pos = (round(hero.center_x, 1), round(hero.center_y, 1))
            still = still + 1 if pos == last else 0
            last = pos
            if still > 45:
                self.hold(set())
                self.step(1)
                return f"blocked at {pos}"
        self.hold(set())
        return "timeout"

    def approach(self, name: str, below: float = 40.0) -> str:
        """Walk to just below ``name``, then face it (a tap of UP)."""
        target = self.named(name)
        if target is None:
            return f"no {name}"
        walked = self.walk_to(target.center_x, target.center_y - below)
        self.press(K.UP, 1)
        return walked

    def draw(self) -> int:
        """One frame drawn and read back (as tooling/hd2d_demo.py's HiddenGame does): how many colours it has."""
        self.window.dispatch_event("on_draw")
        picture = optional_arcade.arcade.get_image(0, 0, *self.window.get_framebuffer_size())
        self.window.ctx.gc()
        return len(picture.convert("RGB").getcolors(1 << 24) or ())

    def talking(self) -> bool:
        box = self.window.ui_controller.dialogue_box
        return bool(box is not None and box.is_active())

    def choose(self, text: str) -> bool:
        box = self.window.ui_controller.dialogue_box
        texts = [str(c.get("text")) for c in box.get_choices()]
        if text not in texts:
            return False
        for _ in range(len(texts)):
            if box.get_choice_cursor() == texts.index(text):
                break
            self.press(K.DOWN)
        self.press(K.E, 5)
        return True

    def talk(self, name: str, choice: str | None = None) -> dict[str, Any]:
        """E beside ``name``; pick ``choice`` if offered; E through to the end."""
        walked = self.approach(name)
        self.press(K.E, 3)
        opened = self.talking()
        chose = self.choose(choice) if (opened and choice) else False
        for _ in range(6):
            if not self.talking():
                break
            self.press(K.E, 3)
        return {"walk": walked, "opened": opened, "chose": chose, "still_talking": self.talking()}

    # ------------------------------------------------------------------------------------------------- reading
    def hero(self) -> Any:
        return self.sc._find_player_sprite()

    def named(self, name: str) -> Any:
        return next((s for s in self.sc.all_sprites if getattr(s, "mesh_name", "") == name), None)

    def behaviour(self, name: str, kind: str) -> Any:
        sprite = self.named(name)
        return next((b for b in (sprite.mesh_behaviours_runtime if sprite else []) if type(b).__name__ == kind), None)

    def room(self) -> str:  # (after a load, current_scene_path is the save slot; room_path the room it was made in)
        return Path(str(getattr(self.sc, "room_path", "") or getattr(self.sc, "current_scene_path", "") or "")).stem

    def gold(self) -> float:
        return float(self.gs.get_counter("gold", 0) or 0)

    def potions(self) -> int:
        from engine.inventory import get_or_create_inventory

        return int(get_or_create_inventory(self.gs.state.values).get_count("healing_potion"))

    def quest(self) -> dict[str, Any]:
        return copy.deepcopy(dict((self.gs.state.values.get("quests") or {}).get("vault_quest") or {}))

    def snapshot(self) -> dict[str, Any]:
        gate = self.behaviour("Gate", "DoorLock")
        chest = self.behaviour("Chest", "RewardChest")
        return {"room": self.room(), "gold": self.gold(), "potions": self.potions(), "quest": self.quest(),
                "elder_thanked": bool(self.gs.get_flag("elder_thanked")),
                "reached_vault": bool(self.gs.get_flag("reached_vault")),
                "vault_badge": self.gs.get_counter("vault_badge", 0),
                "gate_scene_seen": bool(self.gs.get_flag("gate_scene_seen")), "renown": self.gs.get_counter("renown", 0),
                "wolf_present": self.named("Wolf") is not None, "potion_present": self.named("Potion") is not None,
                "gate_locked": getattr(gate, "locked", None),
                "gate_solid": self.named("Gate") in self.sc.solid_sprites if self.named("Gate") else None,
                "chest_looted": getattr(chest, "looted", None)}

    def note(self, step: str, ok: bool, **detail: Any) -> None:
        facts["steps"][step] = {"ok": bool(ok), **detail}


# ------------------------------------------------------------------------------------------------------ the plays
def leave_and_return(p: Player) -> dict[str, Any]:
    """Through the door to the Shed (a 2D room), a few steps there, and back through its door."""
    out: dict[str, Any] = {"to_door": p.walk_to(*_door(p, "Door to Shed"), frames=900)}
    p.step(10)
    out["room_after_door"] = p.room()
    if out["room_after_door"] == "shed":
        hero = p.hero()
        x0 = hero.center_x
        p.hold({K.RIGHT})
        p.step(20)
        p.hold(set())
        p.step(2)
        out["moved_in_shed"] = round(p.hero().center_x - x0, 1)
        out["back"] = p.walk_to(*_door(p, "Door to Start"), frames=900)
        p.step(10)
    out["room_back"] = p.room()
    return out


def _door(p: Player, name: str) -> tuple[float, float]:
    door = p.named(name)
    return (door.center_x, door.center_y) if door is not None else (-1.0, -1.0)


def through_gate(p: Player, eastward: bool) -> dict[str, Any]:
    gate = p.named("Gate")
    side = 1 if eastward else -1
    first = p.walk_to(gate.center_x - side * 64, gate.center_y)
    second = p.walk_to(gate.center_x + side * 64, gate.center_y)
    hero = p.hero()
    return {"walk": [first, second], "passed": (hero.center_x - gate.center_x) * side > 40,
            "at": round(hero.center_x, 1)}


def play(p: Player) -> None:
    wolf_hp = p.behaviour("Wolf", "Health")
    hero_hp = next((b for b in p.hero().mesh_behaviours_runtime if type(b).__name__ == "Health"), None)
    facts["start"] = p.snapshot()
    facts["start"]["wolf_hp"] = [getattr(wolf_hp, "hp", None), getattr(wolf_hp, "max_hp", None)]
    facts["start"]["player_hp"] = [getattr(hero_hp, "hp", None), getattr(hero_hp, "max_hp", None)]

    # 1. The Elder: an "Only once" conversation whose "Thank you" is a "Choice once" reward (+25 gold).
    first = p.talk("Elder", "Thank you")
    paid = p.gold()
    again = p.talk("Elder", "Thank you")
    p.note("dialogue_once_reward", paid == 25.0 and p.gold() == 25.0 and first["chose"] and not again["opened"],
           first=first, again=again, gold_after_first=paid, gold_after_second=p.gold())
    p.note("quest_started", p.quest().get("status") == "active" and p.quest().get("current_stage") == "open_gate",
           quest=p.quest())

    # 2. A potion to pick up.
    p.approach("Potion")
    p.press(K.E, 3)
    p.note("pickup", p.potions() == 1 and p.named("Potion") is None, potions=p.potions())

    # 3. The Shopkeeper: E opens the shop, ENTER buys the first item (5 gold), ESC closes it.
    walked = p.approach("Merchant")
    p.press(K.E, 3)
    panel = p.window.ui_controller.shop_panel
    opened = bool(panel and panel.visible)
    before = (p.gold(), p.potions())
    if opened:
        p.press(K.ENTER, 2)
        p.press(K.ESCAPE, 2)
    p.note("shop_purchase", opened and p.potions() == before[1] + 1 and p.gold() == before[0] - 5,
           walk=walked, opened=opened, before=before, after=(p.gold(), p.potions()))

    # 4. The Wolf: attack (SPACE) from beside it until it is gone; it drops 5 gold.
    gold0, attacks = p.gold(), 0
    for _ in range(30):
        wolf = p.named("Wolf")
        if wolf is None or p.hero() is None:
            break
        p.walk_to(wolf.center_x - 28, wolf.center_y, tol=6, frames=120)
        p.press(K.RIGHT, 0)
        p.press(K.SPACE, 20)
        attacks += 1
    p.step(20)
    p.note("enemy_defeated", p.named("Wolf") is None and p.gold() == gold0 + 5,
           attacks=attacks, gold_before=gold0, gold_after=p.gold(), wolf_hp_at_start=facts["start"]["wolf_hp"])

    # 5. The Button opens the gate; walk through it.
    walked = p.approach("Lever")
    p.press(K.E, 5)
    lock = p.behaviour("Gate", "DoorLock")
    unlocked = lock is not None and not lock.locked
    p.step(30)  # (the cutscene the button's event starts: a flag and a counter)
    p.note("cutscene_plays", bool(p.gs.get_flag("gate_scene_seen")) and p.gs.get_counter("renown", 0) == 1,
           renown=p.gs.get_counter("renown", 0))
    crossing = through_gate(p, eastward=True)
    p.note("lever_unlocks_gate_and_walk_through", unlocked and crossing["passed"], walk=walked, unlocked=unlocked,
           crossing=crossing, gate_solid=p.named("Gate") in p.sc.solid_sprites)
    stages = p.quest()
    p.note("quest_stage_advances", stages.get("completed_stages") == ["open_gate"]
           and stages.get("current_stage") == "enter_vault", quest=stages)

    # 6. The chest behind the gate (+10 gold).
    gold0 = p.gold()
    walked = p.approach("Chest")
    p.press(K.E, 3)
    chest = p.behaviour("Chest", "RewardChest")
    p.note("chest_opens", p.gold() == gold0 + 10 and bool(getattr(chest, "looted", False)), walk=walked,
           gold_before=gold0, gold_after=p.gold())

    # 7. The zone: its event sets reached_vault, which completes the quest.
    zone = p.named("VaultZone")
    walked = p.walk_to(zone.center_x, zone.center_y)
    p.step(10)
    p.note("zone_event", bool(p.gs.get_flag("reached_vault")), walk=walked)
    p.note("quest_completed", p.quest().get("status") == "completed" and p.gs.get_counter("vault_badge", 0) == 1,
           quest=p.quest(), vault_badge=p.gs.get_counter("vault_badge", 0))

    # 8. Back through the gate, out through the door to the Shed and back: nothing repeats on re-entry.
    back = through_gate(p, eastward=False)
    trip = leave_and_return(p)
    p.note("door_to_2d_room_and_back", trip.get("room_after_door") == "shed" and trip.get("room_back") == "start"
           and (trip.get("moved_in_shed") or 0) > 10, back_through_gate=back, trip=trip)
    revisit(p, "reentry")
    facts["before_save"] = p.snapshot()
    p.press(K.F5, 5)  # quick save
    facts["saves"] = p.window.save_manager.list_saves()


def revisit(p: Player, when: str) -> None:
    """After coming back (re-entry, or a load in a new process): nothing pays twice, and the gate stays open."""
    gold0 = p.gold()
    elder = p.talk("Elder", "Thank you")
    crossing = through_gate(p, eastward=True)
    p.approach("Chest")
    p.press(K.E, 3)
    snap = p.snapshot()
    p.note(f"{when}_nothing_repeats", gold0 == p.gold() and not elder["opened"] and crossing["passed"]
           and snap["chest_looted"] is True and not snap["wolf_present"] and not snap["potion_present"],
           gold_before=gold0, gold_after=p.gold(), elder=elder, crossing=crossing, snapshot=snap)
    through_gate(p, eastward=False)


def resume(p: Player) -> None:
    facts["slots_at_start"] = p.window.save_manager.list_saves()
    facts["before_load"] = p.snapshot()  # (a new game: nothing done yet)
    p.press(K.F9, 3)  # quick load
    p.step(5)
    facts["after_load"] = p.snapshot()
    revisit(p, "after_load")
    trip = leave_and_return(p)
    revisit(p, "after_load_reentry")
    facts["after_load_trip"] = trip


def export_play(p: Player) -> None:
    facts["slots_at_start"] = p.window.save_manager.list_saves()
    hero = p.hero()
    x0 = hero.center_x
    p.hold({K.RIGHT})
    p.step(30)
    p.hold(set())
    p.step(2)
    p.note("exported_walks", p.hero().center_x > x0 + 20, moved=round(p.hero().center_x - x0, 1))
    talk = p.talk("Elder", "Thank you")
    p.note("exported_reward", p.gold() == 25.0, gold=p.gold(), talk=talk)
    facts["before_save"] = p.snapshot()
    p.press(K.F5, 5)
    facts["saves"] = p.window.save_manager.list_saves()


def export_resume(p: Player) -> None:
    facts["slots_at_start"] = p.window.save_manager.list_saves()
    facts["before_load"] = p.snapshot()
    p.press(K.F9, 3)
    p.step(5)
    facts["after_load"] = p.snapshot()


def smoke(p: Player) -> None:
    """A template's start: the room, a player, and arrow keys move it."""
    facts["room"] = p.room()
    facts["sprites"] = len(list(p.sc.all_sprites))
    hero = p.hero()
    facts["player"] = hero is not None
    if hero is not None:
        x0, y0 = hero.center_x, hero.center_y
        for key in (K.RIGHT, K.LEFT, K.UP, K.DOWN):
            p.hold({key})
            p.step(20)
            p.hold(set())
            p.step(2)
            hero = p.hero()
            if abs(hero.center_x - x0) + abs(hero.center_y - y0) > 10:
                break
        facts["moved"] = round(abs(hero.center_x - x0) + abs(hero.center_y - y0), 1)
    # An HD-2D room's frame is drawn only where GL rendering is tested (the gpu lane: smoke_draw).
    facts["hd2d"] = p.window.hd2d_renderer is not None
    if MODE == "smoke_draw" or not facts["hd2d"]:
        facts["colours"] = p.draw()


def hd2d(p: Player) -> None:
    """Through a door into an HD-2D room: it renders, the player walks, a frame draws; then back through its door."""
    out: dict[str, Any] = {"to_door": p.walk_to(*_door(p, "Door to Glade"))}
    p.step(10)
    out.update(room=p.room(), renderer=p.window.hd2d_renderer is not None, error=getattr(p.window, "hd2d_error", None))
    if out["room"] == "glade":
        x0 = p.hero().center_x
        p.hold({K.RIGHT})
        p.step(30)
        p.hold(set())
        p.step(2)
        out["moved"] = round(p.hero().center_x - x0, 1)
        out["colours"] = p.draw()
        out["back"] = p.walk_to(*_door(p, "Door to Start"))
        p.step(10)
    out["room_back"] = p.room()
    out["colours_back"] = p.draw()
    facts["hd2d"] = out


PLAYS = {"play": play, "resume": resume, "export_play": export_play, "export_resume": export_resume, "smoke": smoke,
         "smoke_draw": smoke, "hd2d": hd2d}


def drive(window: Any) -> None:
    p = Player(window)
    facts["save_dir"] = str(window.save_manager.save_dir)
    menu = getattr(window, "main_menu_overlay", None)
    facts["main_menu_open"] = bool(menu is not None and getattr(menu, "visible", False))
    p.step(5)
    try:
        PLAYS[MODE](p)
        if MODE in ("play", "resume", "export_play", "export_resume"):
            facts["colours"] = p.draw()  # (a 2D room's frame, at the end)
    except Exception:  # (reported, with the facts so far, to the test)
        facts["error"] = traceback.format_exc()
    finally:
        window.close()


GameWindow.run = drive  # type: ignore[method-assign]
try:
    runpy.run_path(str(GAME / "main.py"), run_name="__main__")
except SystemExit:
    pass
print("MESH-E2E " + json.dumps(facts, default=str), flush=True)
