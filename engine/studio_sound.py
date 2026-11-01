"""Mesh Studio's sound authoring (Milestone 21B): sounds placed in a room, and its weather and how it sounds.

- **Sound** (top bar): the room's rain (off, light, steady, heavy) and wind, their sounds and volumes, and the room's
  sound emitters (``+ Add sound`` places one; a click on one in the list selects it).
- **A sound emitter** is an object (Objects > Sound, or ``+ Add sound``): placed with a click on the map (in an HD-2D
  room on the floor under the mouse, at its height), moved by dragging, deleted, copied and undone like any object.
  Its inspector chooses its sound (the project's sounds, Mesh's library, or a file imported), its volume, how far it
  is heard, stereo, looping and fades. While editing it shows as a speaker with two rings: full strength inside the
  filled one, silent beyond the outer one; the game never shows it.
- A sound chosen from Mesh's library (``assets/ambience``: CC0 loops) or imported is copied into the project's
  ``assets/ambience`` (straight away, like a picture: not an undo step), so the game and its export have it.

The editor is silent: rooms' sounds play in play-tests (F4) only (``AudioManager.scene_music``)."""

from __future__ import annotations

import math
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import engine.optional_arcade as optional_arcade
import engine.project_ops as ops
from engine.studio_ui import C_ERROR, C_MUTED, C_OK, S_ACTIVE, S_BUTTON, ask_path, gui

if TYPE_CHECKING:
    from engine.studio_project import Project

PX = 32.0  # px a metre (a tile)
SOUND_BUILT_IN: dict[str, Any] = {"id": "sound", "display_name": "Sound", "built_in": "sound"}
RAIN_TITLES = (("off", "Off"), ("light", "Light"), ("steady", "Steady"), ("heavy", "Heavy"))
WINDS = (("Calm", 0.0, 0.0), ("Breeze", 3.0, 0.3), ("Strong", 9.0, 0.3), ("Gusty", 5.0, 0.9))  # as the 3D view's
SOUND_FILE_TYPES = [("Sound files", "*.wav *.ogg *.mp3"), ("All files", "*.*")]


class SoundMixin:
    if TYPE_CHECKING:  # what the mixin uses of its host, ``engine.studio.Studio``
        project: Project
        panel: str
        panel_scroll: int
        selected: str | None
        place_prefab: dict[str, Any] | None
        zoom: float
        hd2d: Any
        window: Any
        tab: str

        def _label(self, text: str, *, color: tuple[int, int, int] = ..., size: int = 11, width: int | None = None,
                   bold: bool = False) -> Any: ...
        def _button(self, text: str, action: Callable[[], object], *, width: int = 100, style: dict[str, Any] = ...,
                    disabled: bool = False) -> Any: ...
        def _field(self, text: str, commit: Callable[[str], object], *, width: int, key: str | None = None) -> Any: ...
        def _toggle(self, label: str, value: bool, flip: Callable[[bool], object], width: int) -> Any: ...
        def _labeled(self, rows: Any, label: str, widget: Any, width: int, label_width: int = 118) -> None: ...
        def _edit(self, change: Callable[[dict[str, Any]], dict[str, Any]], ok: str = "") -> bool: ...
        def _rebuild(self) -> None: ...
        def _say(self, text: str, ok: bool = True) -> None: ...
        def _flush_fields(self) -> bool: ...
        def _cancel_panel(self) -> None: ...
        def _text(self, key: str, text: str, x: float, y: float, color: tuple[int, int, int], size: int = 10) -> None: ...
        def arm_place(self, prefab: dict[str, Any]) -> None: ...
        def select(self, entity_id: str | None) -> None: ...

    # ---------------------------------------------------------------- the Sound panel
    def open_sound(self) -> None:
        self._flush_fields()
        self.panel, self.panel_scroll = ("inspect" if self.panel == "sound" else "sound"), 0
        self._rebuild()

    def arm_sound(self) -> None:
        """``+ Add sound``: the next click on the map places a sound emitter."""
        if self.place_prefab is not SOUND_BUILT_IN:
            self.arm_place(SOUND_BUILT_IN)

    def _sound_panel(self, rows: Any, width: int) -> None:
        scene = self.project.scene()
        quarter = (width - 12) // 4
        rows.add(self._label("Sound and weather", bold=True, size=12))
        rows.add(self._label("What this room sounds like. Heard in play (F4); the editor stays silent.", color=C_MUTED,
                             size=9, width=width))
        rows.add(self._label("Rain (snow and windborne leaves: Environment, Weather particles...)" if self.hd2d.active
                             else "Rain", color=C_MUTED, size=10, width=width))
        rain = ops.rain_strength(scene)
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        for key, title in RAIN_TITLES:
            row.add(self._button(title, partial(self.set_rain, key), width=quarter,
                                 style=S_ACTIVE if rain == key else S_BUTTON))
        rows.add(row)
        rows.add(self._label("Wind", color=C_MUTED, size=10))
        wind = _wind_of(scene)
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        for title, speed, gust in WINDS:
            now = abs(wind.speed - speed) < 1e-6 and (speed == 0 or abs(wind.gust - gust) < 1e-6)
            row.add(self._button(title, partial(self.set_room_wind, title, speed, gust), width=quarter,
                                 style=S_ACTIVE if now else S_BUTTON))
        rows.add(row)
        sounds = ops.weather_sounds_of(scene)
        for kind, title in (("rain", "Rain sound"), ("wind", "Wind sound")):
            path = sounds[kind]
            rows.add(self._label(f"{title}: {_short(path) if path else 'none'}", color=C_MUTED, size=10, width=width))
            problem = self._sound_problem(path) if path else None
            if problem:
                rows.add(self._label(problem, color=C_ERROR, size=9, width=width))
            row = gui.UIBoxLayout(vertical=False, space_between=4)
            row.add(self._button("Choose...", partial(self._open_sound_picker, f"{title} for this room",
                                                      partial(self._set_weather_sound, kind)), width=(width - 8) // 3))
            row.add(self._button("None", partial(self._set_weather_sound, kind, ""), width=(width - 8) // 3,
                                 disabled=not path))
            row.add(self._field(f"{round(sounds[f'{kind}_volume'] * 100)}", partial(self._set_weather_volume, kind),
                                width=(width - 8) // 3 - 30, key=f"weather_{kind}_volume"))
            row.add(self._label("%", color=C_MUTED, size=10, width=24))
            rows.add(row)
        rows.add(self._label("The rain is heard as hard as it falls, the wind as hard as it blows where the player is; "
                             "both fade when the weather stops.", color=C_MUTED, size=9, width=width))
        rows.add(gui.UISpace(height=6))
        emitters = [e for e in ops.entities(scene) if ops.sound_emitter_of(e) is not None]
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        row.add(self._label(f"Sounds in this room ({len(emitters)})", bold=True, size=11, width=width - 110))
        row.add(self._button("+ Add sound", self.arm_sound, width=104,
                             style=S_ACTIVE if self.place_prefab is SOUND_BUILT_IN else S_BUTTON))
        rows.add(row)
        for entity in emitters:
            emitter = ops.sound_emitter_of(entity) or {}
            text = f"{entity.get('name') or 'Sound'}: {_short(emitter.get('sound') or 'no sound yet', 22)}"
            rows.add(self._button(text, partial(self._select_sound, str(entity["id"])), width=width,
                                  style=S_ACTIVE if entity.get("id") == self.selected else S_BUTTON))
        rows.add(self._label("+ Add sound, then click the map where it is heard from: water, birds in the trees, a "
                             "machine. Drag it to move it.", color=C_MUTED, size=9, width=width))
        rows.add(self._button("Done", self.open_sound, width=80))

    def _select_sound(self, entity_id: str) -> None:
        self.select(entity_id)  # (the inspector: its look tab is its sound)

    def set_rain(self, strength: str) -> None:
        sounds = ops.weather_sounds_of(self.project.scene())
        library = self._library_sound("rain_loop.wav") if strength != "off" and not sounds["rain"] else None

        def change(scene: dict[str, Any]) -> dict[str, Any]:
            out = ops.set_rain(scene, strength)
            return ops.set_weather_sounds(out, rain=library) if library else out

        title = dict(RAIN_TITLES)[strength]
        said = "No rain." if strength == "off" else f"Rain: {title.lower()}." + (
            f" Its sound: Mesh's rain ({library}); change it below." if library else "")
        self._edit(change, said)

    def set_room_wind(self, title: str, speed: float, gust: float) -> None:
        sounds = ops.weather_sounds_of(self.project.scene())
        library = self._library_sound("wind_loop.wav") if speed > 0 and not sounds["wind"] else None

        def change(scene: dict[str, Any]) -> dict[str, Any]:
            out = ops.set_wind(scene, speed=speed, gust=gust)
            return ops.set_weather_sounds(out, wind=library) if library else out

        said = "Calm." if speed <= 0 else f"{title}: {speed:g} m/s, gusts {gust:g}." + (
            f" Its sound: Mesh's wind ({library}); change it below." if library else "")
        self._edit(change, said)

    def _set_weather_sound(self, kind: str, path: str) -> None:
        self._edit(lambda s: ops.set_weather_sounds(s, **{kind: path}),
                   f"{kind.capitalize()} sound: {_short(path)}." if path else f"No {kind} sound.")

    def _set_weather_volume(self, kind: str, text: str) -> None:
        try:
            value = float(text) / 100.0
        except ValueError:
            self._say("Volume: a number from 0 to 100.", ok=False)
            return
        self._edit(lambda s: ops.set_weather_sounds(s, **{f"{kind}_volume": max(0.0, min(1.0, value))}),
                   f"{kind.capitalize()} volume: {round(max(0.0, min(1.0, value)) * 100)}%.")

    # ---------------------------------------------------------------- a sound emitter's inspector (its Look tab)
    def _sound_look(self, rows: Any, entity: dict[str, Any], width: int) -> None:
        target, emitter = str(entity["id"]), ops.sound_emitter_of(entity) or {}
        half = (width - 126) // 2

        def change(ok: str = "Sound changed.", **values: Any) -> None:
            self._edit(lambda s: ops.set_sound_emitter(s, target, **values), ok)

        def number(key: str, scale: float, lo: float, hi: float, what: str) -> Callable[[str], object]:
            def commit(text: str) -> None:
                try:
                    value = float(text)
                except ValueError:
                    value = math.nan
                if not math.isfinite(value) or not lo <= value <= hi:
                    self._say(f"{what}: a number from {lo:g} to {hi:g}.", ok=False)
                    self._rebuild()
                    return
                change(f"{what}: {value:g}.", **{key: value * scale})
            return commit

        rows.add(self._label("Sound", bold=True, size=12))
        if emitter.get("error"):
            rows.add(self._label(f"Not used as set: {emitter['error']}. Correct it here.", color=C_ERROR, size=9,
                                 width=width))
        sound = str(emitter.get("sound") or "")
        rows.add(self._label(f"File: {_short(sound, 38)}" if sound else "No sound chosen yet.",
                             color=C_OK if sound else C_ERROR, size=10, width=width))
        problem = self._sound_problem(sound) if sound else None
        if problem:
            rows.add(self._label(problem, color=C_ERROR, size=9, width=width))
        rows.add(self._button("Choose sound...", partial(self._open_sound_picker, "Choose its sound",
                                                         lambda rel: change(f"Sound: {_short(rel)}.", sound=rel)),
                              width=width, style=S_BUTTON if sound else S_ACTIVE))
        self._labeled(rows, "Volume (%)", self._field(f"{round(float(emitter.get('volume', 0.8)) * 100)}",
                                                      number("volume", 0.01, 0, 100, "Volume"), width=half,
                                                      key="sound_volume"), width)
        self._labeled(rows, "Full strength within (m)", self._field(
            f"{float(emitter.get('radius', 64)) / PX:g}", number("radius", PX, 0, 255, "Full strength within"),
            width=half, key="sound_radius"), width)
        self._labeled(rows, "Heard up to (m)", self._field(
            f"{float(emitter.get('distance', 320)) / PX:g}", number("distance", PX, 0.25, 500, "Heard up to"),
            width=half, key="sound_distance"), width)
        if self.hd2d.active:
            elevation = entity.get("elevation", 0.0)
            metres = float(elevation) / PX if isinstance(elevation, (int, float)) and not isinstance(elevation, bool) else 0.0
            self._labeled(rows, "Height (m)", self._field(f"{round(metres, 2):g}", partial(self._set_sound_height, target),
                                                          width=half, key="sound_height"), width)
        rows.add(self._toggle("Stereo (heard from its side)", bool(emitter.get("stereo", True)),
                              lambda on: change("Heard from its side." if on else "Heard the same in both ears.",
                                                stereo=on), width))
        rows.add(self._toggle("Loop", bool(emitter.get("loop", True)),
                              lambda on: change("Plays round." if on else "Plays once each time the player comes near.",
                                                loop=on), width))
        rows.add(self._toggle("On", bool(emitter.get("enabled", True)),
                              lambda on: change("On." if on else "Off: silent.", enabled=on), width))
        self._labeled(rows, "Fade in / out (s)", self._fields_pair(
            (f"{float(emitter.get('fade_in', 1.0)):g}", number("fade_in", 1.0, 0, 30, "Fade in"), "sound_fade_in"),
            (f"{float(emitter.get('fade_out', 1.0)):g}", number("fade_out", 1.0, 0, 30, "Fade out"), "sound_fade_out"),
            half), width)
        rows.add(self._label("Louder as the player comes near: full strength inside the filled ring, fading to "
                             "silence at the outer ring. Shown only while editing; the game has no picture of it. "
                             "1 m is a tile.", color=C_MUTED, size=9, width=width))

    def _fields_pair(self, a: tuple[str, Callable[[str], object], str], b: tuple[str, Callable[[str], object], str],
                     width: int) -> Any:
        row = gui.UIBoxLayout(vertical=False, space_between=4)
        each = (width - 4) // 2
        row.add(self._field(a[0], a[1], width=each, key=a[2]))
        row.add(self._field(b[0], b[1], width=each, key=b[2]))
        return row

    def _set_sound_height(self, target: str, text: str) -> None:
        try:
            metres = float(text)
        except ValueError:
            self._say("Height: a number of metres.", ok=False)
            return
        self._edit(lambda s: ops.set_entity_fields(s, target, elevation=round(metres * PX, 2)), f"Height: {metres:g} m.")

    # ---------------------------------------------------------------- choosing a sound file
    def _open_sound_picker(self, title: str, choose: Callable[[str], object], music: bool = False) -> None:
        """Choose a sound file (``music``: a room's soundtrack, Milestone 23D: the project's files with
        ``assets/music/`` first, imports into ``assets/music/``, no ambience library)."""
        self._flush_fields()
        self.sound_pick: dict[str, Any] | None = {"title": title, "choose": choose, "back": self.panel, "music": music}
        self.panel, self.panel_scroll = "pick_sound", 0
        self._rebuild()

    def _sound_picker(self, rows: Any, width: int) -> None:
        pick = getattr(self, "sound_pick", None) or {}
        rows.add(self._label(pick.get("title", "Choose a sound"), bold=True, size=12))
        row = gui.UIBoxLayout(vertical=False, space_between=6)
        if pick.get("music"):
            row.add(self._button("Import music file...", partial(self._import_sound, True), width=150))
            row.add(self._button("Cancel", self._cancel_sound_pick, width=80))
            rows.add(row)
            self._music_picker(rows, width)
            return
        row.add(self._button("Import sound file...", self._import_sound, width=150))
        row.add(self._button("Cancel", self._cancel_sound_pick, width=80))
        rows.add(row)
        rows.add(self._label("In this project", color=C_MUTED, size=10))
        own = self.project.sounds()
        if not own:
            rows.add(self._label("No sounds in this project yet: choose one from Mesh's library below, or import one.",
                                 color=C_MUTED, size=9, width=width))
        for rel in own:
            rows.add(self._button(_short(rel.removeprefix("assets/"), 40), partial(self._sound_picked, rel), width=width))
        from engine.sound_emitters import library  # noqa: PLC0415

        rows.add(self._label("Mesh's sound library (CC0; copied into the project when chosen)", color=C_MUTED,
                             size=10, width=width))
        for path in library():
            rows.add(self._button(f"{_LIBRARY_TITLES.get(path.name, path.stem)}  ({path.name})",
                                  partial(self._library_picked, path), width=width))
        rows.add(self._label("WAV plays on every computer; OGG and MP3 need the system's decoders.", color=C_MUTED,
                             size=9, width=width))

    def _cancel_sound_pick(self) -> None:
        pick = getattr(self, "sound_pick", None) or {}
        self.sound_pick = None
        self.panel = pick.get("back") or "inspect"
        self._rebuild()

    def _sound_picked(self, rel: str) -> None:
        problem = self._sound_problem(rel)
        if problem:
            self._say(problem, ok=False)
            return
        pick = getattr(self, "sound_pick", None) or {}
        self.sound_pick = None
        self.panel = pick.get("back") or "inspect"
        choose = pick.get("choose")
        if choose is not None:
            choose(rel)
        else:
            self._rebuild()

    def _library_picked(self, path: Path) -> None:
        try:
            rel = self.project.import_sound(path)
        except ops.OpError as err:
            self._say(str(err), ok=False)
            return
        self._sound_picked(rel)

    def _library_sound(self, name: str) -> str | None:
        """Mesh's library sound ``name`` copied into the project (its project path), or None if it can't be."""
        from engine.sound_emitters import library  # noqa: PLC0415

        path = next((p for p in library() if p.name == name), None)
        if path is None:
            return None
        try:
            return self.project.import_sound(path)
        except ops.OpError as err:
            self._say(str(err), ok=False)
            return None

    def _import_sound(self, music: bool = False) -> None:
        path = ask_path(folder=False, title="Import music (WAV, OGG or MP3)" if music else "Import a sound (WAV, OGG or MP3)",
                        filetypes=SOUND_FILE_TYPES)
        if not path:
            return
        try:
            rel = self.project.import_sound(Path(path), "music" if music else "ambience")
        except ops.OpError as err:
            self._say(str(err), ok=False)
            return
        self._sound_picked(rel)

    # ---------------------------------------------------------------- a room's music (Milestone 23D)
    def open_music(self) -> None:
        self._flush_fields()
        self.panel, self.panel_scroll = ("inspect" if self.panel == "music" else "music"), 0
        self._rebuild()

    def set_room_music(self, mode: str, path: str = "") -> None:
        """One checked edit (``project_ops.set_room_music``): one undo step."""
        label = self.project.label(self.project.current)
        said = {"continue": f"{label}: the music playing carries on.", "silence": f"{label}: silence.",
                "track": f"{label} plays {_short(path)}."}[mode]
        self._edit(lambda s: ops.set_room_music(s, mode, path), said)

    def choose_room_music(self) -> None:
        self._open_sound_picker(f"Music for {self.project.label(self.project.current)}",
                                partial(self.set_room_music, "track"), music=True)

    def _music_picker(self, rows: Any, width: int) -> None:
        own = self.project.music_files()
        rows.add(self._label("Sound files in this project (assets/music first)", color=C_MUTED, size=10, width=width))
        if not own:
            rows.add(self._label("No sound files in this project yet: import one.", color=C_MUTED, size=9, width=width))
        for rel in own:
            rows.add(self._button(_short(rel.removeprefix("assets/"), 40), partial(self._sound_picked, rel), width=width))
        rows.add(self._label("Import copies the file into assets/music/ at once (a file already there is never "
                             "replaced: a new name is used). Undo takes back the room's choice, not the file. WAV plays "
                             "on every computer; OGG and MP3 need the system's decoders.", color=C_MUTED, size=9,
                             width=width))

    def _music_panel(self, rows: Any, width: int) -> None:
        scene, key = self.project.scene(), self.project.current
        now = ops.room_music(scene)
        rows.add(self._label(f"Room music: {self.project.label(key)}", bold=True, size=12, width=width))
        rows.add(self._label("What the music does as the player enters this room (through a door, a new game or a "
                             "loaded save). Heard in play (F4) and the game; the editor stays silent.", color=C_MUTED,
                             size=9, width=width))
        if now.get("error"):
            rows.add(self._label(f"Not used as set: {now['error']}. Choose one below.", color=C_ERROR, size=9,
                                 width=width))
        for mode, title, words in (
                ("continue", "Continue previous music", "Whatever is playing carries on: a track from an earlier room, or "
                                                        "silence."),
                ("silence", "Silence", "The music stops (or fades out, with crossfade on)."),
                ("track", "Play a track", "This room's own track: it starts as the room is entered, or carries on if it "
                                          "is already playing.")):
            action = self.choose_room_music if mode == "track" else partial(self.set_room_music, mode)
            rows.add(self._button(title, action, width=width, style=S_ACTIVE if now["mode"] == mode else S_BUTTON))
            rows.add(self._label(words, color=C_MUTED, size=9, width=width))
        if now["mode"] == "track":
            path = str(now["path"])
            rows.add(self._label(f"Track: {_short(path, 40)}", color=C_OK, size=10, width=width))
            problem = self._sound_problem(path)
            if problem:
                rows.add(self._label(problem, color=C_ERROR, size=9, width=width))
            rows.add(self._button("Choose another track...", self.choose_room_music, width=width))
        rows.add(self._label(self._crossfade_words(), color=C_MUTED, size=9, width=width))
        rows.add(self._label("Every room", bold=True, size=11))
        start = ops.start_room(self.project.world)
        for room, label, _path in self.project.rooms():
            music = ops.room_music(self.project.scene(room))
            what = {"continue": "carries on", "silence": "silence"}.get(str(music["mode"])) or \
                f"plays {_short(str(music['path']).rsplit('/', 1)[-1], 24)}"
            rows.add(self._label(f"{label}{' (start)' if room == start else ''}: {what}",
                                 color=C_OK if room == key else C_MUTED, size=10, width=width))
        rows.add(self._button("Done", self.open_music, width=80))

    def _crossfade_words(self) -> str:
        """How a change of track sounds: the room's own crossfade setting, else the project's (docs/audio.md)."""
        import json  # noqa: PLC0415

        try:
            config = json.loads((self.project.root / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            config = {}
        settings = self.project.scene().get("settings") or {}
        on = settings.get("music_crossfade_enabled", (config or {}).get("music_crossfade_enabled", False))
        if not on:
            return "Changes of music are immediate (crossfade is off in the project's config)."
        out = settings.get("music_crossfade_out_s", config.get("music_crossfade_out_s", 0.25))
        fade_in = settings.get("music_crossfade_in_s", config.get("music_crossfade_in_s", 0.25))
        return f"Changes of music crossfade: {out:g} s out, {fade_in:g} s in (the project's config)."

    def _sound_problem(self, rel: str) -> str | None:
        """Why the project's sound ``rel`` can't be played here (checked once per file and change)."""
        from engine.sound_emitters import sound_problem  # noqa: PLC0415

        path = self.project.root / rel
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            stamp = None
        cache: dict[tuple[str, Any], str | None] = self.__dict__.setdefault("_sound_problems", {})
        if (rel, stamp) not in cache:
            cache[(rel, stamp)] = sound_problem(path)
        return cache[(rel, stamp)]

    # ---------------------------------------------------------------- where a sound is, while editing (2D)
    def _draw_sound(self, entity: dict[str, Any], emitter: dict[str, Any], cx: float, cy: float) -> None:
        a = optional_arcade.arcade
        chosen = entity.get("id") == self.selected
        on = bool(emitter.get("enabled", True)) and bool(emitter.get("sound"))
        colour = (120, 220, 255) if on else (170, 170, 180)
        radius, distance = float(emitter.get("radius", 64)), float(emitter.get("distance", 320))
        a.draw_circle_filled(cx, cy, radius, (*colour, 40 if chosen else 22))
        a.draw_circle_outline(cx, cy, distance, (*colour, 200 if chosen else 90), (2 if chosen else 1) / self.zoom)
        a.draw_circle_filled(cx, cy, 8 / self.zoom, colour)
        for k in (1, 2):  # a speaker's waves
            a.draw_arc_outline(cx + 6 / self.zoom, cy, 10 * k / self.zoom, 14 * k / self.zoom, colour, -50, 50,
                               1.5 / self.zoom)
        name = str(entity.get("name") or "Sound")
        self._text(f"sound:{entity.get('id')}", f"{name}: {_short(emitter.get('sound') or 'no sound', 24)}", cx,
                   cy + 14 / self.zoom, colour)


_LIBRARY_TITLES = {"rain_loop.wav": "Rain", "wind_loop.wav": "Wind", "stream_loop.wav": "Flowing water",
                   "birds_loop.wav": "Birdsong", "forest_loop.wav": "Forest or meadow"}


def _short(path: str, size: int = 30) -> str:
    text = str(path).removeprefix("assets/")
    return text if len(text) <= size else "..." + text[-(size - 3):]


def _wind_of(scene: dict[str, Any]) -> Any:
    from engine.wind import WindError, parse_wind  # noqa: PLC0415

    settings = scene.get("settings")
    try:
        return parse_wind(settings.get("wind") if isinstance(settings, dict) else None)
    except WindError:
        return parse_wind(None)
