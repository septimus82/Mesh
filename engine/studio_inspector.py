"""Mesh Studio's object inspector: what you see on the right when an object is selected.

Tabs group an object's settings the way a person thinks about them: how it Looks, how it's
Animated, how it Collides, what it Says, When things about it change, and its Behaviours
(everything else). Each control edits through engine.project_ops, so every change is
validated, undoable and the same as what an AI or script would write.

Mixed into ``engine.studio.Studio``; it uses the Studio's widget helpers (_button, _field,
_label), its edit path (_edit) and its state (project, selected).
"""

from __future__ import annotations

import time
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import engine.optional_arcade as optional_arcade
from engine import behaviour_guide
from engine import project_ops as ops
from engine.studio_ui import C_MUTED, C_OK, C_TEXT, S_ACTIVE, S_BUTTON, S_DANGER, ask_path, gui

if TYPE_CHECKING:
    from engine.studio_ai import Proposal, StudioAIHost
    from engine.studio_project import Project

TABS = (("look", "Look"), ("animation", "Animation"), ("collision", "Collision"),
        ("dialogue", "Dialogue"), ("conditions", "Conditions"), ("behaviours", "Behaviours"))
_DOOR_TABS = ("look", "conditions", "behaviours")  # a door doesn't talk, animate or block


def _tabs_for(entity: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """The inspector tabs that mean something for this object: none for an arrival spot, three for a door."""
    tag = entity.get("tag")
    if tag == "spawn_point":
        return ()
    if tag == "door":
        return tuple(t for t in TABS if t[0] in _DOOR_TABS)
    return TABS
THUMB = 96  # picture and animation previews, in pixels
_DOOR_STYLE_HELP = {  # short lines: they must not need wrapping
    "door": ("A door picture the player goes through.", "Change the picture below; it blocks no one."),
    "passage": ("Not drawn in the game: an opening, a way off the map.", "It works in its outlined area."),
    "map_art": ("Not drawn: put its area over a door or stairs", "you painted on the map."),
}
IMAGE_FILES = [("Images", "*.png *.gif *.bmp *.jpg *.jpeg *.webp"), ("All files", "*.*")]


class Rows:
    """The right panel's rows, collected so the Studio can show the ones that fit (scrolling)."""

    def __init__(self) -> None:
        self.items: list[Any] = []
        self.anchors: dict[str, int] = {}

    def add(self, widget: Any) -> Any:
        self.items.append(widget)
        return widget

    def anchor(self, name: str) -> None:
        """Remember where a section starts, to scroll it into view."""
        self.anchors[name] = len(self.items)


def row_height(widget: Any) -> float:
    if isinstance(widget, gui.UIBoxLayout):
        kids = list(widget.children)
        if not kids:
            return 0.0
        if widget.vertical:
            return sum(row_height(k) for k in kids) + getattr(widget, "_space_between", 0) * (len(kids) - 1)
        return max(row_height(k) for k in kids)
    hint = getattr(widget, "size_hint_min", None) or (0, 0)
    return float(max(widget.height, hint[1] or 0))


def _names(values: Any) -> str:
    return ", ".join(str(v) for v in values or [])


def _guess_frame(size: tuple[int, int] | None) -> tuple[int, int]:
    """A likely frame size for a character sheet: 3 (or 4, 6, 8) frames across, square if it fits."""
    if size is None:
        return 32, 32
    width, height = size
    frame_w = next((width // n for n in (3, 4, 6, 8, 2) if width % n == 0), width)
    return frame_w, frame_w if height % frame_w == 0 else (height // 4 if height % 4 == 0 else height)


def _on_screen(widget: Any) -> bool:
    """Whether a preview slot is in the shown panel (rows scrolled out of view never get laid out)."""
    return getattr(widget, "parent", None) is not None


def _short(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class InspectorMixin:
    """The tabbed inspector, the picture browser, the conversation tester and the flag pickers."""

    if TYPE_CHECKING:  # what the mixin uses of its host, ``engine.studio.Studio``
        project: Project
        ai: StudioAIHost
        expanded: str | None
        mouse: tuple[float, float]
        _images: dict[str, Any]
        _focusable: dict[str, gui.UIInputText]
        menu: tuple[float, float, list[tuple[str, Callable[[], object]]]] | None
        _focus_after_build: str | None

        def _label(self, text: str, *, color: tuple[int, int, int] = C_TEXT, size: int = 11, width: int | None = None,
                   bold: bool = False) -> gui.UILabel: ...
        def _button(self, text: str, action: Callable[[], object], *, width: int = 100, style: dict[str, Any] = S_BUTTON,
                    disabled: bool = False) -> gui.UIFlatButton: ...
        def _field(self, text: str, commit: Callable[[str], object], *, width: int, key: str | None = None) -> gui.UIInputText: ...
        def _edit(self, change: Callable[[dict[str, Any]], dict[str, Any]], ok: str = "") -> bool: ...
        def _rebuild(self) -> None: ...
        def _say(self, text: str, ok: bool = True) -> None: ...
        def _flush_fields(self) -> None: ...
        def _cancel_panel(self) -> None: ...
        def _toggle_expand(self, name: str) -> None: ...
        def _open_picker(self) -> None: ...
        def _image(self, path: str) -> Any: ...
        def _entity(self, entity_id: str | None) -> dict[str, Any] | None: ...
        def _sprites_by_id(self) -> dict[str, Any]: ...
        def _behaviour_fields(self, box: gui.UIBoxLayout, entity: dict[str, Any], behaviour: str, width: int) -> None: ...
        def remove_behaviour(self, name: str) -> None: ...
        def delete_selected(self) -> None: ...
        def accept_ai(self, proposal: Proposal) -> None: ...
        def reject_ai(self, proposal: Proposal) -> None: ...
        def share_player(self, key: str) -> None: ...
        def keep_separate_players(self) -> None: ...

    # ---------------------------------------------------------------- shared state
    def _init_inspector(self) -> None:
        self.tab = "look"
        self.dlg_line: str | None = None  # the conversation line being edited
        self.dlg_choice: int | None = None  # ... and its choice being edited
        self.clip_sel: str | None = None  # the animation clip being edited
        self.preview: dict[str, Any] | None = None  # the conversation tester's state
        self.pick: dict[str, Any] | None = None  # the picture browser: {"title", "choose": callback}
        self.anim_form: dict[str, str] = {}
        self.panel_scroll = 0
        self._scroll_to: str | None = None
        self._panel_more = (0, 0)
        self._thumbs: list[tuple[Any, str]] = []  # (UISpace, image path) drawn after the UI
        self._anim_space: Any = None
        self._textures: dict[Any, Any] = {}

    # ---------------------------------------------------------------- small helpers
    def _toggle(self, label: str, value: bool, flip: Callable[[bool], object], width: int) -> Any:
        return self._button(f"{label}: {'On' if value else 'Off'}", lambda: flip(not value), width=width,
                            style=S_ACTIVE if value else S_BUTTON)

    def _labeled(self, rows: Rows, label: str, widget: Any, width: int, label_width: int = 118) -> None:
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        row.add(self._label(label, color=C_MUTED, size=10, width=label_width))
        row.add(widget)
        rows.add(row)

    def _flag_field(self, rows: Rows, label: str, values: Any, commit: Callable[[str], object], width: int, key: str) -> None:
        """A comma-separated flag list with a "Flags..." picker of the flags the project already uses."""
        field = self._field(_names(values), commit, width=width - 118 - 52 - 8, key=key)
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        row.add(self._label(label, color=C_MUTED, size=10, width=118))
        row.add(field)
        row.add(self._button("Pick", partial(self._pick_flag, field, commit), width=52))
        rows.add(row)

    def _pick_flag(self, field: Any, commit: Callable[[str], object]) -> None:
        known = list(self._flag_uses())
        current = [n.strip() for n in field.text.split(",") if n.strip()]
        items: list[tuple[str, Callable[[], object]]] = []
        for name in known:
            if name not in current:
                items.append((name, partial(commit, ", ".join(current + [name]))))
        items.append(("New flag... (type it in the box)", lambda: self._activate(field)))
        x, y = self.mouse
        self.menu = (x - 220, y, items)
        self._rebuild()

    def _activate(self, field: Any) -> None:
        for key, widget in self._focusable.items():
            if widget is field:
                self._focus_after_build = key
        self._rebuild()

    def _flag_uses(self) -> dict[str, list[str]]:
        rooms = {key: (label, self.project.scene(key)) for key, label, _path in self.project.rooms()}
        return ops.flag_uses(rooms)

    def _say_edit(self, change: Callable[[dict[str, Any]], dict[str, Any]], ok: str = "") -> bool:
        return self._edit(change, ok)

    def _image_size(self, rel: str) -> tuple[int, int] | None:
        image = self._image(str(self.project.root / rel)) if rel else None
        return image.size if image is not None else None

    # ---------------------------------------------------------------- the inspector
    def _inspector(self, rows: Rows, entity: dict[str, Any], width: int) -> None:
        target = entity["id"]
        rows.add(self._label("Name", color=C_MUTED))
        rows.add(self._field(str(entity.get("name") or ""), lambda v: self._edit(lambda s: ops.rename_entity(s, target, v), "Renamed."),
                             width=width, key="name"))
        rows.add(self._label(f"Position  {entity.get('x', 0):.0f}, {entity.get('y', 0):.0f}", color=C_MUTED, size=10))
        if self.project.is_shared_player(target):
            rows.add(self._label("The game's player: picture, size, collision and behaviours are the same in every "
                                 "room. Only where it starts belongs to this room.", color=C_OK, size=9, width=width))
        elif entity.get("tag") == "player" and self.project.player is None:
            rows.add(self._label("This room has its own player: changes here don't reach other rooms.",
                                 color=(240, 200, 120), size=9, width=width))
            rows.add(self._button("Use one player in every room...", self._open_players, width=width))
        tabs = _tabs_for(entity)
        if entity.get("tag") == "spawn_point":
            rows.add(self._label("An arrival spot: where the player appears on coming into this room through a door. "
                                 "Drag it to move it. Keep it clear of the door here, or the player walks straight back "
                                 "out.", color=C_MUTED, size=10, width=width))
            rows.add(gui.UISpace(height=6))
            rows.add(self._button("Delete object", self.delete_selected, width=120, style=S_DANGER))
            return
        if entity.get("tag") == "door":
            rows.add(self._label(self._door_note(entity), color=C_MUTED, size=10, width=width))
        if self.tab not in {key for key, _title in tabs}:
            self.tab = tabs[0][0]
        third = (width - 8) // 3
        for line in (tabs[:3], tabs[3:]):
            row = gui.UIBoxLayout(vertical=False, space_between=4)
            for key, title in line:
                row.add(self._button(title, partial(self._open_tab, key), width=third,
                                     style=S_ACTIVE if self.tab == key else S_BUTTON))
            rows.add(row)
        rows.add(gui.UISpace(height=4))
        {"look": self._look_tab, "animation": self._animation_tab, "collision": self._collision_tab,
         "dialogue": self._dialogue_tab, "conditions": self._conditions_tab,
         "behaviours": self._behaviours_tab}[self.tab](rows, entity, width)
        rows.add(gui.UISpace(height=6))
        rows.add(self._button("Delete object", self.delete_selected, width=120, style=S_DANGER))

    def _door_note(self, entity: dict[str, Any]) -> str:
        config = (entity.get("behaviour_config") or {}).get("SceneTransition") or {}
        rooms = {key: label for key, label, _path in self.project.rooms()}
        where = rooms.get(str(config.get("target_scene") or ""), "another room")
        door = ops.door_settings(entity)
        how = " or ".join(w for w, on in (("walking into it", door["touch"]), ("pressing E beside it", door["interact"])) if on)
        return (f"A door to {where}: the player goes through by {how} (its outlined area on the map). "
                "The arrival spot shows where they come back in.")

    def _open_tab(self, key: str) -> None:
        self.tab, self.panel_scroll = key, 0
        self._rebuild()

    # ---------------------------------------------------------------- Look
    def _look_tab(self, rows: Rows, entity: dict[str, Any], width: int) -> None:
        target, sprite = entity["id"], str(entity.get("sprite") or "")
        if entity.get("tag") == "door" and "SceneTransition" in ops.entity_behaviours(entity):
            self._door_look(rows, entity, width)
            if ops.door_style(entity) != "door":
                self._shadow_settings(rows, entity, width)
                return
        rows.add(self._label("Picture", bold=True, size=12))
        if sprite:
            space = gui.UISpace(width=THUMB, height=THUMB)
            self._thumbs.append((space, str(self.project.root / sprite)))
            rows.add(space)
            size = self._image_size(sprite)
            rows.add(self._label(f"{sprite}" + (f"  ({size[0]}x{size[1]} px)" if size else "  (missing!)"),
                                 color=C_MUTED, size=9, width=width))
            frame = _guess_frame(size)
            animated = ops.animation_clips(entity) or entity.get("animations")
            # Not for a single small picture (a 32x32 sprite would "divide" into 8x8 frames).
            single = size is not None and (size[0] == size[1] <= 64 or min(frame) < 16)
            if size and not animated and not single and (size[0] > frame[0] or size[1] > frame[1]):
                rows.add(self._label("This looks like a sheet of frames: the whole sheet shows until you set up "
                                     "its animation in the Animation tab.", color=(240, 200, 120), size=9, width=width))
        else:
            rows.add(self._label("No picture: it's invisible in the game (fine for zones and markers).",
                                 color=C_MUTED, size=10, width=width))
        half = (width - 6) // 2
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._button("Choose picture...", lambda: self._open_picker_images(
            "Choose a picture", lambda rel: self._choose_picture(entity, rel, "Picture changed.")), width=half))
        row.add(self._button("Import PNG...", lambda: self._import_picture(
            lambda rel: self._choose_picture(entity, rel, "Imported and assigned.")), width=half))
        rows.add(row)
        if sprite:
            animated = bool(ops.animation_clips(entity) or entity.get("animations"))
            rows.add(self._button("No picture", lambda: self._edit(lambda s: ops.set_picture(s, target, None), "Picture removed." + (
                " Its animation is kept for when you choose a picture again." if animated else "")), width=half))
        self._animation_warning(rows, entity, width)
        rows.add(gui.UISpace(height=4))
        self._labeled(rows, "Size (1 = as drawn)", self._field(f"{float(entity.get('scale', 1.0)):g}",
                      lambda v: self._edit(lambda s: ops.set_look(s, target, scale=v), "Size changed."), width=width - 122,
                      key="look_scale"), width)
        rows.add(self._toggle("Mirrored (faces the other way)", bool(entity.get("flip_x")),
                              lambda on: self._edit(lambda s: ops.set_look(s, target, flip_x=on), "Mirrored." if on else "Not mirrored."),
                              width))
        rows.add(self._label("To change the picture with the story (a dug grave), use Conditions.", color=C_MUTED, size=9, width=width))
        self._shadow_settings(rows, entity, width)

    def _door_look(self, rows: Rows, entity: dict[str, Any], width: int) -> None:
        """How a door shows (a picture, an invisible passage, or an area over painted map art) and how the player
        goes through it. One door behaviour underneath; the style only changes what is drawn."""
        target, door = entity["id"], ops.door_settings(entity)
        rows.add(self._label("How it shows", bold=True, size=12))
        third = (width - 8) // 3
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        for style, text in (("door", "Door"), ("passage", "Passage"), ("map_art", "Map artwork")):
            row.add(self._button(text, partial(self._set_door, target, f"Shows as: {text.lower()}.", style=style),
                                 width=third, style=S_ACTIVE if door["style"] == style else S_BUTTON))
        rows.add(row)
        for line in _DOOR_STYLE_HELP[door["style"]]:
            rows.add(self._label(line, color=C_MUTED, size=9))
        if door["style"] != "door":
            field_w = width - 122
            for label, key in (("Area width (px)", "width"), ("Area height (px)", "height")):
                self._labeled(rows, label, self._field(f"{door[key]:g}", partial(self._set_door_area, target, key),
                                                       width=field_w, key=f"door_{key}"), width)
        half = (width - 6) // 2
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._toggle("Walk in", door["touch"], lambda on: self._edit(
            lambda s: ops.set_door(s, target, touch=on), "Walking into it goes through." if on else "Walking in does nothing."), half))
        row.add(self._toggle("Press E", door["interact"], lambda on: self._edit(
            lambda s: ops.set_door(s, target, interact=on), "Pressing E beside it goes through." if on else "E does nothing."), half))
        rows.add(row)
        rows.add(gui.UISpace(height=6))

    def _set_door(self, target: str, message: str, **change: Any) -> None:
        self._edit(lambda s: ops.set_door(s, target, **change), message)

    def _set_door_area(self, target: str, key: str, text: str) -> None:
        self._set_door(target, "Area changed.", **{key: text})

    def _shadow_settings(self, rows: Rows, entity: dict[str, Any], width: int) -> None:
        """The object's two shadows: the small one under its feet, and the one lamps cast of it."""
        target = entity["id"]
        rows.add(gui.UISpace(height=6))
        rows.add(self._label("Shadows", bold=True, size=12))
        half = (width - 6) // 2
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._toggle("Under feet", ops.has_ground_shadow(entity),
                             lambda on: self._edit(lambda s: ops.set_shadows(s, target, ground=on),
                                                   "Shadow under its feet." if on else "No shadow under its feet."), half))
        casting = ops.casts_shadow(entity)
        row.add(self._toggle("From lamps", casting,
                             lambda on: self._edit(lambda s: ops.set_shadows(s, target, cast=on),
                                                   "Lamps cast its shadow." if on else "Lamps cast no shadow of it."), half))
        rows.add(row)
        if not casting:
            return
        raw = entity.get("cast_shadow")
        settings = raw if isinstance(raw, dict) else {}
        more = self.expanded == "shadow_more"
        rows.add(self._button(("v " if more else "> ") + "Shadow from lamps: fine-tune", lambda: self._toggle_expand("shadow_more"),
                              width=width))
        if not more:
            return
        field_w = width - 122
        height = settings.get("height")
        self._labeled(rows, "Height (px, empty: from picture)", self._field("" if height is None else f"{float(height):g}",
                      lambda v: self._edit(lambda s: ops.set_shadows(s, target, height=v.strip() or None), "Shadow height changed."),
                      width=field_w, key="shadow_height"), width)
        self._labeled(rows, "Darkness (0-1)", self._field(f"{float(settings.get('strength', 0.85)):g}",
                      lambda v: self._edit(lambda s: ops.set_shadows(s, target, strength=v), "Shadow darkness changed."),
                      width=field_w, key="shadow_strength"), width)
        self._labeled(rows, "Length (x)", self._field(f"{float(settings.get('length', 1.0)):g}",
                      lambda v: self._edit(lambda s: ops.set_shadows(s, target, length=v), "Shadow length changed."),
                      width=field_w, key="shadow_length"), width)
        rows.add(self._label("Lamps throw its shadow away from them, longer the farther it stands. Height is how tall it "
                             "looks; darkness, how much of a lamp's light it blocks.", color=C_MUTED, size=9, width=width))

    def _choose_picture(self, entity: dict[str, Any], rel: str, message: str) -> None:
        """Change the picture; an animation follows a same-layout sheet, otherwise it's kept and flagged."""
        target, old = entity["id"], str(entity.get("sprite") or "")
        animated = bool(ops.animation_clips(entity) or entity.get("animations"))
        same_layout = bool(old) and self._image_size(old) is not None and self._image_size(old) == self._image_size(rel)
        if animated and old and rel != old:
            message += (" Its animation now uses it (same frame layout)." if same_layout
                        else " Its animation was made for the old picture: check it below.")
        self._edit(lambda s: ops.set_picture(s, target, rel, follow=animated and same_layout), message)

    def _animation_warning(self, rows: Rows, entity: dict[str, Any], width: int) -> None:
        """Say when the animation doesn't fit the picture, and offer the two ways out."""
        sprite = str(entity.get("sprite") or "")
        problem = ops.animation_fit(entity, self._image_size(sprite)) if sprite else None
        if not problem:
            return
        target = entity["id"]
        rows.add(self._label(problem + " So the game would show the wrong part of the picture.", color=(240, 200, 120),
                             size=9, width=width))
        rows.add(self._label("A single picture: show it as it is. A sheet of frames: set up its frames in the "
                             "Animation tab.", color=C_MUTED, size=9, width=width))
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        half = (width - 6) // 2
        if any(c.get("sheet") != sprite for c in ops.animation_clips(entity).values() if isinstance(c, dict)):
            row.add(self._button("Use this picture", lambda: self._edit(
                lambda s: ops.animation_use_picture(s, target), "The animation now cuts its frames from this picture."), width=half))
        row.add(self._button("Show it as it is", lambda: self._edit(
            lambda s: ops.reset_animation(s, target), "The picture shows as it is (its animation is off). Undo brings it back."),
            width=half))
        rows.add(row)

    # ---------------------------------------------------------------- picture browser
    def _open_picker_images(self, title: str, choose: Callable[[str], object]) -> None:
        self.pick = {"title": title, "choose": choose}
        self.panel, self.panel_scroll = "pick_image", 0
        self._rebuild()

    def _import_picture(self, then: Callable[[str], object]) -> None:
        path = ask_path(folder=False, title="Import a picture (PNG)", filetypes=IMAGE_FILES)
        if not path:
            return
        try:
            rel = self.project.import_sprite(path)
        except ops.OpError as err:
            self._say(str(err), ok=False)
            return
        self._images.pop(str(self.project.root / rel), None)
        self.panel = "inspect"
        then(rel)

    def _picture_picker(self, rows: Rows, width: int) -> None:
        pick = self.pick or {}
        rows.add(self._label(pick.get("title", "Choose a picture"), bold=True, size=12))
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._button("Import PNG...", lambda: self._import_picture(self._picked), width=130))
        row.add(self._button("Cancel", self._cancel_panel, width=80))
        rows.add(row)
        images = self.project.images()
        if not images:
            rows.add(self._label("No pictures in this project yet: import one.", color=C_MUTED, width=width))
        for rel in images:
            row = gui.UIBoxLayout(vertical=False, space_between=6)
            space = gui.UISpace(width=32, height=32)
            self._thumbs.append((space, str(self.project.root / rel)))
            row.add(space)
            row.add(self._button(_short(rel.removeprefix("assets/"), 34), partial(self._picked, rel), width=width - 38))
            rows.add(row)

    def _picked(self, rel: str) -> None:
        choose = (self.pick or {}).get("choose")
        self.pick, self.panel = None, "inspect"
        if choose is not None:
            choose(rel)
        else:
            self._rebuild()

    # ---------------------------------------------------------------- Animation
    def _animation_tab(self, rows: Rows, entity: dict[str, Any], width: int) -> None:
        target = entity["id"]
        clips = ops.animation_clips(entity)
        if entity.get("animations"):
            rows.add(self._label("This object uses the simple built-in animation. Setting one up here replaces it.",
                                 color=C_MUTED, size=10, width=width))
        rows.add(self._label("Animation", bold=True, size=12))
        self._animation_warning(rows, entity, width)
        if clips:
            shown = self.clip_sel if self.clip_sel in clips else next(iter(clips))
            self._anim_space = gui.UISpace(width=THUMB, height=THUMB)
            self._anim_space.mesh_clip = clips[shown]
            rows.add(self._anim_space)
            rows.add(self._label(f"Playing: {shown}", color=C_MUTED, size=9))
            config = (entity.get("behaviour_config") or {}).get("Animator") or {}
            if config.get("directional_mode") == "4-way":
                facing = config.get("facing_default") or "down"
                nxt = ops.DIRECTIONS[(ops.DIRECTIONS.index(facing) + 1) % 4] if facing in ops.DIRECTIONS else "down"
                rows.add(self._button(f"Faces at the start: {facing}", lambda: self._edit(
                    lambda s: ops.set_behaviour_param(s, target, "Animator", "facing_default", nxt), f"Faces {nxt} at the start."),
                    width=width))
            for name, clip in clips.items():
                columns = self._sheet_columns(clip)
                r, first = ops.clip_position(clip, columns)
                text = f"{name}: row {r}, {clip.get('frames', 1)} frame(s){'  (mirrored)' if clip.get('flip_x') else ''}"
                rows.add(self._button(text, partial(self._select_clip, name), width=width,
                                      style=S_ACTIVE if name == self.clip_sel else S_BUTTON))
                if name == self.clip_sel:
                    self._clip_editor(rows, entity, name, clip, width)
        else:
            rows.add(self._label("Not animated yet.", color=C_MUTED))
        rows.anchor("walk_setup")
        rows.add(gui.UISpace(height=6))
        self._walk_setup(rows, entity, width)
        rows.add(gui.UISpace(height=4))
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._button("+ Clip", lambda: self._add_clip(entity), width=90))
        if clips:
            row.add(self._button("Remove animation", lambda: self._edit(lambda s: ops.set_animation(s, target, {}), "Animation removed."),
                                 width=150, style=S_DANGER))
        rows.add(row)

    def _sheet_columns(self, clip: dict[str, Any]) -> int:
        size = self._image_size(str(clip.get("sheet") or ""))
        fw = int(clip.get("frame_width") or clip.get("width") or 32)
        return max(1, size[0] // fw) if size else 1

    def _select_clip(self, name: str) -> None:
        self.clip_sel = None if self.clip_sel == name else name
        self._rebuild()

    def _clip_editor(self, rows: Rows, entity: dict[str, Any], name: str, clip: dict[str, Any], width: int) -> None:
        target, columns = entity["id"], self._sheet_columns(clip)
        row_n, first = ops.clip_position(clip, columns)
        size = self._image_size(str(clip.get("sheet") or ""))
        fw, fh = int(clip.get("frame_width") or 32), int(clip.get("frame_height") or 32)

        def update(**changes: Any) -> None:
            values = {"row": row_n, "first": first, "count": clip.get("frames", 1), "fps": clip.get("fps", 8),
                      "flip": bool(clip.get("flip_x")), "fw": fw, "fh": fh}
            values.update(changes)
            try:  # a new frame size changes how many frames fit across and down
                new_w, new_h = int(float(values["fw"])), int(float(values["fh"]))
                across = max(1, size[0] // new_w) if size else columns
                down = max(1, size[1] // new_h) if size else None
            except (ValueError, ZeroDivisionError):
                self._say("The frame size must be whole numbers of pixels.", ok=False)
                self._rebuild()
                return
            if "fw" in changes or "fh" in changes:  # keep the clip's frame count inside the new row
                values["first"], values["count"] = 0, min(int(values["count"]), across)
            self._edit(lambda s: ops.set_clip(s, target, name, ops.clip_spec(
                clip["sheet"], new_w, new_h, across, values["row"], values["first"], values["count"], values["fps"],
                flip_x=values["flip"], sheet_rows=down)), f"{name} changed.")

        quarter = (width - 122 - 12) // 2
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        row.add(self._label("Frame size w / h", color=C_MUTED, size=10, width=118))
        row.add(self._field(str(fw), lambda v: update(fw=v), width=quarter, key="clip_fw"))
        row.add(self._field(str(fh), lambda v: update(fh=v), width=quarter, key="clip_fh"))
        rows.add(row)
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        row.add(self._label("Row / from frame", color=C_MUTED, size=10, width=118))
        row.add(self._field(str(row_n), lambda v: update(row=v), width=quarter, key="clip_row"))
        row.add(self._field(str(first), lambda v: update(first=v), width=quarter, key="clip_first"))
        rows.add(row)
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        row.add(self._label("Frames / per second", color=C_MUTED, size=10, width=118))
        row.add(self._field(str(clip.get("frames", 1)), lambda v: update(count=v), width=quarter, key="clip_count"))
        row.add(self._field(f"{float(clip.get('fps', 8)):g}", lambda v: update(fps=v), width=quarter, key="clip_fps"))
        rows.add(row)
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._toggle("Mirror", bool(clip.get("flip_x")), lambda on: update(flip=on), (width - 6) // 2))
        row.add(self._button("Delete clip", lambda: self._edit(lambda s: ops.set_clip(s, target, name, None), f"Deleted {name}."),
                             width=(width - 6) // 2, style=S_DANGER))
        rows.add(row)

    def _walk_setup(self, rows: Rows, entity: dict[str, Any], width: int) -> None:
        """One form that sets up idle and walk clips for four directions from a character sheet."""
        form = self.anim_form
        if form.get("_for") != entity["id"]:
            sheet = str(entity.get("sprite") or "")
            frame = _guess_frame(self._image_size(sheet))
            form.clear()
            form.update({"_for": entity["id"], "sheet": sheet, "fw": str(frame[0]), "fh": str(frame[1]), "down": "0",
                         "left": "1", "right": "2", "up": "3", "walk_first": "0", "walk_count": "3", "idle_first": "1",
                         "idle_count": "1", "fps": "8"})
        rows.add(self._label("Walking character (4 directions)", bold=True, size=11))
        rows.add(self._label("Rows count from 0 at the top. Leave Left empty to mirror Right.", color=C_MUTED, size=9, width=width))
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        row.add(self._label(_short(form["sheet"].removeprefix("assets/") or "no image", 26), size=10, width=width - 84))
        def use_sheet(rel: str) -> None:
            form.update(sheet=rel)
            self._rebuild()

        row.add(self._button("Image...", lambda: self._open_picker_images("Image with the frames", use_sheet), width=80))
        rows.add(row)

        def set_(key: str) -> Callable[[str], object]:
            return lambda v: form.__setitem__(key, v.strip())

        half = (width - 122 - 12) // 2
        for label, a, b in (("Frame size w / h", "fw", "fh"), ("Row: down / up", "down", "up"),
                            ("Row: left / right", "left", "right"), ("Walk: from / count", "walk_first", "walk_count"),
                            ("Stand: from / count", "idle_first", "idle_count")):
            row = gui.UIBoxLayout(vertical=False, space_between=4)
            row.add(self._label(label, color=C_MUTED, size=10, width=118))
            row.add(self._field(form[a], set_(a), width=half, key=f"anim_{a}"))
            row.add(self._field(form[b], set_(b), width=half, key=f"anim_{b}"))
            rows.add(row)
        self._labeled(rows, "Frames per second", self._field(form["fps"], set_("fps"), width=width - 122, key="anim_fps"), width)
        rows.add(self._button("Set up walking", lambda: self._apply_walk_setup(entity), width=width, style=S_ACTIVE))

    def _apply_walk_setup(self, entity: dict[str, Any]) -> None:
        form, target = self.anim_form, entity["id"]
        size = self._image_size(form.get("sheet", ""))
        if size is None:
            self._say("Choose the image with the character's frames first.", ok=False)
            return
        try:
            columns = max(1, size[0] // int(float(form["fw"])))
            sheet_rows = max(1, size[1] // int(float(form["fh"])))
        except (ValueError, ZeroDivisionError):
            self._say("The frame size must be whole numbers of pixels.", ok=False)
            return
        try:
            clips = ops.character_clips(form["sheet"], form["fw"], form["fh"], columns,
                                        {d: form.get(d) for d in ops.DIRECTIONS}, walk_first=form["walk_first"],
                                        walk_count=form["walk_count"], idle_first=form["idle_first"],
                                        idle_count=form["idle_count"], walk_fps=form["fps"],
                                        idle_fps=max(1.0, float(form["fps"] or 8) / 3), sheet_rows=sheet_rows)
        except (ops.OpError, ValueError) as err:
            self._say(str(err) if isinstance(err, ops.OpError) else "Those numbers don't look right.", ok=False)
            return
        if self._edit(lambda s: ops.set_animation(s, target, clips), "Walking set up: 4 directions, standing and walking."):
            self.clip_sel = "walk_down"
            self._rebuild()

    def _add_clip(self, entity: dict[str, Any]) -> None:
        clips = ops.animation_clips(entity)
        sheet = str(entity.get("sprite") or (next(iter(clips.values()))["sheet"] if clips else ""))
        if not sheet:
            self._say("Give the object a picture first (Look tab): clips cut frames from it.", ok=False)
            return
        n, name = 1, "idle" if "idle" not in clips else "clip"
        while name in clips:
            n += 1
            name = f"clip_{n}"
        size = self._image_size(sheet)
        fw, fh = _guess_frame(size)  # never the whole sheet as one frame
        across = max(1, size[0] // fw) if size else 1
        target = entity["id"]
        spec = ops.clip_spec(sheet, fw, fh, across, 0, 0, across, 6)  # the first row, as a start
        if self._edit(lambda s: ops.set_clip(s, target, name, spec),
                      f"Added {name}: {across} frame(s) of {fw}x{fh}. Check the frame size and row below."):
            self.clip_sel = name
            self._rebuild()

    def _clip_frames(self, clip: dict[str, Any]) -> list[Any]:
        """The clip's frames as textures, cut the way the Animator cuts them (top-left, row by row)."""
        sheet = str(clip.get("sheet") or "")
        fw, fh = int(clip.get("frame_width") or 32), int(clip.get("frame_height") or 32)
        start, count, flip = int(clip.get("start") or 0), int(clip.get("frames") or 1), bool(clip.get("flip_x"))
        key = (sheet, fw, fh, start, count, flip)
        if key not in self._textures:
            image = self._image(str(self.project.root / sheet)) if sheet else None
            frames = []
            if image is not None:
                from PIL import ImageOps  # noqa: PLC0415

                columns = max(1, image.width // fw)
                for index in range(start, start + count):
                    x, y = (index % columns) * fw, (index // columns) * fh
                    if y + fh > image.height:
                        break
                    frame = image.crop((x, y, x + fw, y + fh))
                    frames.append(optional_arcade.arcade.Texture(ImageOps.mirror(frame) if flip else frame,
                                                                 hash=f"mesh-studio-clip-{key}-{index}"))
            self._textures[key] = frames
        cached: list[Any] = self._textures[key]
        return cached

    # ---------------------------------------------------------------- Collision
    def _collision_tab(self, rows: Rows, entity: dict[str, Any], width: int) -> None:
        target = entity["id"]
        rows.add(self._label("Collision", bold=True, size=12))
        rows.add(self._toggle("Blocks movement", bool(entity.get("solid")),
                              lambda on: self._edit(lambda s: ops.set_solid(s, target, on), "Blocks movement." if on else "Walk-through."),
                              width))
        collider = ops.collider_of(entity, self._picture_size(entity))
        third = (width - 8) // 3
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        for kind, title in (("picture", "Whole picture"), ("box", "Footprint"), ("circle", "Circle")):
            row.add(self._button(title, partial(self._set_shape, entity, kind), width=third,
                                 style=S_ACTIVE if collider["kind"] == kind else S_BUTTON))
        rows.add(row)

        def commit(**changes: Any) -> None:
            values = {**collider, **changes}
            self._edit(lambda s: ops.set_collider(s, target, values["kind"], w=values.get("w", 32), h=values.get("h", 16),
                                                  r=values.get("r", 12), offset_x=values.get("offset_x", 0),
                                                  offset_y=values.get("offset_y", 0)), "Collider changed.")

        half = (width - 122 - 12) // 2
        if collider["kind"] == "box":
            row = gui.UIBoxLayout(vertical=False, space_between=4)
            row.add(self._label("Width / height", color=C_MUTED, size=10, width=118))
            row.add(self._field(f"{collider['w']:g}", lambda v: commit(w=v), width=half, key="col_w"))
            row.add(self._field(f"{collider['h']:g}", lambda v: commit(h=v), width=half, key="col_h"))
            rows.add(row)
        elif collider["kind"] == "circle":
            self._labeled(rows, "Radius", self._field(f"{collider['r']:g}", lambda v: commit(r=v), width=width - 122, key="col_r"), width)
        if collider["kind"] != "picture":
            row = gui.UIBoxLayout(vertical=False, space_between=4)
            row.add(self._label("Offset x / y", color=C_MUTED, size=10, width=118))
            row.add(self._field(f"{collider['offset_x']:g}", lambda v: commit(offset_x=v), width=half, key="col_ox"))
            row.add(self._field(f"{collider['offset_y']:g}", lambda v: commit(offset_y=v), width=half, key="col_oy"))
            rows.add(row)
            rows.add(self._label(("Sized to the picture: it follows a new picture or size. " if collider.get("auto") else "")
                                 + "Drag the blue handles on the map to set it yourself: the corner sizes it, the centre "
                                   "moves it.", color=C_MUTED, size=9, width=width))
        else:
            rows.add(self._label("The whole picture blocks. A footprint blocks only where it stands.", color=C_MUTED, size=9, width=width))

        rows.add(gui.UISpace(height=8))
        rows.anchor("zone")
        rows.add(self._label("Trigger zone", bold=True, size=12))
        zone = ops.trigger_zone(entity)
        if zone is None:
            rows.add(self._label("Something happens when the player walks into it.", color=C_MUTED, size=10, width=width))
            rows.add(self._button("Make it a trigger zone", lambda: self._edit(
                lambda s: ops.set_trigger_zone(s, target, width=96, height=96), "It's a trigger zone now: drag its orange corner to size it."),
                width=width))
            return

        def zone_commit(**changes: Any) -> None:
            values = {**zone, **changes}
            self._edit(lambda s: ops.set_trigger_zone(s, target, width=values["width"], height=values["height"], once=values["once"],
                                                      start_conversation=values["start_conversation"],
                                                      set_flags=values["set_flags"]), "Zone changed.")

        row = gui.UIBoxLayout(vertical=False, space_between=4)
        row.add(self._label("Width / height", color=C_MUTED, size=10, width=118))
        row.add(self._field(f"{zone['width']:g}", lambda v: zone_commit(width=v), width=half, key="zone_w"))
        row.add(self._field(f"{zone['height']:g}", lambda v: zone_commit(height=v), width=half, key="zone_h"))
        rows.add(row)
        rows.add(self._label("When the player walks in:", color=C_TEXT, size=10))
        rows.add(self._toggle("Start its conversation", zone["start_conversation"], lambda on: zone_commit(start_conversation=on), width))
        self._flag_field(rows, "Set flags", zone["set_flags"], lambda v: zone_commit(set_flags=v), width, "zone_flags")
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._toggle("Only once", zone["once"], lambda on: zone_commit(once=on), (width - 6) // 2))
        row.add(self._button("Remove zone", lambda: self._edit(lambda s: ops.remove_trigger_zone(s, target), "Zone removed."),
                             width=(width - 6) // 2, style=S_DANGER))
        rows.add(row)

    def _picture_size(self, entity: dict[str, Any]) -> tuple[float, float]:
        sprite = self._sprites_by_id().get(str(entity.get("id") or ""))
        if sprite is None or not entity.get("sprite"):
            return 32.0, 32.0
        return float(getattr(sprite, "width", 32) or 32), float(getattr(sprite, "height", 32) or 32)

    def _set_shape(self, entity: dict[str, Any], kind: str) -> None:
        target = entity["id"]
        w, h = self._picture_size(entity)
        if kind == "box":  # the feet, following the picture: a new picture or size keeps them right
            self._edit(lambda s: ops.set_collider(s, target, "box", auto=True), "Footprint: the feet, sized to the picture.")
            return
        sizes: dict[str, Any] = {"circle": {"r": round(max(6.0, min(w, h) * 0.2)), "offset_y": round(-h * 0.3)}}.get(kind, {})
        self._edit(lambda s: ops.set_collider(s, target, kind, **sizes), "Collider changed.")

    # ---------------------------------------------------------------- Dialogue
    def _dialogue_tab(self, rows: Rows, entity: dict[str, Any], width: int) -> None:
        target = entity["id"]
        talk = ops.conversation(entity)
        nodes = talk["nodes"]
        order = list(nodes)
        number = {node_id: i + 1 for i, node_id in enumerate(order)}
        rows.add(self._label("Conversation", bold=True, size=12))
        self._labeled(rows, "First line says", self._field(ops.dialogue_text(entity), lambda v: self._edit(
            lambda s: ops.set_dialogue_text(s, target, v), "Dialogue updated."), width=width - 122, key="says"), width)
        if not nodes:
            rows.add(self._label("Nothing to say yet." + (" (Old lines will be kept.)" if talk["legacy_lines"] else ""),
                                 color=C_MUTED, size=10, width=width))
            rows.add(self._button("+ First line", lambda: self._add_line(target, None), width=width, style=S_ACTIVE))
            return
        self._labeled(rows, "Speaker", self._field(talk["speaker"], lambda v: self._edit(
            lambda s: ops.set_conversation(s, target, speaker=v), "Speaker changed."), width=width - 122, key="dlg_speaker"), width)
        half = (width - 6) // 2
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._toggle("Only once", talk["once"], lambda on: self._edit(lambda s: ops.set_conversation(s, target, once=on)), half))
        row.add(self._toggle("Starts by itself", talk["auto_start"],
                             lambda on: self._edit(lambda s: ops.set_conversation(s, target, auto_start=on)), half))
        rows.add(row)
        rows.add(self._button("Test conversation", lambda: self._start_preview(entity), width=width, style=S_ACTIVE))

        rows.add(gui.UISpace(height=4))
        rows.add(self._label("Lines", bold=True, size=11))
        for node_id in order:
            node = nodes[node_id]
            flow = " ?" if node.get("choices") else (f" > {number[node['next']]}" if node.get("next") in number else " (end)")
            text = f"{number[node_id]}. {_short(node.get('text', ''), 30)}{flow}"
            rows.add(self._button(text, partial(self._select_line, node_id), width=width,
                                  style=S_ACTIVE if node_id == self.dlg_line else S_BUTTON))
            if node_id == self.dlg_line:
                rows.anchor("line_editor")
                self._line_editor(rows, entity, node_id, node, number, order, width)
        last = nodes[order[-1]]
        half = (width - 6) // 2
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        if not last.get("next") and not last.get("choices"):
            row.add(self._button(f"+ Next line (after {len(order)})", lambda: self._add_line(target, None), width=half))
        row.add(self._button("+ Separate line", lambda: self._add_line(target, None, link=False), width=half))
        rows.add(row)
        rows.add(self._label("A separate line follows nothing: lead to it from an opening or a choice.",
                             color=C_MUTED, size=9, width=width))

        rows.add(gui.UISpace(height=6))
        rows.anchor("openings")
        rows.add(self._label("Openings", bold=True, size=11))
        rows.add(self._label("The first that applies picks the opening line.", color=C_MUTED, size=9, width=width))
        starts = talk["starts"]

        def opening(i: int, rule: dict[str, Any]) -> None:  # one opening rule's row (i is this rule's, not the loop's)
            def save_rule(**changes: Any) -> None:
                rules = [dict(r) for r in starts]
                rules[i].update(changes)
                self._edit(lambda s: ops.set_start_rules(s, target, rules), "Opening changed.")

            row = gui.UIBoxLayout(vertical=False, space_between=4)
            row.add(self._label(f"{i + 1}. start at line", color=C_MUTED, size=10, width=118))
            row.add(self._field(str(number.get(str(rule.get("node")), "")), lambda v: self._line_ref(
                v, order, lambda node: save_rule(node=node)), width=50, key=f"open_node_{i}"))
            row.add(self._button("Remove", lambda: self._edit(lambda s: ops.set_start_rules(
                s, target, [r for j, r in enumerate(starts) if j != i]), "Opening removed."), width=width - 122 - 50 - 8, style=S_DANGER))
            rows.add(row)
            self._flag_field(rows, "  when flags set", rule.get("require_flags"), lambda v: save_rule(require_flags=v), width,
                             f"open_req_{i}")
            self._flag_field(rows, "  and not set", rule.get("forbid_flags"), lambda v: save_rule(forbid_flags=v), width,
                             f"open_forbid_{i}")

        for i, rule in enumerate(starts):
            opening(i, rule)
        self._labeled(rows, "Otherwise line", self._field(str(number.get(talk["start"], 1)), lambda v: self._line_ref(
            v, order, lambda node: self._edit(lambda s: ops.set_conversation(s, target, start=node), "Opening changed."), allow_end=False),
            width=60, key="dlg_start"), width)
        rows.add(self._button("+ Opening", lambda: self._edit(lambda s: ops.set_start_rules(
            s, target, starts + [{"node": order[0], "require_flags": [], "forbid_flags": []}]), "Added an opening: set its flags."),
            width=110))

    def _line_ref(self, value: str, order: list[str], then: Callable[[str | None], object], allow_end: bool = True) -> None:
        text = value.strip()
        if not text:
            if allow_end:
                then(None)
            else:
                self._say("Give a line number.", ok=False)
            return
        if not text.isdigit() or not 1 <= int(text) <= len(order):
            self._say(f"There is no line {text}: lines are numbered 1 to {len(order)}" + (", or leave it empty to end." if allow_end else "."), ok=False)
            self._rebuild()
            return
        then(order[int(text) - 1])

    def _select_line(self, node_id: str) -> None:
        self._flush_fields()
        self.dlg_line = None if self.dlg_line == node_id else node_id
        self.dlg_choice = None
        self._scroll_to = "line_editor" if self.dlg_line else None
        self._rebuild()

    def _add_line(self, target: str, after: str | None, *, link: bool = True) -> None:
        made: list[str] = []

        def change(scene: dict[str, Any]) -> dict[str, Any]:
            out, node_id = ops.add_line(scene, target, after=after, text="...", link=link)
            made.append(node_id)
            return out

        said = ("Added a line: write it in the box." if link else
                "Added a separate line: nothing leads to it yet. Use it from an opening or a choice.")
        if self._edit(change, said):
            self.dlg_line, self.dlg_choice = made[0], None
            self._scroll_to, self._focus_after_build = "line_editor", "line_text"
            self._rebuild()

    def _line_editor(self, rows: Rows, entity: dict[str, Any], node_id: str, node: dict[str, Any], number: dict[str, int],
                     order: list[str], width: int) -> None:
        target = entity["id"]
        self._labeled(rows, "  Says", self._field(str(node.get("text", "")), lambda v: self._edit(
            lambda s: ops.set_line(s, target, node_id, text=v), "Line changed."), width=width - 122, key="line_text"), width)
        self._labeled(rows, "  Speaker (optional)", self._field(str(node.get("speaker", "")), lambda v: self._edit(
            lambda s: ops.set_line(s, target, node_id, speaker=v), "Speaker changed."), width=width - 122, key="line_speaker"), width)
        if not node.get("choices"):
            self._labeled(rows, "  Then line (empty: end)", self._field(str(number.get(str(node.get("next")), "")), lambda v: self._line_ref(
                v, order, lambda nxt: self._edit(lambda s: ops.set_line(s, target, node_id, next_line=nxt), "Flow changed.")),
                width=width - 122, key="line_next"), width)
        for i, choice in enumerate(node.get("choices") or []):
            choice = choice if isinstance(choice, dict) else {"text": str(choice)}
            goes = f" > {number[choice['next']]}" if choice.get("next") in number else " (end)"
            needs = f"  [needs {_names(choice.get('require_flags'))}]" if choice.get("require_flags") else ""
            rows.add(self._button(f"  {chr(97 + i)}) {_short(choice.get('text', ''), 22)}{goes}{needs}",
                                  partial(self._select_choice, i), width=width,
                                  style=S_ACTIVE if self.dlg_choice == i else S_BUTTON))
            if self.dlg_choice == i:
                self._choice_editor(rows, target, node_id, i, choice, number, order, width)
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        third = (width - 8) // 3
        row.add(self._button("+ Choice", lambda: self._add_choice(target, node_id, len(node.get("choices") or [])), width=third))
        row.add(self._button("+ Line after", lambda: self._add_line(target, node_id), width=third))
        row.add(self._button("Delete line", lambda: self._delete_line(target, node_id), width=third, style=S_DANGER))
        rows.add(row)

    def _delete_line(self, target: str, node_id: str) -> None:
        if self._edit(lambda s: ops.remove_line(s, target, node_id), "Line deleted."):
            self.dlg_line, self.dlg_choice = None, None
            self._rebuild()

    def _select_choice(self, index: int) -> None:
        self._flush_fields()
        self.dlg_choice = None if self.dlg_choice == index else index
        self._rebuild()

    def _add_choice(self, target: str, node_id: str, index: int) -> None:
        if self._edit(lambda s: ops.add_choice(s, target, node_id, "Choice"), "Added a choice: write it in the box."):
            self.dlg_choice, self._focus_after_build = index, "choice_text"
            self._rebuild()

    def _choice_editor(self, rows: Rows, target: str, node_id: str, index: int, choice: dict[str, Any],
                       number: dict[str, int], order: list[str], width: int) -> None:
        def save(**fields: Any) -> None:
            self._edit(lambda s: ops.set_choice(s, target, node_id, index, **fields), "Choice changed.")

        self._labeled(rows, "    Choice says", self._field(str(choice.get("text", "")), lambda v: save(text=v), width=width - 122,
                                                           key="choice_text"), width)
        self._labeled(rows, "    Goes to line", self._field(str(number.get(str(choice.get("next")), "")), lambda v: self._line_ref(
            v, order, lambda nxt: save(next_line=nxt)), width=width - 122, key="choice_next"), width)
        self._flag_field(rows, "    Requires flags", choice.get("require_flags"), lambda v: save(require_flags=v), width, "choice_req")
        self._flag_field(rows, "    Not if flags", choice.get("forbid_flags"), lambda v: save(forbid_flags=v), width, "choice_forbid")
        self._flag_field(rows, "    Sets flags", list((choice.get("set_flags") or {}).keys()), lambda v: save(set_flags=v), width,
                         "choice_sets")
        self._flag_field(rows, "    Clears flags", choice.get("clear_flags"), lambda v: save(clear_flags=v), width, "choice_clears")
        counters = ", ".join(f"{k}" if float(v) == 1 else f"{k}{'+' if float(v) > 0 else ''}{float(v):g}"
                             for k, v in (choice.get("inc_counters") or {}).items())
        self._labeled(rows, "    Counts up", self._field(counters, lambda v: save(add_counters=v), width=width - 122,
                                                                 key="choice_counters"), width)
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        half = (width - 6) // 2
        row.add(self._toggle("Choice once", bool(choice.get("once")), lambda on: save(once=on), half))
        row.add(self._button("Delete choice", lambda: self._delete_choice(target, node_id, index), width=half, style=S_DANGER))
        rows.add(row)

    def _delete_choice(self, target: str, node_id: str, index: int) -> None:
        if self._edit(lambda s: ops.remove_choice(s, target, node_id, index), "Choice deleted."):
            self.dlg_choice = None
            self._rebuild()

    # ---------------------------------------------------------------- conversation tester
    def _start_preview(self, entity: dict[str, Any], flags: set[str] | None = None) -> None:
        self._flush_fields()
        talk = ops.conversation(entity)
        state = {"id": entity["id"], "flags": set(flags or ()), "counters": {}, "node": None}
        state["node"] = self._preview_opening(talk, state["flags"])
        self.preview, self.panel, self.panel_scroll = state, "preview", 0
        self._rebuild()

    @staticmethod
    def _preview_opening(talk: dict[str, Any], flags: set[str]) -> str | None:
        for rule in talk["starts"]:
            if rule.get("node") in talk["nodes"] and set(rule.get("require_flags") or []) <= flags \
                    and not set(rule.get("forbid_flags") or []) & flags:
                return str(rule["node"])
        start: str | None = talk["start"]
        return start

    def _preview_panel(self, rows: Rows, width: int) -> None:
        state = self.preview or {}
        entity = self._entity(state.get("id"))
        if entity is None:
            self._cancel_panel()
            return
        talk = ops.conversation(entity)
        rows.add(self._label("Testing the conversation", bold=True, size=12))
        rows.add(self._label("Nothing here changes your game; flags below are pretend.", color=C_MUTED, size=9, width=width))
        self._labeled(rows, "Pretend flags", self._field(_names(sorted(state["flags"])), lambda v: self._start_preview(
            entity, set(ops.flag_names(v))), width=width - 122, key="preview_flags"), width)
        node = talk["nodes"].get(state.get("node") or "")
        if node is None:
            rows.add(self._label("(The conversation has ended.)", color=C_OK, width=width))
        else:
            speaker = node.get("speaker") or talk["speaker"]
            rows.add(self._label(speaker, bold=True, size=11))
            rows.add(self._label(str(node.get("text", "")), size=11, width=width))
            choices = [c if isinstance(c, dict) else {"text": str(c)} for c in node.get("choices") or []]
            for choice in choices:
                missing = [f for f in choice.get("require_flags") or [] if f not in state["flags"]]
                blocked = [f for f in choice.get("forbid_flags") or [] if f in state["flags"]]
                reason = f"  (needs {_names(missing)})" if missing else (f"  (not with {_names(blocked)})" if blocked else "")
                rows.add(self._button(_short(choice.get("text", ""), 30) + reason, partial(self._preview_choose, choice), width=width,
                                      disabled=bool(missing or blocked)))
            if not choices:
                rows.add(self._button("Next" if node.get("next") else "End", lambda: self._preview_go(node.get("next")), width=120,
                                      style=S_ACTIVE))
        if state.get("counters"):
            rows.add(self._label("Counters: " + ", ".join(f"{k} = {v:g}" for k, v in state["counters"].items()), color=C_MUTED, size=10))
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._button("Restart", lambda: self._start_preview(entity, state["flags"]), width=100))
        row.add(self._button("Back to editing", self._end_preview, width=150))
        rows.add(row)

    def _preview_choose(self, choice: dict[str, Any]) -> None:
        state = self.preview or {}
        state["flags"] |= set((choice.get("set_flags") or {}).keys())
        state["flags"] -= set(choice.get("clear_flags") or [])
        for name, step in (choice.get("inc_counters") or {}).items():
            state["counters"][name] = state["counters"].get(name, 0) + float(step)
        self._preview_go(choice.get("next"))

    def _preview_go(self, node_id: str | None) -> None:
        if self.preview is not None:
            self.preview["node"] = node_id
        self._rebuild()

    def _end_preview(self) -> None:
        self.preview, self.panel = None, "inspect"
        self._rebuild()

    # ---------------------------------------------------------------- Conditions
    def _conditions_tab(self, rows: Rows, entity: dict[str, Any], width: int) -> None:
        target = entity["id"]
        need, never = ops.show_when(entity)
        rows.add(self._label("Show when", bold=True, size=12))
        rows.add(self._label("Hidden objects aren't drawn, don't block and can't be used.", color=C_MUTED, size=9, width=width))
        self._flag_field(rows, "Requires flags", need, lambda v: self._edit(lambda s: ops.set_show_when(s, target, v, never), "Shown when changed."),
                         width, "show_req")
        self._flag_field(rows, "Hidden once set", never, lambda v: self._edit(lambda s: ops.set_show_when(s, target, need, v), "Shown when changed."),
                         width, "show_forbid")
        if "Dialogue" in ops.entity_behaviours(entity):
            talk = ops.conversation(entity)
            rows.add(gui.UISpace(height=6))
            rows.add(self._label("Can be talked to when", bold=True, size=12))
            self._flag_field(rows, "Requires flags", talk["require_flags"], lambda v: self._edit(
                lambda s: ops.set_conversation(s, target, require_flags=v), "Changed when it can talk."), width, "talk_req")
            self._flag_field(rows, "Not if flags", talk["forbid_flags"], lambda v: self._edit(
                lambda s: ops.set_conversation(s, target, forbid_flags=v), "Changed when it can talk."), width, "talk_forbid")
        rows.add(gui.UISpace(height=6))
        rows.anchor("pictures")
        rows.add(self._label("Looks different when", bold=True, size=12))
        rules = ops.picture_rules(entity)

        def picture_rule(i: int, rule: dict[str, Any]) -> None:  # one picture rule's row
            def save_rule(**changes: Any) -> None:
                updated = [dict(r) for r in rules]
                updated[i].update(changes)
                self._edit(lambda s: ops.set_picture_rules(s, target, updated), "Picture change saved.")

            row = gui.UIBoxLayout(vertical=False, space_between=4)
            space = gui.UISpace(width=32, height=32)
            self._thumbs.append((space, str(self.project.root / rule["sprite"])))
            row.add(space)
            row.add(self._button(_short(Path(rule["sprite"]).name, 20), lambda: self._open_picker_images(
                "The picture to show", lambda rel: save_rule(sprite=rel)), width=width - 38 - 84))
            row.add(self._button("Remove", lambda: self._edit(lambda s: ops.set_picture_rules(
                s, target, [r for j, r in enumerate(rules) if j != i]), "Picture change removed."), width=80, style=S_DANGER))
            rows.add(row)
            self._flag_field(rows, "  when flags set", rule.get("require_flags"), lambda v: save_rule(require_flags=v), width, f"pic_req_{i}")
            self._flag_field(rows, "  and not set", rule.get("forbid_flags"), lambda v: save_rule(forbid_flags=v), width, f"pic_forbid_{i}")

        for i, rule in enumerate(rules):
            picture_rule(i, rule)
        rows.add(self._button("+ Picture change...", lambda: self._open_picker_images(
            "The picture to show", lambda rel: self._edit(lambda s: ops.set_picture_rules(
                s, target, rules + [{"sprite": rel, "require_flags": [], "forbid_flags": []}]), "Added: now choose its flags.")),
            width=180))

    # ---------------------------------------------------------------- Behaviours
    def _behaviours_tab(self, rows: Rows, entity: dict[str, Any], width: int) -> None:
        rows.add(self._label("Behaviours", bold=True, size=12))
        rows.add(self._label("Everything an object can do. The tabs above set up the common ones for you.",
                             color=C_MUTED, size=9, width=width))
        names = ops.entity_behaviours(entity)
        if not names:
            rows.add(self._label("None yet.", color=C_MUTED))
        for name in names:
            info = behaviour_guide.guide(name)
            row = gui.UIBoxLayout(vertical=False, space_between=4)
            arrow = "v " if self.expanded == name else "> "
            row.add(self._button(arrow + info.label, partial(self._toggle_expand, name), width=width - 80,
                                 style=S_ACTIVE if self.expanded == name else S_BUTTON))
            row.add(self._button("Remove", partial(self.remove_behaviour, name), width=76, style=S_DANGER))
            rows.add(row)
            config = (entity.get("behaviour_config") or {}).get(name) or {}
            for problem in behaviour_guide.problems(name, config if isinstance(config, dict) else {}):
                rows.add(self._label(problem, color=(240, 200, 120), size=9, width=width))
            if self.expanded == name:
                rows.add(self._label(f"{info.summary}  ({name})", color=C_MUTED, size=9, width=width))
                self._behaviour_fields(rows, entity, name, width)
        rows.add(self._button("+ Add behaviour", self._open_picker, width=150, style=S_ACTIVE))

    # ---------------------------------------------------------------- AI proposals
    def _ai_panel(self, rows: Rows, width: int) -> None:
        rows.add(self._label("Changes proposed from outside", bold=True, size=12))
        rows.add(self._label("An AI (or a script) connected to this project can propose changes. Nothing changes "
                             "until you accept; accepted changes are one Undo away.", color=C_MUTED, size=9, width=width))
        pending, done = self.ai.pending(), [p for p in self.ai.proposals if p.status not in ("pending", "conflict")]
        if not pending:
            rows.add(self._label("Nothing waiting.", color=C_MUTED))
        half = (width - 6) // 2
        for proposal in reversed(pending):
            rows.add(gui.UISpace(height=4))
            rows.add(self._label(f"{proposal.title}", bold=True, size=11, width=width))
            rows.add(self._label(f"from {proposal.source}", color=C_MUTED, size=9))
            for line in proposal.summary[:24]:
                rows.add(self._label("- " + line, size=10, width=width))
            if len(proposal.summary) > 24:
                rows.add(self._label(f"... and {len(proposal.summary) - 24} more", color=C_MUTED, size=9))
            if proposal.status == "conflict":
                rows.add(self._label(proposal.message, color=(240, 200, 120), size=9, width=width))
                for clash in proposal.conflicts[:8]:
                    rows.add(self._label(f"  {clash.get('what') or clash['path']}: here {clash['studio']!r}, proposed {clash['ai']!r}",
                                         color=(240, 200, 120), size=9, width=width))
            row = gui.UIBoxLayout(vertical=False, space_between=6)
            row.add(self._button("Accept", partial(self.accept_ai, proposal), width=half, style=S_ACTIVE,
                                 disabled=proposal.status == "conflict"))
            row.add(self._button("Reject", partial(self.reject_ai, proposal), width=half, style=S_DANGER))
            rows.add(row)
        if done:
            rows.add(gui.UISpace(height=8))
            rows.add(self._label("Earlier", bold=True, size=11))
            for proposal in list(reversed(done))[:6]:
                rows.add(self._label(f"{proposal.title}: {proposal.status}", color=C_MUTED, size=10, width=width))
        rows.add(self._button("Close", self._cancel_panel, width=80))

    # ---------------------------------------------------------------- flags
    def _open_players(self) -> None:
        self.panel = "players"
        self._rebuild()

    def _players_panel(self, rows: Rows, width: int) -> None:
        rows.add(self._label("One player for the whole game", bold=True, size=12))
        rows.add(self._label("Each room of this project has its own copy of the player. With one player, its picture, "
                             "size, collision and behaviours are set once for every room; each room keeps where its "
                             "player starts.", color=C_MUTED, size=9, width=width))
        differences = self.project.player_differences()
        if differences:
            rows.add(self._label(f"Compared with {self.project.label(self.project.start_key())}'s player:", size=10))
            for key, what in differences.items():
                rows.add(self._label(f"  {self.project.label(key)}: different {', '.join(what)}", color=(240, 200, 120),
                                     size=10, width=width))
        rows.add(self._label("Whose player should every room use?", size=10))
        for key in self.project.own_players():
            rows.add(self._button(f"Use {self.project.label(key)}'s player", partial(self.share_player, key), width=width))
        rows.add(self._button("Keep them separate", self.keep_separate_players, width=width))

    def _flags_panel(self, rows: Rows, width: int) -> None:
        rows.add(self._label("Flags", bold=True, size=12))
        rows.add(self._label("A flag is a yes/no fact your game remembers (has_shovel). It exists once something "
                             "sets or checks it: type a new name in any flag box to make one.", color=C_MUTED, size=9, width=width))
        uses = self._flag_uses()
        if not uses:
            rows.add(self._label("No flags yet.", color=C_MUTED))
        for name, places in uses.items():
            rows.add(self._label(name, bold=True, size=11))
            for place in places:
                rows.add(self._label("  " + place, color=C_MUTED, size=9, width=width))
        rows.add(self._button("Close", self._cancel_panel, width=80))

    # ---------------------------------------------------------------- previews (drawn over the UI)
    def _draw_previews(self) -> None:
        a = optional_arcade.arcade
        for space, path in self._thumbs:
            if self.panel not in ("inspect", "pick_image") or space.width <= 1 or not _on_screen(space):
                continue
            image = self._image(path)
            if image is None:
                a.draw_lrbt_rectangle_outline(space.left, space.right, space.bottom, space.top, (200, 80, 80), 1)
                continue
            key = ("thumb", path)
            if key not in self._textures:
                self._textures[key] = a.Texture(image, hash=f"mesh-studio-thumb-{path}")
            scale = min(space.width / image.width, space.height / image.height, 4.0)
            w, h = image.width * scale, image.height * scale
            a.draw_lrbt_rectangle_filled(space.left, space.right, space.bottom, space.top, (24, 26, 31))
            a.draw_texture_rect(self._textures[key], a.XYWH(space.center_x, space.center_y, w, h), pixelated=True)
        space = self._anim_space
        if space is not None and self.panel == "inspect" and self.tab == "animation" and _on_screen(space):
            frames = self._clip_frames(getattr(space, "mesh_clip", {}) or {})
            a.draw_lrbt_rectangle_filled(space.left, space.right, space.bottom, space.top, (24, 26, 31))
            if frames:
                fps = float((getattr(space, "mesh_clip", {}) or {}).get("fps", 8) or 8)
                frame = frames[int(time.monotonic() * fps) % len(frames)]
                scale = min(space.width / frame.width, space.height / frame.height, 4.0)
                a.draw_texture_rect(frame, a.XYWH(space.center_x, space.center_y, frame.width * scale, frame.height * scale),
                                    pixelated=True)
