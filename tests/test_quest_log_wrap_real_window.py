"""The Quest Log keeps every text inside its panel (owner playtest of Lantern Road: "Objective: Bandits on the Forest
Pa..." ran off the panel's right edge, #765).

In a real (hidden) GameWindow: quests with long titles and objectives, the Quest Log open, a frame drawn. Each line is
taken from the draw call itself (its text, position and font size) and measured again here in a fresh arcade.Text:
titles stay in the left column, status and objective in the right one, both inside the panel's padding, wrapped
titles push the next title down, the selected quest's title is always on screen, and what doesn't fit stops above the
"Press Q to close" hint, its last line ending in an ellipsis.
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
ELLIPSIS = "\u2026"
LONG_TITLE = "Escort the lantern keeper's apprentice through the flooded crypt beneath the old watchtower"
LONG_OBJECTIVE = ("Bandits on the Forest Path have taken the shrine's last lamp oil; follow their tracks past the mill, "
                  "through the flooded crypt and up to the watchtower before nightfall, then bring the oil back to the "
                  "shrine keeper")
QUESTS = [
    ("relight", "Relight the shrine lantern", "Bandits on the Forest Path"),
    ("escort", LONG_TITLE, LONG_OBJECTIVE),
    ("ferry", "Find the ferryman", "Ask at the docks"),
]
MANY = [(f"q{n:02d}", f"Quest {n}: carry the lantern oil from the old mill to the shrine", f"Errand number {n}")
        for n in range(45)]


def _draw_quest_log(root: Path, size: tuple[int, int], selected: int, monkeypatch: pytest.MonkeyPatch,
                    quests: list[tuple[str, str, str]] = QUESTS):
    """Open the Quest Log on ``quests`` with quest ``selected`` chosen and draw a frame. Returns (lines, window width,
    window height): each line (kind, text, left, top, width, height), the text, position and font size as passed to
    the draw call, the width and height measured here. A second frame draws the same and makes no new Text."""
    from engine.config import load_config
    from engine.game import GameWindow
    from engine.studio_project import Project
    from engine.text_draw import get_text_scale
    from engine.ui_overlays import hud

    create_project(root, "Game", template_id="blank")
    data = [{"id": quest_id, "title": title, "stages": [{"id": "go", "text": objective}]}
            for quest_id, title, objective in quests]
    (root / "assets" / "data").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "data" / "quests.json").write_text(json.dumps({"quests": data}), encoding="utf-8")
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
        for quest_id, _, _ in quests:
            window.quest_manager.start_quest(quest_id)
        log = window.ui_controller.quest_log
        log.set_visible(True)
        for _ in range(selected):
            log.on_key_press(optional_arcade.arcade.key.DOWN)

        calls: list[tuple[str, float, float, float]] = []
        draw = hud.draw_text_cached

        def recording(text: str, x: float, y: float, **kwargs):
            if kwargs.get("cache") is log._text_cache:
                calls.append((text, x, y, kwargs.get("font_size", 12.0)))
            return draw(text, x, y, **kwargs)

        monkeypatch.setattr(hud, "draw_text_cached", recording)
        window.on_draw()
        first, texts = list(calls), {id(t) for t in log._text_cache._cache.values()}
        calls.clear()
        window.on_draw()
        assert calls == first, "the second frame draws the same"
        assert {id(t) for t in log._text_cache._cache.values()} == texts, "the second frame made new Text objects"

        assert first, "the Quest Log drew nothing"
        assert [line[1] for line in log.drawn_lines] == [call[0] for call in first]
        text_class = optional_arcade.arcade.Text
        measured = []
        for (kind, *_), (text, x, y, font_size) in zip(log.drawn_lines, first):
            probe = text_class(text, 0, 0, font_size=font_size * get_text_scale(), anchor_y="top")
            measured.append((kind, text, x, y, float(probe.content_width), float(probe.content_height)))
        return measured, window.width, window.height
    finally:
        dispose_game_window(window)


def _panel(width: int) -> tuple[float, float, float]:
    """The panel's left, right and bottom edges, as QuestLog.draw lays it out."""
    panel_width = min(420.0, max(280.0, width * 0.4))
    right = width - 24.0
    return right - panel_width, right, 72.0


def _assert_inside(lines, width: int) -> None:
    left, right, bottom = _panel(width)
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

    spans: dict[str, tuple[float, float]] = {}
    for kind, _, _, top, _, line_height in titles:
        high, low = spans.get(kind, (top, top - line_height))
        spans[kind] = (max(high, top), min(low, top - line_height))
    ordered = [spans[k] for k in sorted(spans, key=lambda k: int(k.split(":")[1]))]
    for (_, low), (high, _) in zip(ordered, ordered[1:]):
        assert high <= low, f"two titles overlap: {ordered}"


@pytest.mark.parametrize("size", [(1280, 720), (800, 600)])
def test_every_quest_log_text_stays_inside_its_panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                     size: tuple[int, int]) -> None:
    lines, width, _ = _draw_quest_log(tmp_path / "game", size, 1, monkeypatch)
    _assert_inside(lines, width)
    assert len([line for line in lines if line[0] == "title:1"]) > 1, "the long title wraps"


def test_the_whole_objective_is_shown_when_it_fits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lines, _, _ = _draw_quest_log(tmp_path / "game", (1280, 720), 1, monkeypatch)
    words = " ".join(text for kind, text, *_ in lines if kind == "detail").split()
    assert words == f"Status: Active Objective: {LONG_OBJECTIVE}".split(), "every word, in order, no ellipsis"
    title = " ".join(text for kind, text, *_ in lines if kind == "title:1").split()
    assert title == LONG_TITLE.split()


def test_the_owner_s_lantern_quest_wraps_its_objective(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lines, _, _ = _draw_quest_log(tmp_path / "game", (1280, 720), 0, monkeypatch)
    detail = [text for kind, text, *_ in lines if kind == "detail"]
    assert detail[0] == "Status: Active"
    assert " ".join(detail[1:]) == "Objective: Bandits on the Forest Path" and len(detail) > 2, detail


def test_an_objective_cut_short_ends_in_an_ellipsis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lines, width, _ = _draw_quest_log(tmp_path / "game", (800, 600), 1, monkeypatch)
    _assert_inside(lines, width)
    detail = [text for kind, text, *_ in lines if kind == "detail"]
    assert detail[-1].endswith(ELLIPSIS), detail
    assert sum(text.endswith(ELLIPSIS) for text in detail) == 1, "only the last line kept"
    shown = " ".join(detail).replace(ELLIPSIS, "").split()
    assert len(shown) < len(f"Status: Active Objective: {LONG_OBJECTIVE}".split()), "the objective was cut short"


@pytest.mark.parametrize("size", [(1280, 720), (800, 600)])
def test_the_selected_quest_s_title_stays_in_view(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                  size: tuple[int, int]) -> None:
    lines, width, _ = _draw_quest_log(tmp_path / "game", size, len(MANY) - 1, monkeypatch, MANY)
    _assert_inside(lines, width)
    last = f"title:{len(MANY) - 1}"
    title = " ".join(text for kind, text, *_ in lines if kind == last).split()
    assert title == MANY[-1][1].split(), "the selected (last) quest's title is shown whole"
    detail = " ".join(text for kind, text, *_ in lines if kind == "detail")
    assert detail.endswith(MANY[-1][2]), "and its details"
