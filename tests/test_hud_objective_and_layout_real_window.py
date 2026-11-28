"""The HUD's "Objective:" line follows the active quest, and the HUD's boxes don't overlap (Lantern Road round 4 and
the final remediation smoke after #745: #768, #769).

1. The objective came from the first active quest, else from *any* quest: the listing has every quest, so before a
   quest was accepted, and after it was completed, its objective was still on screen. Now: nothing before acceptance,
   the current stage's objective while it runs, nothing (or the next active quest's) once it's done; the same after a
   save is loaded in a fresh window.
2. At 800x600 the controls hint ("Q: Quest Log  Tab: Inventory ...") ran under the open Quest Log panel: a toast now
   wraps to the panel's left while it's open.

In a real (hidden) GameWindow; the rectangles are the ones the draw itself recorded (``PlayerHUD.drawn``,
``QuestLog.panel_rect``). Studio's play bar against the HP bar and objective: tests/test_hud_studio_play_bar_gpu.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.project_scaffold import create_project
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)"),
              pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function")]

START = "packs/core_regions/scenes/start.json"
CONTROLS_HINT = "Q: Quest Log  Tab: Inventory  I: Inspector  C: Character  H: Help"
QUESTS = [  # (given by someone: they wait to be accepted)
    {"id": "oil", "title": "Lamp oil", "auto_start": False,
     "stages": [{"id": "find", "title": "Find the oil", "text": "Search the mill"},
                {"id": "bring", "title": "Bring it back", "text": "The shrine keeper waits"}]},
    {"id": "ferry", "title": "Find the ferryman", "auto_start": False,
     "stages": [{"id": "ask", "title": "Ask at the docks", "text": "Someone there knows him"}]},
    {"id": "letter", "title": "The keeper's letter", "auto_start": False,  # (a ~200-character objective)
     "stages": [{"id": "carry", "title": "Carry the letter",
                 "text": ("Take the sealed letter from the shrine keeper past the old mill and the flooded crypt, "
                          "then up the watchtower stairs before nightfall, and hand it to the lantern keeper "
                          "waiting at the top")}]},
]


def _project(root: Path) -> Path:
    create_project(root, "Game", template_id="blank")
    (root / "assets" / "data").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "data" / "quests.json").write_text(json.dumps({"quests": QUESTS}), encoding="utf-8")
    prefabs = json.loads((root / "assets" / "prefabs.json").read_text(encoding="utf-8"))
    player = next(p for p in prefabs if p["id"] == "player")["entity"]  # (the shared player every room uses)
    player["behaviours"] = [*player["behaviours"], "Health"]  # (the HUD draws its stats for a player with health)
    player["behaviour_config"]["Health"] = {"max_hp": 10, "hp": 10}
    (root / "assets" / "prefabs.json").write_text(json.dumps(prefabs), encoding="utf-8")
    return root


def _window(root: Path, size: tuple[int, int], monkeypatch: pytest.MonkeyPatch) -> Any:
    from engine.config import load_config
    from engine.game import GameWindow

    monkeypatch.chdir(root)
    monkeypatch.setenv("MESH_SAVE_DIR", str(root.parent / "saves"))
    config = load_config(str(root / "config.json"))
    config.tour_completed = True
    window = GameWindow(width=size[0], height=size[1], title=config.title, vsync=False, config=config)
    window.load_scene(START)
    if window.main_menu_overlay.visible:
        window.main_menu_overlay.close()
    return window


def _objective(window: Any) -> str | None:
    """The objective the HUD draws now (None: none drawn)."""
    window.on_draw()
    assert "hp" in window.player_hud.drawn, "the HUD didn't draw (no player with health?)"
    drawn = window.player_hud.drawn.get("objective")
    return drawn[0] if drawn else None


def test_the_objective_follows_the_active_quest_and_a_loaded_save(tmp_path: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    root = _project(tmp_path / "game")
    window = _window(root, (1280, 720), monkeypatch)
    try:
        quests = window.quest_manager
        assert _objective(window) is None, "an objective before any quest was accepted"
        assert quests.start_quest("oil") is True
        assert _objective(window) == "Objective: Find the oil\nSearch the mill"
        assert quests.complete_stage("oil", "find") is True
        assert _objective(window) == "Objective: Bring it back\nThe shrine keeper waits"
        assert window.save_manager.save_game("midway")
        assert quests.complete_stage("oil", "bring") is True and quests.is_quest_completed("oil")
        assert _objective(window) is None, "the completed quest's objective is still shown"
        assert window.save_manager.save_game("done")
        assert quests.start_quest("ferry") is True
        assert _objective(window) == "Objective: Ask at the docks\nSomeone there knows him", "the next active quest's"
    finally:
        dispose_game_window(window)

    window = _window(root, (1280, 720), monkeypatch)  # a fresh window: the saves loaded
    try:
        assert _objective(window) is None
        assert window.save_manager.load_game("midway")
        assert _objective(window) == "Objective: Bring it back\nThe shrine keeper waits"
        assert window.save_manager.load_game("done")
        assert window.quest_manager.is_quest_completed("oil")
        assert _objective(window) is None, "the loaded completed quest's objective is shown"
    finally:
        dispose_game_window(window)


def _apart(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    """Rectangles (left, bottom, right, top) that don't overlap (touching edges are apart)."""
    return a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


@pytest.mark.parametrize("size", [(800, 600), (1280, 720)])
def test_the_hud_boxes_and_the_open_quest_log_do_not_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                             size: tuple[int, int]) -> None:
    window = _window(_project(tmp_path / "game"), size, monkeypatch)
    try:
        assert window.quest_manager.start_quest("oil") is True
        hud = window.player_hud
        hud.enqueue_toast(CONTROLS_HINT, seconds=30.0)
        window.on_draw()  # the Quest Log closed: the HP bar, the objective and the toasts
        closed = dict(hud.drawn)
        assert {"hp", "objective"} <= set(closed) and CONTROLS_HINT in [v[0] for v in closed.values()], closed
        log = window.ui_controller.quest_log
        log.set_visible(True)
        window.on_draw()
        boxes = {kind: rect for kind, (_text, *rect) in hud.drawn.items()}
        assert "objective" not in boxes, "the objective shows while the Quest Log is open"
        assert any(text == CONTROLS_HINT for text, *_ in hud.drawn.values()), "the controls hint went"
        panel = log.panel_rect()
        assert log.drawn_panel == panel, f"the Quest Log drew {log.drawn_panel}, not its panel_rect() {panel}"
        assert log.drawn_lines, "the Quest Log drew no text"
        for kind, text, x, top, line_width, line_height in log.drawn_lines:
            inside = panel[0] <= x and x + line_width <= panel[2] and panel[1] <= top - line_height and top <= panel[3]
            assert inside, f"{kind} {text!r} lies outside the panel {panel}"
        for kind, rect in boxes.items():
            assert _apart(rect, panel), f"{kind} {rect} overlaps the open Quest Log {panel}"
        _assert_all_apart(closed)
    finally:
        dispose_game_window(window)


def _assert_all_apart(drawn: dict[str, tuple[str, float, float, float, float]]) -> None:
    boxes = {kind: rect for kind, (_text, *rect) in drawn.items()}
    kinds = sorted(boxes)
    for n, a in enumerate(kinds):
        for b in kinds[n + 1:]:
            assert _apart(boxes[a], boxes[b]), f"{a} {boxes[a]} overlaps {b} {boxes[b]}"


@pytest.mark.parametrize("size", [(800, 600), (640, 480)])
def test_a_long_objective_and_a_wide_toast_do_not_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                          size: tuple[int, int]) -> None:
    # A ~200-character objective reaches down past the toasts' top: the controls hint wraps to its left.
    window = _window(_project(tmp_path / "game"), size, monkeypatch)
    try:
        assert window.quest_manager.start_quest("letter") is True
        hud = window.player_hud
        hud.enqueue_toast(CONTROLS_HINT, seconds=30.0)
        window.on_draw()
        objective = hud.drawn["objective"]
        assert objective[0].startswith("Objective: Carry the letter") and objective[2] < size[1] - 110, objective
        assert CONTROLS_HINT in [text for text, *_ in hud.drawn.values()], hud.drawn
        _assert_all_apart(hud.drawn)
    finally:
        dispose_game_window(window)
