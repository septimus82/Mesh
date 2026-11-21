"""SL-2: one quest event is one reaction for a SetGameStateOnEvent listener (Ember Hollow).

Real runtime: a hidden GameWindow, a real room with a SetGameStateOnEvent object, a quest whose stage completes
through the production QuestManager. The behaviour subscribed on the event bus AND received every event again in
the scene's per-frame delivery, so its counters and toast ran twice for one event.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

from engine import optional_arcade
from tests._b01_arena import PIC, Arena, close_window, make_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

HERO = {"id": "hero", "name": "Hero", "tag": "player", "x": 50, "y": 50, "sprite": PIC}


def _listener(event_type: str, **cfg: Any) -> dict[str, Any]:
    return {"id": "listener", "name": "Listener", "x": 0, "y": 0, "sprite": PIC, "layer": "background",
            "behaviours": ["SetGameStateOnEvent"],
            "behaviour_config": {"SetGameStateOnEvent": {"event_type": event_type, **cfg}}}


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        yield Arena(window, tmp_path)
    finally:
        close_window(window)


def _install_quest(window: Any) -> None:
    qm = window.quest_manager
    quest = qm._normalize_quest({
        "id": "hunt", "title": "Hunt", "description": "",
        "stages": [{"id": "cull", "title": "Cull", "text": "Cull.",
                    "complete_event": {"type": "culled"}}],
        "reward": {"set_flags": {}, "inc_counters": {}}})
    assert quest is not None
    qm._definitions = {quest["id"]: quest}
    qm._rebuild_stage_lookup()
    qm.reload_from_state()


def test_stage_completed_reacts_once(arena: Arena) -> None:
    arena.write_room(HERO, _listener("quest_stage_completed", payload_field="stage_id", payload_value="cull",
                                     inc_counters={"stages_done": 1}, toast="Culled!"))
    arena.enter()
    window = arena.window
    _install_quest(window)
    bus_seen: list[Any] = []
    window.event_bus.subscribe("quest_stage_completed", bus_seen.append)
    toasts: list[str] = []
    orig = window.player_hud.enqueue_toast
    window.player_hud.enqueue_toast = lambda text, **kw: (toasts.append(text), orig(text, **kw))[1]

    window.emit_signal("culled")
    window.on_update(1 / 60)  # the frame that runs the quest manager and delivers queued events
    window.on_update(1 / 60)

    assert len(bus_seen) == 1  # the bus carried the stage completion once ...
    assert window.get_counter("stages_done") == 1  # ... and the listener counted it once
    assert toasts.count("Culled!") == 1
