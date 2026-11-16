"""Mesh Studio's side panels scroll without building the editor again (hidden window, worked through input events).

A wheel notch over the Inspector or the Tools panel shows other rows of the rows that panel already has
(``Studio._rewindow``): nothing is rebuilt, the other panel and the top bar keep their very widgets, and what the
person then sees and can click is exactly what a full rebuild at that scroll would have made. Everything is built
again, as every notch used to do, where the rows kept may not be current: text typed and not yet committed, a menu
open, an edit behind the panels, another room, a resized window.
Set MESH_GL_SMOKE=1."""

from __future__ import annotations

import gc
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
SCENE = "packs/core_regions/scenes/start.json"
LINES = ["Have you seen the old mill?", "It stopped turning the winter the river froze.", "My father kept its wheel.",
         "He said the water remembers.", "Go and look, if you like.", "Mind the loose boards.", "And the owl.",
         "It has lived there longer than I have.", "Come back and tell me what you find.", "Safe roads."]
ELDER, PLAYER = "start_elder", "start_player_128_128_0_0"


class Counts:
    """What Studio does, counted from outside: full rebuilds, selective refreshes, widgets constructed."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import arcade.gui as gui

        from engine.studio import Studio

        self.rebuilds = self.rewindows = self.widgets = 0
        rebuild, rewindow, init = Studio._rebuild, Studio._rewindow, gui.UIWidget.__init__

        def counted_rebuild(studio: Any) -> None:
            self.rebuilds += 1
            rebuild(studio)

        def counted_rewindow(studio: Any, side: str) -> bool:
            done = rewindow(studio, side)
            self.rewindows += bool(done)
            return done

        def counted_init(widget: Any, *args: Any, **kwargs: Any) -> None:
            self.widgets += 1
            init(widget, *args, **kwargs)

        monkeypatch.setattr(Studio, "_rebuild", counted_rebuild)
        monkeypatch.setattr(Studio, "_rewindow", counted_rewindow)
        monkeypatch.setattr(gui.UIWidget, "__init__", counted_init)

    def take(self) -> tuple[int, int, int]:
        out = (self.rebuilds, self.rewindows, self.widgets)
        self.rebuilds = self.rewindows = self.widgets = 0
        return out


@pytest.fixture(scope="module")
def session(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    """Studio open on the HD-2D starter room, its elder given a conversation of ten more lines (a long Inspector)."""
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops
    from engine.project_scaffold import create_project

    project = tmp_path_factory.mktemp("panel_scroll") / "Panel scroll"
    create_project(project, "Panel scroll", "hd2d_rpg")
    path = project / SCENE
    scene = json.loads(path.read_text(encoding="utf-8"))
    for text in LINES:
        scene, _line = ops.add_line(scene, ELDER, text=text)
    for x, y in ((400.0, 800.0), (880.0, 800.0), (960.0, 1000.0)):
        scene, _index = ops.add_light(scene, x, y, color="Warm", radius=200)
    path.write_bytes(json.dumps(scene, indent=2).encode("utf-8"))
    d = StudioDriver(project)
    try:
        yield d
    finally:
        d.close()


@pytest.fixture
def d(session: Any) -> Any:
    """The session's Studio in a known state: 1280x720, nothing typed or refused, no edits, the elder's conversation
    in the Inspector at its top, the Rooms tools."""
    studio = session.studio
    if studio.mode != "edit":
        studio.stop()
    studio.menu = None
    studio._held.clear()
    studio._rebuild()
    while studio.project.can_undo():
        studio.undo()
    _size(session, 1280, 720)
    studio.panel, studio.show_left, studio.show_right = "inspect", True, True
    studio.set_left_tab("rooms")
    studio.select(None)
    studio.select(ELDER)
    session.advance(2)
    assert studio.tab == "dialogue" and studio.panel_scroll == 0 and not studio.project.can_undo()
    return session


# ------------------------------------------------------------------ as a person works it
def _size(d: Any, w: int, h: int) -> None:
    if (d.window.width, d.window.height) != (w, h):
        d.window.set_size(w, h)
        d.window.dispatch_event("on_resize", w, h)
    d.advance(2)


def _wheel(d: Any, side: str, notches: int) -> None:
    x = d.window.width - 100 if side == "right" else 100
    d.window.dispatch_event("on_mouse_scroll", x, d.window.height / 2, 0, notches)


def _more(d: Any, side: str) -> tuple[int, int]:
    above, below = d.studio._panel_more if side == "right" else d.studio._left_more
    return int(above), int(below)


def _to_end(d: Any, side: str, down: bool) -> int:
    """Wheel that way until nothing more is that way; how many notches it took."""
    notches = 0
    while _more(d, side)[1 if down else 0]:
        _wheel(d, side, -1 if down else 1)
        notches += 1
        assert notches < 200
    return notches


def _button(d: Any, text: str, *, prefix: bool = False) -> Any:
    for widget in d.studio.ui.walk_widgets():
        label = getattr(widget, "text", None)
        if hasattr(widget, "on_click") and isinstance(label, str) and (label == text or (prefix and label.startswith(text))):
            return widget
    return None


def _press(d: Any, widget: Any) -> None:
    d.advance()  # (laid out where it is now)
    r = widget.rect
    d.click(r.left + r.width / 2, r.bottom + r.height / 2)


def _click(d: Any, text: str, *, prefix: bool = False) -> None:
    widget = _button(d, text, prefix=prefix)
    assert widget is not None, f"no button {text!r} on screen: {_texts(d)}"
    _press(d, widget)


def _type(d: Any, key: str, text: str) -> Any:
    """Click the box, select what is in it and type: no Enter (the box stays being typed in)."""
    field = d.studio._focusable[key]
    assert field.get_ui_manager() is not None, f"the box {key!r} is not on screen"
    _press(d, field)
    k = d.arcade.key
    d.window.dispatch_event("on_key_press", k.A, k.MOD_CTRL)
    d.window.dispatch_event("on_key_release", k.A, k.MOD_CTRL)
    d.window.dispatch_event("on_text", text)
    return field


def _texts(d: Any) -> list[str]:
    return [w.text for w in d.studio.ui.walk_widgets() if isinstance(getattr(w, "text", None), str) and w.text]


def _side(d: Any, side: str) -> list[Any]:
    """The widgets of the left panel, the right panel or the top bar, as laid out."""
    from engine.studio import TOP_H

    left, right = d.studio._panel_widths()
    width, height = d.window.width, d.window.height
    d.studio.ui.execute_layout()
    out = []
    for widget in d.studio.ui.walk_widgets():
        r = widget.rect
        if r.width >= width - 40:
            continue  # (the root layout)
        top_bar = r.bottom >= height - TOP_H
        where = "top" if top_bar else "left" if r.right <= left + 1 else "right" if r.left >= width - right - 1 else "other"
        if where == side:
            out.append(widget)
    return out


def _entity(d: Any, entity_id: str) -> dict[str, Any]:
    from engine import project_ops as ops

    found: dict[str, Any] = ops.find_entity(d.studio.project.scene(), entity_id)
    return found


def _rect(widget: Any) -> list[float]:
    r = widget.rect
    return [round(r.left, 1), round(r.bottom, 1), round(r.width, 1), round(r.height, 1)]


def _studio_now(d: Any) -> dict[str, Any]:
    """Everything of Studio's panels a person can see or click, and what Studio keeps about it."""
    from engine.studio_inspector import _on_screen

    studio = d.studio
    studio.ui.execute_layout()
    widgets = []
    for w in studio.ui.walk_widgets():
        style = getattr(w, "_style", None) or getattr(w, "style", None)
        widgets.append([type(w).__name__, getattr(w, "text", None), _rect(w), getattr(w, "disabled", None),
                        json.dumps(style, sort_keys=True, default=str) if isinstance(style, dict) else None,
                        bool(getattr(w, "hovered", False)), bool(getattr(w, "pressed", False)),
                        bool(getattr(w, "_active", False)) and hasattr(w, "caret")])  # (a box being typed in)
    shown = {id(w) for w in studio.ui.walk_widgets()}
    keys = {id(f): key for key, f in studio._focusable.items()}
    return {
        "widgets": widgets,
        "scroll": [studio.panel_scroll, studio.left_scroll, list(studio._panel_more), list(studio._left_more)],
        "bars": {side: [round(v, 1) if isinstance(v, float) else v for v in bar] for side, bar in sorted(studio._bars.items())},
        "tips": sorted([tip, _rect(w)] for w, tip in studio.hd2d.tips),
        "sheet": _rect(studio._sheet_space) if studio._sheet_space is not None else None,
        "boxes": sorted([str(keys.get(id(f))), f.text, original, id(f) in shown, bool(f.active)]
                        for f, original, _commit in studio._fields),
        "pictures": sorted([str(path)[-40:], _rect(space)] for space, path in studio._thumbs if _on_screen(space)),
        "typing": studio._typing(),
    }


def _same_as_a_rebuild(d: Any, where: str) -> None:
    kept = _studio_now(d)
    d.studio._rebuild()
    rebuilt = _studio_now(d)
    for key in kept:
        assert kept[key] == rebuilt[key], f"{where}: the panel kept differs from a rebuild in its {key}"


def _panel_picture(d: Any, side: str) -> Any:
    """The panel as drawn, in a real frame."""
    left, right = d.studio._panel_widths()
    image = d.frame().convert("RGB")
    scale = image.width / d.window.width
    box = (0, 0, left, d.window.height) if side == "left" else (d.window.width - right, 0, d.window.width, d.window.height)
    return image.crop(tuple(int(v * scale) for v in box))


# ------------------------------------------------------------------ nothing is rebuilt, and nothing else is touched
def test_a_wheel_notch_over_the_inspector_builds_nothing_again_and_leaves_the_rest_alone(
        d: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    counts = Counts(monkeypatch)
    tools, top = _side(d, "left"), _side(d, "top")
    before = _texts(d)
    assert _more(d, "right") == (0, _more(d, "right")[1]) and _more(d, "right")[1] > 4, "a long Inspector, at its top"
    for notch in range(1, 4):
        counts.take()
        _wheel(d, "right", -1)
        rebuilds, rewindows, widgets = counts.take()
        assert (rebuilds, rewindows) == (0, 1), "one notch: the Inspector's rows in view, nothing rebuilt"
        assert widgets <= 4, f"{widgets} widgets made for one notch (the two 'more above / below' lines at most)"
        assert d.studio.panel_scroll == 2 * notch
    assert [id(w) for w in _side(d, "left")] == [id(w) for w in tools], "the Tools panel's own widgets, untouched"
    assert [id(w) for w in _side(d, "top")] == [id(w) for w in top], "the top bar's own widgets, untouched"
    assert _texts(d) != before and "^ 6 more above (scroll up)" in _texts(d)
    assert d.studio.selected == ELDER and d.studio.tab == "dialogue" and not d.studio.project.can_undo()


def test_a_wheel_notch_over_the_tools_builds_nothing_again_and_leaves_the_inspector_alone(
        d: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _size(d, 1100, 620)  # (a small laptop's window: the Environment tools don't fit it)
    _click(d, "Environment")
    d.advance()
    assert d.studio._panel_widths() == (230, 330) and _more(d, "left")[1] > 0, "both panels, the Tools one scrolling"
    counts = Counts(monkeypatch)
    inspector, top = _side(d, "right"), _side(d, "top")
    inspector_scroll = d.studio.panel_scroll
    seen = set(_texts(d))
    notches = 0
    while _more(d, "left")[1]:
        counts.take()
        _wheel(d, "left", -1)
        notches += 1
        assert counts.take()[:2] == (0, 1)
        seen |= set(_texts(d))
    assert notches >= 2 and d.studio.left_scroll == _more(d, "left")[0] > 0
    assert [id(w) for w in _side(d, "right")] == [id(w) for w in inspector], "the Inspector's own widgets, untouched"
    assert [id(w) for w in _side(d, "top")] == [id(w) for w in top]
    assert d.studio.panel_scroll == inspector_scroll and d.studio.selected == ELDER
    assert {"Lighting...", "Rain and weather sounds..."} <= seen, "the tools at the panel's end were scrolled into view"


@pytest.mark.parametrize("panel", ["conversation", "look", "one light", "models", "tools"])
def test_the_panel_kept_is_the_panel_a_rebuild_makes_at_every_scroll(d: Any, panel: str) -> None:
    """Down to the end and back up, a notch at a time: after each, Studio is what a rebuild at that scroll makes
    (every widget's kind, text, place, size, state and style; scrollbars; tooltips; boxes; pictures), and draws the
    same. The mouse is over one of the panel's buttons when it starts, as a person's is."""
    side = "right"
    if panel == "look":
        d.studio.select(PLAYER)
        d.advance()
        _click(d, "Look")
    elif panel == "one light":
        _click(d, "Lighting")
        _click(d, "Light 4", prefix=True)  # (one light's own settings under the list of lights)
    elif panel == "models":
        d.studio.hd2d.open_models()  # (a long list: its rows are made as they are first shown, with a picture each)
    elif panel == "tools":
        _size(d, 1100, 620)
        _click(d, "Environment")
        side = "left"
    d.advance()
    assert _more(d, side)[1] > 0, f"the {panel} panel scrolls"
    under = next(w for w in _side(d, side) if hasattr(w, "on_click"))
    d.window.dispatch_event("on_mouse_motion", under.rect.left + 6, under.rect.bottom + 6, 0, 0)
    assert under.hovered
    positions = 0
    for down in (True, False):
        while _more(d, side)[1 if down else 0]:
            _wheel(d, side, -1 if down else 1)
            positions += 1
            d.window.motion_time = d.window.water_time = 0.0
            kept = _panel_picture(d, side)
            _same_as_a_rebuild(d, f"{panel} at {_more(d, side)}")
            d.window.motion_time = d.window.water_time = 0.0
            assert kept.tobytes() == _panel_picture(d, side).tobytes(), f"{panel} at {_more(d, side)}: drawn differently"
    assert positions >= 4 and _more(d, side)[0] == 0


@pytest.mark.parametrize("side", ["right", "left"])
def test_notches_one_after_another_with_nothing_built_between_draw_what_a_rebuild_draws(
        d: Any, monkeypatch: pytest.MonkeyPatch, side: str) -> None:
    """A person's scroll: several notches down, and back, the same rows shown again where they were last drawn."""
    if side == "left":
        _size(d, 1100, 620)
        _click(d, "Environment")
        d.advance()
    counts = Counts(monkeypatch)
    for notches in ([-1, -1, -1], [1, 1], [-1], [1, 1]):
        for notch in notches:
            _wheel(d, side, notch)
        rebuilds, rewindows, _widgets = counts.take()
        assert rebuilds == 0 and rewindows >= 1, "only re-windowed (a notch past an end does nothing)"
        d.window.motion_time = d.window.water_time = 0.0
        kept = _panel_picture(d, side)
        d.studio._rebuild()
        d.window.motion_time = d.window.water_time = 0.0
        assert kept.tobytes() == _panel_picture(d, side).tobytes(), f"after {notches}: drawn differently"
        counts.take()
    assert _more(d, side)[0] == 0


def test_both_ends_of_the_inspector_are_reached_and_a_notch_past_them_does_nothing(
        d: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    counts = Counts(monkeypatch)
    lines: list[str] = []
    down = 0
    while True:
        lines.extend(t for t in _texts(d) if t[:1].isdigit() and ". " in t[:5] and t not in lines)
        if not _more(d, "right")[1]:
            break
        _wheel(d, "right", -1)
        down += 1
    for words in LINES:
        assert any(words[:16] in line for line in lines), f"the line {words!r} was never scrolled into view: {lines}"
    assert "v" not in "".join(t[:1] for t in _texts(d) if "more below" in t)
    at_bottom, tree = d.studio.panel_scroll, [id(w) for w in d.studio.ui.walk_widgets()]
    counts.take()
    _wheel(d, "right", -1)
    assert counts.take() == (0, 0, 0) and d.studio.panel_scroll == at_bottom
    assert [id(w) for w in d.studio.ui.walk_widgets()] == tree, "a notch past the bottom changes nothing"
    assert _to_end(d, "right", down=False) == down and d.studio.panel_scroll == 0
    tree = [id(w) for w in d.studio.ui.walk_widgets()]
    counts.take()
    _wheel(d, "right", 1)
    assert counts.take() == (0, 0, 0) and [id(w) for w in d.studio.ui.walk_widgets()] == tree
    assert not any("more above" in t for t in _texts(d))


def test_a_long_lists_rows_are_made_once_however_often_they_are_scrolled_past(d: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    d.studio.hd2d.open_models()
    d.advance()
    assert _more(d, "right")[1] > 0
    first = _to_end(d, "right", down=True)  # (each row made as it is first shown)
    _to_end(d, "right", down=False)
    pictures = len(d.studio._thumbs)
    counts = Counts(monkeypatch)
    assert _to_end(d, "right", down=True) == first and _to_end(d, "right", down=False) == first
    rebuilds, rewindows, widgets = counts.take()
    assert (rebuilds, rewindows) == (0, 2 * first) and widgets <= 4 * 2 * first, "no row is made a second time"
    assert len(d.studio._thumbs) == pictures, "nor its picture slot listed again"
    d.advance()
    shown = {id(w) for w in d.studio.ui.walk_widgets()}
    from engine.studio_inspector import _on_screen

    assert all((id(space) in shown) == _on_screen(space) for space, _path in d.studio._thumbs)
    assert any(not _on_screen(space) for space, _path in d.studio._thumbs), "pictures of rows out of view are not drawn"


# ------------------------------------------------------------------ what is clicked is what is under the mouse
def test_a_control_scrolled_into_view_is_clicked_where_it_is_shown(d: Any) -> None:
    _to_end(d, "right", down=True)
    last = next((w for w in d.studio.ui.walk_widgets() if hasattr(w, "on_click") and "Safe roads." in str(getattr(w, "text", ""))),
                None)
    assert last is not None, _texts(d)
    _press(d, last)  # the last line's own row: its editor opens for that line, not for whatever was there before
    assert d.studio.dlg_line is not None and d.studio._focusable["line_text"].text == "Safe roads."


def test_a_control_scrolled_away_and_back_still_does_its_own_action_and_undoes(d: Any) -> None:
    d.studio.select(PLAYER)
    d.advance()
    _click(d, "Look")
    d.advance()
    toggle = _button(d, "Mirrored", prefix=True)
    assert toggle is not None and toggle.text.endswith("Off")
    _to_end(d, "right", down=True)
    _to_end(d, "right", down=False)
    again = _button(d, "Mirrored", prefix=True)
    assert again is toggle, "the very button, kept while the panel only scrolled"
    before = dict(_entity(d, PLAYER))
    _press(d, again)
    after = _entity(d, PLAYER)
    changed = {key for key in set(before) | set(after) if before.get(key) != after.get(key)}
    assert len(changed) == 1 and _button(d, "Mirrored", prefix=True).text.endswith("On"), changed
    _click(d, "Undo")
    assert _entity(d, PLAYER) == before and not d.studio.project.can_undo()
    _click(d, "Redo")
    assert _entity(d, PLAYER) == after


def test_tooltips_are_where_their_buttons_are_shown_and_nowhere_else(d: Any) -> None:
    _size(d, 1100, 620)
    _click(d, "Environment")
    d.advance()
    hd2d = d.studio.hd2d
    assert hd2d.tips and _more(d, "left")[1] > 0
    at_top = {tip: _rect(w) for w, tip in hd2d.tips}
    _to_end(d, "left", down=True)
    d.advance()
    shown = {id(w) for w in d.studio.ui.walk_widgets()}
    assert hd2d.tips and all(id(w) in shown for w, _tip in hd2d.tips), "only buttons in view have a tooltip"
    gone = [tip for tip in at_top if tip not in {tip for _w, tip in hd2d.tips}]
    assert gone, "the tools scrolled out of view lost their tooltips"
    for tip in gone:  # (where such a button was, there is now another row, or nothing: never its tooltip)
        left, bottom, width, height = at_top[tip]
        assert hd2d.tooltip(left + width / 2, bottom + height / 2) != tip
    for widget, tip in hd2d.tips:
        left, bottom, width, height = _rect(widget)
        assert hd2d.tooltip(left + width / 2, bottom + height / 2) == tip
    _same_as_a_rebuild(d, "tools at the bottom")


def test_the_import_preview_is_drawn_only_while_its_row_is_in_view(d: Any) -> None:
    """The picture being imported is drawn over a slot in the panel: none where that row is scrolled out of view."""
    studio = d.studio
    _size(d, 1100, 560)
    studio.import_form.update(path=str(Path(studio.project.root) / "assets" / "sprites" / "hd2d_hero.png"), name="hero", tile="32")
    studio.panel = "import_tileset"
    studio._rebuild()
    d.advance()
    assert studio._spaces_built[1] is not None and _more(d, "right")[1] > 0, "the preview, in a panel that scrolls"
    seen = set()
    for down in (True, False):
        while True:
            slot = studio._spaces_built[1]
            in_view = slot.get_ui_manager() is not None
            assert studio._import_space is (slot if in_view else None), f"at {_more(d, 'right')}"
            seen.add(in_view)
            if not _more(d, "right")[1 if down else 0]:
                break
            _wheel(d, "right", -1 if down else 1)
            d.advance()
            _same_as_a_rebuild(d, f"importing, at {_more(d, 'right')}")
    assert seen == {True, False}, "the preview's row was scrolled into view and out of it"
    studio.panel = "inspect"
    studio._rebuild()


# ------------------------------------------------------------------ boxes
def test_a_box_being_typed_in_is_committed_once_to_its_own_property_by_the_wheel(
        d: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    before = dict(_entity(d, ELDER))
    field = _type(d, "name", "Elder Rowan")
    assert d.studio._typing() and field.text == "Elder Rowan" and _entity(d, ELDER) == before, "typed, not committed"
    counts = Counts(monkeypatch)
    _wheel(d, "right", -1)
    after = _entity(d, ELDER)
    changed = {key for key in set(before) | set(after) if before.get(key) != after.get(key)}
    # (a rename also renames the speaker of the object's own lines: its conversation, nothing else)
    assert {"name"} <= changed <= {"name", "behaviour_config"} and after["name"] == "Elder Rowan"
    assert counts.rebuilds >= 1 and counts.rewindows == 0, "a commit may change any row: everything is built again"
    assert d.studio.panel_scroll == 2 and not d.studio._typing() and d.studio.message_ok
    _click(d, "Undo")
    assert _entity(d, ELDER) == before and not d.studio.project.can_undo(), "one undo step, no more"


def test_a_box_only_clicked_is_left_untyped_in_by_the_wheel_and_nothing_is_committed(
        d: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    before = dict(_entity(d, ELDER))
    field = d.studio._focusable["name"]
    _press(d, field)
    assert field.active and d.studio._typing()
    counts = Counts(monkeypatch)
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (0, 1), "nothing typed: only the rows in view change"
    assert not field.active and not d.studio._typing(), "as after a rebuild, no box is being typed in"
    assert _entity(d, ELDER) == before and not d.studio.project.can_undo()
    d.window.dispatch_event("on_text", "x")  # typing now goes nowhere: not into a box out of view
    d.advance()
    assert field.text == before.get("name", field.text) and _entity(d, ELDER) == before
    _same_as_a_rebuild(d, "after a clicked box was scrolled")


def test_a_box_scrolled_out_of_view_and_back_keeps_its_text_and_commits_to_its_own_property(d: Any) -> None:
    before = dict(_entity(d, ELDER))
    field = d.studio._focusable["name"]
    shown = field.text
    _to_end(d, "right", down=True)
    assert field.get_ui_manager() is None, "the name box is out of view"
    _to_end(d, "right", down=False)
    assert d.studio._focusable["name"] is field and field.get_ui_manager() is not None and field.text == shown
    _type(d, "name", "Rowan")
    d.key(d.arcade.key.ENTER)
    after = _entity(d, ELDER)
    changed = {key for key in set(before) | set(after) if before.get(key) != after.get(key)}
    assert {"name"} <= changed <= {"name", "behaviour_config"} and after["name"] == "Rowan"


def test_a_refused_value_stays_in_its_box_through_scrolling_and_esc_puts_back_what_it_was(d: Any) -> None:
    d.studio.select(PLAYER)
    d.advance()
    _click(d, "Look")
    d.advance()
    before = dict(_entity(d, PLAYER))
    original = d.studio._focusable["look_scale"].text
    _type(d, "look_scale", "wide")
    _wheel(d, "right", -1)  # the wheel commits it: refused
    d.advance()
    assert not d.studio.message_ok and "look_scale" in d.studio._held and _entity(d, PLAYER) == before
    _to_end(d, "right", down=True)
    _to_end(d, "right", down=False)
    d.advance()
    field = d.studio._focusable["look_scale"]
    assert field.text == "wide" and field.get_ui_manager() is not None, "still typed in its box, back in view"
    assert _entity(d, PLAYER) == before and not d.studio.project.can_undo(), "never committed"
    _click(d, "Collision")  # going elsewhere waits for the box
    assert d.studio.tab == "look" and "Correct the box" in d.studio.message
    _press(d, d.studio._focusable["look_scale"])
    d.key(d.arcade.key.ESCAPE)
    d.advance()
    assert d.studio._focusable["look_scale"].text == original and "look_scale" not in d.studio._held
    _click(d, "Collision")
    assert d.studio.tab == "collision" and _entity(d, PLAYER) == before


def test_ctrl_s_after_scrolling_saves_what_was_typed(d: Any) -> None:
    _to_end(d, "right", down=True)
    _to_end(d, "right", down=False)
    _type(d, "name", "Elder of the Mill")
    k = d.arcade.key
    d.window.dispatch_event("on_key_press", k.S, k.MOD_CTRL)
    d.window.dispatch_event("on_key_release", k.S, k.MOD_CTRL)
    d.advance()
    saved = json.loads((Path(d.studio.project.root) / SCENE).read_text(encoding="utf-8"))
    assert next(e for e in saved["entities"] if e["id"] == ELDER)["name"] == "Elder of the Mill"
    assert not d.studio.project.is_dirty and d.studio.message_ok
    _click(d, "Undo")  # (and saved again as it was, for the tests after this one)
    d.studio.save()
    assert not d.studio.project.can_undo() or not d.studio.project.is_dirty


# ------------------------------------------------------------------ when the rows kept are not current
def test_another_object_selected_shows_its_own_rows_from_the_top_and_scrolls_them(
        d: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _to_end(d, "right", down=True)
    assert d.studio.panel_scroll > 0
    kept = d.studio._windows["right"][0]
    d.studio.select(PLAYER)
    d.advance()
    assert d.studio.panel_scroll == 0 and d.studio._windows["right"][0] is not kept, "the player's rows, not the elder's"
    counts = Counts(monkeypatch)
    _click(d, "Look")
    counts.take()
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (0, 1)
    assert not any(line in " ".join(_texts(d)) for line in LINES), "nothing of the elder's conversation is shown"
    _same_as_a_rebuild(d, "the player's Look, scrolled")


def test_an_edit_behind_the_panels_makes_the_next_notch_build_them_again(d: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import project_ops as ops

    counts = Counts(monkeypatch)
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (0, 1)
    d.studio.project.edit_scene(lambda s: ops.set_entity_fields(s, ELDER, name="Renamed behind the panels"))
    assert "Renamed behind the panels" not in _texts(d), "(nothing rebuilt the panels: they show the old name)"
    _wheel(d, "right", 1)
    assert counts.take()[:2] == (1, 0), "the project is not the one the rows were built from: built again"
    assert d.studio._focusable["name"].text == "Renamed behind the panels"
    counts.take()
    d.studio._refresh_top_bar()  # (what a live edit does: the top bar only)
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (1, 0), "the panels were left as built before: built again"
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (0, 1), "and then only scrolled"


def test_what_the_renderer_cannot_draw_here_changing_makes_the_next_notch_build_them_again(
        d: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The 3D panels say what this computer can't draw (bloom, depth of field): the renderer's word, not an edit."""
    counts = Counts(monkeypatch)
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (0, 1)
    monkeypatch.setattr(d.renderer, "bloom_unavailable", "bloom is off on this computer (simulated)")
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (1, 0)
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (0, 1)
    monkeypatch.setattr(d.renderer, "dof_status", lambda: ("unavailable", "depth of field is off on this computer"))
    _wheel(d, "right", 1)
    assert counts.take()[:2] == (1, 0)
    _wheel(d, "right", 1)
    assert counts.take()[:2] == (0, 1)


def test_the_window_losing_the_keyboard_makes_the_next_notch_build_the_panels_again(
        d: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Back from another program, the project's folder may hold other files than the panels list."""
    counts = Counts(monkeypatch)
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (0, 1)
    d.window.dispatch_event("on_deactivate")
    d.window.dispatch_event("on_activate")
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (1, 0)
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (0, 1)


def test_a_menu_open_over_the_panels_is_drawn_again_by_a_rebuild(d: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    d.studio.menu = (640.0, 360.0, [("Nothing", lambda: None)])
    d.studio._rebuild()
    counts = Counts(monkeypatch)
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (1, 0) and d.studio.menu is not None and "Nothing" in _texts(d)
    d.studio.menu = None
    d.studio._rebuild()
    counts.take()
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (0, 1)


def test_resizing_after_scrolling_fits_the_rows_to_the_window_and_scrolling_goes_on(
        d: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _to_end(d, "right", down=True)
    bottom_720 = d.studio.panel_scroll
    counts = Counts(monkeypatch)
    d.window.set_size(1100, 620)
    d.window.dispatch_event("on_resize", 1100, 620)
    _wheel(d, "right", 1)  # before the next frame has rebuilt for the new size
    assert counts.rebuilds >= 1 and counts.rewindows == 0, "the window is not the size the rows were laid out for"
    d.advance(2)
    assert d.studio._built_for == (1100, 620)
    counts.take()
    _to_end(d, "right", down=True)
    assert counts.rebuilds == 0 and d.studio.panel_scroll > bottom_720, "a shorter window shows fewer rows: more to scroll"
    _same_as_a_rebuild(d, "the bottom, in the smaller window")
    _size(d, 1280, 720)
    assert d.studio.panel_scroll == bottom_720 and _more(d, "right")[1] == 0, "back in the larger one: its own bottom"


def test_play_and_back_to_editing_rebuilds_the_panels_and_scrolling_goes_on(d: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _wheel(d, "right", -1)
    kept = d.studio._windows["right"][0]
    d.studio.play()
    d.advance(2)
    assert d.studio.mode == "play"
    _wheel(d, "right", -1)  # (the game's own, in play)
    d.studio.stop()
    d.advance(2)
    assert d.studio.mode == "edit" and d.studio._windows["right"][0] is not kept
    counts = Counts(monkeypatch)
    before = d.studio.panel_scroll
    _wheel(d, "right", -1)
    assert counts.take()[:2] == (0, 1) and d.studio.panel_scroll == before + 2
    _same_as_a_rebuild(d, "after a play-test")


# ------------------------------------------------------------------ lifetime
def test_scrolling_and_switching_many_times_leaves_no_widgets_or_listeners_behind(d: Any) -> None:
    import arcade.gui as gui
    from arcade.gui.property import Property

    def live() -> int:
        gc.collect()
        return sum(1 for o in gc.get_objects() if isinstance(o, gui.UIWidget))

    def listeners(widget: Any) -> int:
        total = 0
        for cls in type(widget).__mro__:
            for value in vars(cls).values():
                if isinstance(value, Property):
                    total += len(value.obs[widget]._listeners) if widget in value.obs else 0
        return total

    def round_trip() -> None:
        for title in ("Terrain", "Objects", "Environment", "Audio", "Rooms"):
            _click(d, title)
        for tab in ("Look", "Collision", "Dialogue"):
            _click(d, tab)
        for _ in range(3):
            _to_end(d, "right", down=True)
            _to_end(d, "right", down=False)

    round_trip()
    name = d.studio._focusable["name"]
    widgets, bound = live(), listeners(name)
    for _ in range(15):
        _to_end(d, "right", down=True)
        _to_end(d, "right", down=False)
    assert d.studio._focusable["name"] is name
    assert listeners(name) == bound, "a kept widget gains no listener each time its panel scrolls"
    assert live() == widgets, "scrolling 15 times down and up leaves no widget behind"
    counts = []
    for _ in range(4):
        round_trip()
        counts.append(live())
    assert counts[0] == counts[-1] <= widgets + 2, f"nor does switching tools and tabs between scrolls: {widgets}, {counts}"
