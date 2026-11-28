"""The Quest Log keeps every text inside its panel (owner playtest of Lantern Road: "Objective: Bandits on the Forest
Pa..." ran off the panel's right edge).

In a real (hidden) GameWindow: quests with long titles and objectives, the Quest Log open, one frame drawn. Each line
it drew is measured again here in a fresh arcade.Text of the same font: titles stay in the left column, status and
objective in the right one, both inside the panel's padding, wrapped titles push the next title down, and what doesn't
fit stops above the "Press Q to close" hint.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import engine.optional_arcade as optional_arcade
from engine.project_scaffold import create_project
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)"),
              pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function")]

PADDING = 20.0
LONG_TITLE = "Escort the lantern keeper's apprentice through the flooded crypt beneath the old watchtower"
LONG_OBJECTIVE = ("Bandits on the Forest Path have taken the shrine's last lamp oil; follow their tracks past the mill, "
                  "through the flooded crypt and up to the watchtower before nightfall, then bring the oil back to the "
                  "shrine keeper")
QUESTS = [
    ("relight", "Relight the shrine lantern", "Bandits on the Forest Path"),
    ("escort", LONG_TITLE, LONG_OBJECTIVE),
    ("ferry", "Find the ferryman", "Ask at the docks"),
]


def _draw_quest_log(root: Path, size: tuple[int, int], selected: int, monkeypatch: pytest.MonkeyPatch):
    """Open the Quest Log on ``QUESTS`` with quest ``selected`` chosen and draw one frame. Returns (lines drawn,
    window width, window height): each line (kind, text, left, top, its width measured here, its height)."""
    from engine.config import load_config
    from engine.game import GameWindow
    from engine.studio_project import Project

    create_project(root, "Game", template_id="blank")
    quests = [{"id": quest_id, "title": title, "stages": [{"id": "go", "text": objective}]}
              for quest_id, title, objective in QUESTS]
    (root / "assets" / "data").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "data" / "quests.json").write_text(json.dumps({"quests": quests}), encoding="utf-8")
    monkeypatch.chdir(root)
    monkeypatch.setenv("MESH_SAVE_DIR", str(root.parent / "saves"))
    config = load_config(str(root / "config.json"))
    config.tour_completed = True
    window = GameWindow(width=size[0], height=size[1], title=config.title, vsync=False, config=config)
    try:
        project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
        window.load_scene(project.path(project.current))
        if window.main_menu_overlay.visible:
            window.main_menu_overlay.close()
        for quest_id, _, _ in QUESTS:
            window.quest_manager.start_quest(quest_id)
        log = window.ui_controller.quest_log
        log.set_visible(True)
        for _ in range(selected):
            log.on_key_press(optional_arcade.arcade.key.DOWN)
        window.on_draw()
        assert log.drawn_lines, "the Quest Log drew nothing"
        text_class = optional_arcade.arcade.Text
        measured = []
        for kind, text, left, top, _width, _height in log.drawn_lines:
            probe = text_class(text, 0, 0, font_size=14 if kind.startswith("title") else 12, anchor_y="top")
            measured.append((kind, text, left, top, float(probe.content_width), float(probe.content_height)))
        return measured, window.width, window.height
    finally:
        dispose_game_window(window)


def _panel(width: int, height: int) -> tuple[float, float, float]:
    """The panel's left, right and bottom edges, as QuestLog.draw lays it out."""
    panel_width = min(420.0, max(280.0, width * 0.4))
    right = width - 24.0
    return right - panel_width, right, 72.0


@pytest.mark.parametrize("size", [(1280, 720), (800, 600)])
def test_every_quest_log_text_stays_inside_its_panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                     size: tuple[int, int]) -> None:
    lines, width, height = _draw_quest_log(tmp_path / "game", size, 1, monkeypatch)
    left, right, bottom = _panel(width, height)
    titles = [line for line in lines if line[0].startswith("title")]
    details = [line for line in lines if line[0] == "detail"]
    assert titles and details, lines

    for kind, text, x, top, line_width, line_height in lines:
        assert x >= left + PADDING, (kind, text)
        assert x + line_width <= right - PADDING, f"{text!r} runs past the panel's right edge"
        assert top - line_height >= bottom + 40.0, f"{text!r} reaches the 'Press Q to close' hint"

    title_right = max(x + w for _, _, x, _, w, _ in titles)
    detail_left = min(x for _, _, x, _, _, _ in details)
    assert title_right < detail_left, "a title runs into the right column"

    long_title = [line for line in titles if line[0] == "title:1"]
    assert len(long_title) > 1, "the long title wraps"
    spans = {}
    for kind, _, _, top, _, line_height in titles:
        high, low = spans.get(kind, (top, top - line_height))
        spans[kind] = (max(high, top), min(low, top - line_height))
    ordered = [spans[k] for k in sorted(spans, key=lambda k: int(k.split(":")[1]))]
    for (_, low), (high, _) in zip(ordered, ordered[1:]):
        assert high <= low, f"two titles overlap: {ordered}"


def test_the_whole_objective_is_shown_when_it_fits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lines, _, _ = _draw_quest_log(tmp_path / "game", (1280, 720), 1, monkeypatch)
    words = " ".join(text for kind, text, *_ in lines if kind == "detail").split()
    assert words == f"Status: Active Objective: {LONG_OBJECTIVE}".split(), "every word, in order"
    title = " ".join(text for kind, text, *_ in lines if kind == "title:1").split()
    assert title == LONG_TITLE.split()


def test_the_owner_s_lantern_quest_wraps_its_objective(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lines, _, _ = _draw_quest_log(tmp_path / "game", (1280, 720), 0, monkeypatch)
    detail = [text for kind, text, *_ in lines if kind == "detail"]
    assert detail[0] == "Status: Active"
    assert " ".join(detail[1:]) == "Objective: Bandits on the Forest Path" and len(detail) > 2, detail
