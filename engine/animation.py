"""Sprite sheet + animation helpers for Mesh Engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, cast, TYPE_CHECKING
import engine.optional_arcade as optional_arcade
from PIL import Image
from PIL.Image import Image as PILImageClass

from .assets import AssetManager
from .paths import resolve_path
from .sprite_sheet_math import SpriteSheetSliceSpec, iter_sprite_sheet_frame_boxes


@dataclass(frozen=True, slots=True)
class SpriteSheetSpec:
    """Describes how to slice a sprite sheet image into equal frames."""

    path: str
    frame_width: int
    frame_height: int
    margin: int = 0
    spacing: int = 0
    columns: Optional[int] = None
    rows: Optional[int] = None

    def normalized_path(self) -> str:
        return str(Path(self.path))


class SpriteSheet:
    """Holds the baked textures for each frame in a sprite sheet."""

    def __init__(self, spec: SpriteSheetSpec, frames: List[optional_arcade.arcade.Texture]) -> None:
        self.spec = spec
        self.frames = frames

    def frame_count(self) -> int:
        return len(self.frames)


class SpriteSheetCache:
    """Caches generated sprite sheets so multiple entities can share them."""

    def __init__(self, assets: AssetManager) -> None:
        self.assets = assets
        self._cache: Dict[SpriteSheetSpec, SpriteSheet] = {}

    def get_or_build(self, spec: SpriteSheetSpec) -> Optional[SpriteSheet]:
        if spec in self._cache:
            return self._cache[spec]

        base_texture = self.assets.get_texture(spec.path)
        if base_texture is None:
            return None

        textures = self._slice_frames(spec, base_texture)
        if not textures:
            print(
                f"[Mesh][Animation] WARNING: Sprite sheet '{spec.path}' produced no frames"  # noqa: T201
            )
            return None

        sheet = SpriteSheet(spec, textures)
        self._cache[spec] = sheet
        return sheet

    def _slice_frames(
        self,
        spec: SpriteSheetSpec,
        base_texture: optional_arcade.arcade.Texture,
    ) -> List[optional_arcade.arcade.Texture]:
        source_image = getattr(base_texture, "image", None)
        if isinstance(source_image, Image.Image):
            sheet_image = source_image.convert("RGBA")
        else:
            try:
                resolved = resolve_path(spec.path)
                sheet_image = Image.open(resolved).convert("RGBA")
            except Exception as exc:  # noqa: BLE001
                print(f"[Mesh][Animation] WARNING: Could not load sprite sheet '{spec.path}': {exc}")  # noqa: T201
                return []

        width = int(sheet_image.width)
        height = int(sheet_image.height)

        frame_w = int(spec.frame_width)
        frame_h = int(spec.frame_height)
        margin = max(0, int(spec.margin))
        spacing = max(0, int(spec.spacing))

        if frame_w <= 0 or frame_h <= 0:
            return []

        slice_spec = SpriteSheetSliceSpec(
            sheet_width=width,
            sheet_height=height,
            frame_width=frame_w,
            frame_height=frame_h,
            margin=margin,
            spacing=spacing,
            columns=spec.columns,
            rows=spec.rows,
        )
        boxes = iter_sprite_sheet_frame_boxes(slice_spec)
        textures: List[optional_arcade.arcade.Texture] = []
        for index, box in enumerate(boxes):
            try:
                frame_image = sheet_image.crop(box)
                textures.append(
                    optional_arcade.arcade.Texture(
                        name=f"{spec.path}_f{index}",
                        image=frame_image,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[Mesh][Animation] WARNING: Failed to slice frame {index} from '{spec.path}': {exc}"  # noqa: T201
                )
        return textures


@dataclass(frozen=True, slots=True)
class AnimationEventMarker:
    """Frame-aligned event metadata for an animation clip."""

    frame: int
    label: str
    payload: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class AnimationClip:
    """Describes a play-ready animation clip."""

    name: str
    frames: List[int]
    fps: float = 8.0
    loop: bool = True
    blend: float = 0.0
    events: Tuple[AnimationEventMarker, ...] = ()
    transition_mode: str = "blend"
    hold_duration: float = 0.0


class AnimationPlayer:
    """Maintains per-entity animation state and applies frames to sprites."""

    def __init__(
        self,
        sprite: optional_arcade.arcade.Sprite,
        sheet: SpriteSheet,
        clips: Dict[str, AnimationClip],
        *,
        default_state: Optional[str] = None,
        debug: bool = False,
        default_blend: float = 0.0,
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        if not clips:
            raise ValueError("AnimationPlayer requires at least one clip")

        self.sprite = sprite
        self.sheet = sheet
        self.clips = clips
        self.debug = debug

        self.current_state: str = default_state or next(iter(clips))
        if self.current_state not in clips:
            self.current_state = next(iter(clips))

        self.frame_cursor: int = 0
        self.elapsed: float = 0.0
        self.paused: bool = False
        self.finished_once: bool = False
        self._dirty: bool = True
        self.default_blend = max(0.0, float(default_blend))
        self._event_sink = event_sink
        self._blend_from_texture: Optional[optional_arcade.arcade.Texture] = None
        self._blend_duration: float = 0.0
        self._blend_elapsed: float = 0.0
        self._blend_cache: dict[tuple[int, int, int], optional_arcade.arcade.Texture] = {}
        self._loop_counts: dict[str, int] = {self.current_state: 0}
        self._state_hold_timer: float = 0.0

        self._apply_frame(force=True)
        self._handle_frame_events(self.clips[self.current_state], self.frame_cursor)

    def available_states(self) -> List[str]:
        return sorted(self.clips.keys())

    def set_state(
        self,
        state: str,
        *,
        restart: bool = False,
        force: bool = False,
        blend: Optional[float] = None,
    ) -> bool:
        if state not in self.clips:
            return False
        if not force and state == self.current_state and not restart:
            return False

        previous = self.current_state
        previous_texture = self.current_frame_texture()
        self._state_hold_timer = 0.0
        self.current_state = state
        self.frame_cursor = 0
        self.elapsed = 0.0
        self.paused = False
        self.finished_once = False
        self._dirty = True
        clip = self.clips[state]
        self._loop_counts[state] = 0
        blend_duration = self._resolve_blend_duration(blend, clip)
        if blend_duration > 0 and previous_texture is not None:
            self._start_blend(previous_texture, blend_duration)
        else:
            self._clear_blend()
        self._apply_frame(force=True)
        self._handle_frame_events(clip, self.frame_cursor)
        if self.debug and previous != state:
            self._log(f"state {previous} -> {state}")
        return True

    def update(self, dt: float) -> None:
        clip = self.clips.get(self.current_state)
        if clip is None or not clip.frames:
            return

        self._advance_blend(dt)

        if self._dirty or self._blend_from_texture is not None:
            self._apply_frame()

        if self._state_hold_timer > 0.0:
            self._state_hold_timer = max(0.0, self._state_hold_timer - max(0.0, dt))
            return

        if self.paused or clip.fps <= 0 or len(clip.frames) == 1:
            return

        frame_time = 1.0 / max(clip.fps, 0.0001)
        self.elapsed += max(0.0, dt)
        while self.elapsed >= frame_time and not self.paused:
            self.elapsed -= frame_time
            self.frame_cursor += 1
            if self.frame_cursor >= len(clip.frames):
                if clip.loop:
                    self.frame_cursor = 0
                    self._loop_counts[self.current_state] = self._loop_counts.get(self.current_state, 0) + 1
                else:
                    self.frame_cursor = len(clip.frames) - 1
                    self.paused = True
                    self.finished_once = True
                    if clip.hold_duration > 0:
                        self._state_hold_timer = max(self._state_hold_timer, clip.hold_duration)
            self._dirty = True
            self._handle_frame_events(clip, self.frame_cursor)
            if self.paused:
                break

        if self._dirty:
            self._apply_frame()

    def current_frame_texture(self) -> Optional[optional_arcade.arcade.Texture]:
        clip = self.clips.get(self.current_state)
        if clip is None or not clip.frames:
            return None
        frame_index = clip.frames[self.frame_cursor]
        if 0 <= frame_index < self.sheet.frame_count():
            return self.sheet.frames[frame_index]
        return None

    def _apply_frame(self, *, force: bool = False) -> None:
        texture = self.current_frame_texture()
        if texture is None:
            return
        texture = self._apply_blend(texture)
        if force or self.sprite.texture is not texture:
            self.sprite.texture = texture
        self._dirty = False

    def _log(self, message: str) -> None:
        name = getattr(self.sprite, "mesh_name", "<unnamed>")
        print(f"[Mesh][Animation] {name}: {message}")  # noqa: T201

    def _advance_blend(self, dt: float) -> None:
        if self._blend_from_texture is None or self._blend_duration <= 0.0:
            return
        self._blend_elapsed = min(self._blend_duration, self._blend_elapsed + max(0.0, dt))
        self._dirty = True
        if self._blend_elapsed >= self._blend_duration:
            self._clear_blend()

    def _start_blend(self, from_texture: optional_arcade.arcade.Texture, duration: float) -> None:
        self._blend_from_texture = from_texture
        self._blend_duration = max(0.0, float(duration))
        self._blend_elapsed = 0.0
        self._dirty = True

    def _clear_blend(self) -> None:
        self._blend_from_texture = None
        self._blend_duration = 0.0
        self._blend_elapsed = 0.0

    def _apply_blend(self, base_texture: optional_arcade.arcade.Texture) -> optional_arcade.arcade.Texture:
        if self._blend_from_texture is None or self._blend_duration <= 0.0:
            return base_texture

        progress = 0.0 if self._blend_duration == 0 else self._blend_elapsed / self._blend_duration
        progress = min(1.0, max(0.0, progress))
        if progress <= 0.0:
            return self._blend_from_texture

        blended = self._blend_textures(self._blend_from_texture, base_texture, progress)
        if progress >= 0.999 or blended is None:
            self._clear_blend()
            return base_texture
        return blended

    def _blend_textures(
        self,
        texture_a: optional_arcade.arcade.Texture,
        texture_b: optional_arcade.arcade.Texture,
        alpha: float,
    ) -> Optional[optional_arcade.arcade.Texture]:
        alpha = min(1.0, max(0.0, alpha))
        cache_key = (id(texture_a), id(texture_b), int(alpha * 1000))
        cached = self._blend_cache.get(cache_key)
        if cached is not None:
            return cached

        image_a = self._texture_image(texture_a)
        image_b = self._texture_image(texture_b)
        if image_a is None or image_b is None:
            return texture_b if alpha >= 0.5 else texture_a
        if image_a.size != image_b.size:
            image_b = image_b.resize(image_a.size)

        blended_image = Image.blend(image_a, image_b, alpha)
        name = f"mesh_anim_blend_{id(self)}_{cache_key[2]}_{len(self._blend_cache)}"
        blended_texture = optional_arcade.arcade.Texture(name=name, image=blended_image)
        self._blend_cache[cache_key] = blended_texture
        if len(self._blend_cache) > 128:
            stale_key = next(iter(self._blend_cache))
            self._blend_cache.pop(stale_key, None)
        return blended_texture

    @staticmethod
    def _texture_image(texture: optional_arcade.arcade.Texture) -> Optional[Image.Image]:
        image = getattr(texture, "image", None)
        if image is None:
            getter = getattr(texture, "get_pil_image", None)
            if callable(getter):  # pragma: no cover - defensive
                image = getter()
        if image is None:
            return None
        if image.mode != "RGBA":
            return image.convert("RGBA")
        
        if TYPE_CHECKING:
            return cast(PILImageClass, image)
        return image


    def _handle_frame_events(self, clip: AnimationClip, frame_index: int) -> None:
        if not clip.events:
            return
        for marker in clip.events:
            if marker.frame == frame_index:
                self._emit_animation_event(marker.label, frame_index, marker.payload)

    def _emit_animation_event(
        self,
        label: str,
        frame_index: int,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not label or self._event_sink is None:
            return
        data: Dict[str, Any] = {
            "entity": getattr(self.sprite, "mesh_name", "<unnamed>"),
            "state": self.current_state,
            "event": label,
            "frame": frame_index,
            "loop": self._loop_counts.get(self.current_state, 0),
        }
        if payload:
            for key, value in payload.items():
                if key in data:
                    continue
                data[key] = value
        try:
            self._event_sink(data)
        except Exception as exc:  # noqa: BLE001
            if self.debug:
                self._log(f"event sink failure: {exc}")

    def _resolve_blend_duration(self, override: Optional[float], clip: AnimationClip) -> float:
        if clip.transition_mode == "snap":
            return 0.0
        if override is not None:
            return max(0.0, float(override))
        if clip.blend > 0:
            return clip.blend
        return self.default_blend


class AnimationFactory:
    """High-level helper that wires animation data on sprites."""

    def __init__(self, assets: AssetManager) -> None:
        self.sheets = SpriteSheetCache(assets)

    def build_for_entity(
        self,
        sprite: optional_arcade.arcade.Sprite,
        entity_data: dict[str, Any],
        *,
        debug: bool = False,
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Optional[AnimationPlayer]:
        sprite_sheet_data = entity_data.get("sprite_sheet")
        animations_data = entity_data.get("animations")
        if not self._can_build(sprite_sheet_data, animations_data):
            return None

        if not isinstance(animations_data, dict):
            animations_data = {}

        spec = self._build_spec(entity_data)
        if spec is None:
            return None

        sheet = self.sheets.get_or_build(spec)
        if sheet is None or sheet.frame_count() == 0:
            return None

        default_fps = self._coerce_fps(entity_data.get("animation_frame_rate"), 8.0)
        clips = self._build_clips(
            animations_data,
            sheet,
            default_fps=default_fps,
            entity_name=str(entity_data.get("name") or getattr(sprite, "mesh_name", "<unnamed>")),
        )
        if not clips:
            return None

        default_state = (
            entity_data.get("default_animation")
            or entity_data.get("animation_state")
            or next(iter(clips))
        )

        default_blend = self._coerce_positive_float(entity_data.get("animation_blend", 0.0), 0.0)

        player = AnimationPlayer(
            sprite,
            sheet,
            clips,
            default_state=default_state,
            debug=debug,
            default_blend=default_blend,
            event_sink=event_sink,
        )
        sprite.mesh_animator = player
        self._log_animator_summary(player, entity_data)
        return player

    def _can_build(self, sprite_sheet_data: Any, animations_data: Any) -> bool:
        if not isinstance(sprite_sheet_data, dict):
            return False
        if not isinstance(animations_data, dict) or not animations_data:
            return False
        # New format requires dict entries with "frames" or list of ints.
        for value in animations_data.values():
            if isinstance(value, dict) and "frames" in value:
                return True
            if isinstance(value, list) and value and all(isinstance(item, int) for item in value):
                return True
        return False

    def _build_spec(self, entity_data: dict[str, Any]) -> Optional[SpriteSheetSpec]:
        sprite_path = entity_data.get("sprite")
        sheet = entity_data.get("sprite_sheet") or {}
        if not isinstance(sheet, dict) or not isinstance(sprite_path, str):
            return None

        frame_w = self._optional_int(sheet.get("frame_width"))
        frame_h = self._optional_int(sheet.get("frame_height"))
        if frame_w is None or frame_h is None:
            print(
                "[Mesh][Animation] WARNING: sprite_sheet requires positive frame_width/frame_height",
                sheet,
            )
            return None

        try:
            return SpriteSheetSpec(
                path=str(sprite_path),
                frame_width=frame_w,
                frame_height=frame_h,
                margin=int(sheet.get("margin", 0) or 0),
                spacing=int(sheet.get("spacing", 0) or 0),
                columns=self._optional_int(sheet.get("columns")),
                rows=self._optional_int(sheet.get("rows")),
            )
        except (TypeError, ValueError):
            print("[Mesh][Animation] WARNING: Invalid sprite_sheet configuration", sheet)  # noqa: T201
            return None

    def _build_clips(
        self,
        animations_data: dict[str, Any],
        sheet: SpriteSheet,
        *,
        default_fps: float,
        entity_name: str,
    ) -> Dict[str, AnimationClip]:
        clips: Dict[str, AnimationClip] = {}
        max_index = sheet.frame_count()
        for name, payload in animations_data.items():
            frames_raw: Iterable[Any]
            fps_value: Any = 8.0
            loop_value: Any = True
            blend_value: Any = None
            events_value: Any = None
            transition_mode = "blend"
            hold_duration = 0.0
            if isinstance(payload, dict):
                frames_raw = payload.get("frames", [])
                fps_value = payload.get("fps", payload.get("frame_rate", 8.0))
                loop_value = payload.get("loop", True)
                blend_value = payload.get("blend")
                events_value = payload.get("events")
                transition_data = payload.get("transition")
                transition_mode, hold_duration = self._parse_transition_config(transition_data)
                if transition_mode == "blend":
                    fallback_mode = payload.get("transition_mode")
                    if isinstance(fallback_mode, str):
                        transition_mode = fallback_mode.lower()
                if hold_duration <= 0:
                    hold_value = payload.get("hold")
                    if hold_value is not None:
                        hold_duration = self._coerce_positive_float(hold_value, 0.0)
            elif isinstance(payload, list):
                frames_raw = payload
            else:
                continue

            frames: List[int] = []
            dropped: List[Any] = []
            for value in frames_raw:
                idx = self._coerce_int(value)
                if idx is None or idx < 0 or idx >= max_index:
                    dropped.append(value)
                    continue
                frames.append(idx)

            if dropped:
                print(
                    f"[Mesh][Animation] WARNING: Dropped frame index(es) {dropped} from '{name}' "
                    f"for entity '{entity_name}' (sheet frames: {max_index})",
                )

            if not frames:
                print(f"[Mesh][Animation] WARNING: Animation '{name}' has no valid frames")  # noqa: T201
                continue

            fps = self._coerce_fps(fps_value, default_fps)
            loop = bool(loop_value)
            blend = self._coerce_positive_float(blend_value, 0.0)
            events = self._parse_clip_events(
                events_value,
                entity_name=entity_name,
                clip_name=name,
                max_frame=len(frames) - 1,
            )
            clips[name] = AnimationClip(
                name=name,
                frames=frames,
                fps=fps,
                loop=loop,
                blend=blend,
                events=tuple(events),
                transition_mode="snap" if transition_mode == "snap" else "blend",
                hold_duration=hold_duration,
            )
        return clips

    def _parse_transition_config(self, payload: Any) -> tuple[str, float]:
        if payload is None:
            return ("blend", 0.0)
        if isinstance(payload, str):
            mode = payload.strip().lower()
            return ("snap" if mode == "snap" else "blend", 0.0)
        if isinstance(payload, (int, float)):
            return ("blend", self._coerce_positive_float(payload, 0.0))
        if not isinstance(payload, dict):
            return ("blend", 0.0)
        mode_raw = payload.get("mode")
        mode = str(mode_raw).lower() if isinstance(mode_raw, str) else "blend"
        if mode not in {"blend", "snap"}:
            mode = "blend"
        hold_value = payload.get("hold") or payload.get("hold_duration")
        hold = self._coerce_positive_float(hold_value, 0.0)
        return (mode, hold)

    def _log_animator_summary(self, player: AnimationPlayer, entity_data: dict[str, Any]) -> None:
        entity_name = entity_data.get("name") or getattr(player.sprite, "mesh_name", "<unnamed>")
        spec = player.sheet.spec
        states = ", ".join(player.available_states())
        print(
            f"[Mesh][Animation] Built '{entity_name}' @ {spec.path} "
            f"[{spec.frame_width}x{spec.frame_height}] states: {states}"
        )

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            parsed = int(value)
            return parsed if parsed > 0 else None
        except (TypeError, ValueError):
            return None

    def _parse_clip_events(
        self,
        raw_events: Any,
        *,
        entity_name: str,
        clip_name: str,
        max_frame: int,
    ) -> List[AnimationEventMarker]:
        markers: List[AnimationEventMarker] = []
        if raw_events is None:
            return markers
        if not isinstance(raw_events, list):
            print(
                f"[Mesh][Animation] WARNING: events for '{clip_name}' on '{entity_name}' must be an array",
            )
            return markers
        for index, entry in enumerate(raw_events):
            frame_value: Any
            label_value: Any
            payload_data: Dict[str, Any] = {}
            if isinstance(entry, dict):
                frame_value = entry.get("frame")
                label_value = entry.get("label")
                for key, value in entry.items():
                    if key in {"frame", "label"}:
                        continue
                    payload_data[key] = value
            elif isinstance(entry, Sequence) and len(entry) >= 2:
                frame_value, label_value = entry[0], entry[1]
            else:
                print(
                    f"[Mesh][Animation] WARNING: events[{index}] for '{clip_name}' must be an object or [frame,label] pair",
                )
                continue
            frame_index = self._coerce_int(frame_value)
            if frame_index is None:
                print(
                    f"[Mesh][Animation] WARNING: events[{index}] for '{clip_name}' has invalid frame '{frame_value}'",
                )
                continue
            if frame_index < 0 or (max_frame >= 0 and frame_index > max_frame):
                print(
                    f"[Mesh][Animation] WARNING: events[{index}] frame {frame_index} is outside clip '{clip_name}'",
                )
                continue
            if not isinstance(label_value, str) or not label_value.strip():
                print(
                    f"[Mesh][Animation] WARNING: events[{index}] for '{clip_name}' requires a non-empty label",
                )
                continue
            markers.append(
                AnimationEventMarker(
                    frame=frame_index,
                    label=label_value.strip(),
                    payload=payload_data or None,
                ),
            )
        return markers

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_positive_float(value: Any, default: float = 0.0) -> float:
        if value is None:
            return max(0.0, float(default))
        try:
            parsed = float(value)
            return max(0.0, parsed)
        except (TypeError, ValueError):
            return max(0.0, float(default))

    @staticmethod
    def _coerce_fps(value: Any, fallback: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return float(fallback)
        return float(parsed)
