"""Lightweight engine self-checks for behaviours, scenes, and worlds."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, cast
import engine.optional_arcade as optional_arcade

from .behaviours.registry import BEHAVIOUR_REGISTRY
from .scene_loader import SceneLoader
from .world_controller import WorldController


@dataclass(slots=True)
class SelfTestResult:
    """Represents the outcome of a single self-test probe."""

    name: str
    ok: bool
    message: str | None = None
    warnings: list[str] = field(default_factory=list)


class _DummyEventBus:
    """Minimal event bus stub to satisfy behaviours that subscribe/emit."""

    def subscribe(self, *_args: Any, **_kwargs: Any) -> Any:
        return ("sub", _args, _kwargs)

    def unsubscribe(self, _token: Any) -> None:  # pragma: no cover - trivial
        return

    def emit(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - trivial
        return


class _DummyGameState:
    """Tiny game state stub with flag/counter accessors."""

    def get_flag(self, _name: str, default: bool = False) -> bool:
        return default

    def get_counter(self, _name: str, default: int = 0) -> int:
        return default

    def get_var(self, _name: str, default: Any = None) -> Any:
        return default

    def set_var(self, _name: str, _value: Any) -> None:  # pragma: no cover - trivial
        return


class _DummySceneController:
    """Stubbed scene controller with minimal state."""

    def __init__(self) -> None:
        self._loaded_scene_data: dict[str, Any] = {}
        self.all_sprites: optional_arcade.arcade.SpriteList = optional_arcade.arcade.SpriteList()

    def queue_scene_change(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - trivial
        return


class _DummyWindow:
    """Small stand-in for the GameWindow used by behaviour smoke tests."""

    def __init__(self) -> None:
        self.event_bus = _DummyEventBus()
        self.game_state_controller = _DummyGameState()
        self.scene_controller = _DummySceneController()
        self.lighting = None
        self.day_night_controller = None
        self.ui_controller = None
        self.input = _DummyInput()

    def __getattr__(self, _name: str) -> Any:  # pragma: no cover - defensive
        return None

    def move_entity_with_collision(self, *_args: Any, **_kwargs: Any) -> None:
        return

    def get_pressed_keys(self) -> list[int]:
        return []


class _DummyInput:
    """Minimal InputManager stub."""

    def get_axis(self, *_args: Any, **_kwargs: Any) -> float:
        return 0.0

    def is_action_down(self, *_args: Any, **_kwargs: Any) -> bool:
        return False

    def get_action_duration(self, *_args: Any, **_kwargs: Any) -> float:
        return 0.0

    def set_text_buffer(self, *_args: Any, **_kwargs: Any) -> None:
        return


class _DummyEntity(optional_arcade.arcade.Sprite):
    """Simple sprite-like stub to host behaviours."""

    def __init__(self) -> None:
        super().__init__()
        self.center_x = 0.0
        self.center_y = 0.0
        self.visible = True
        self.behaviours: list[Any] = []
        self.mesh_behaviours_runtime: list[Any] = []
        self.mesh_entity_data: dict[str, Any] = {}
        self.change_x: float = 0.0
        self.change_y: float = 0.0


class SelfTestManager:
    """Aggregates simple smoke tests for engine subsystems."""

    def __init__(
        self,
        window: Any | None = None,
        behaviour_registry: Dict[str, Any] | None = None,
    ) -> None:
        self.window = window or _DummyWindow()
        self.behaviour_registry = behaviour_registry or BEHAVIOUR_REGISTRY
        self._scene_loader = SceneLoader()
        self._wrap_collision_for_selftest()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def run_all(self) -> list[SelfTestResult]:
        """Run all available self-tests and return results."""
        results: list[SelfTestResult] = []
        results.extend(self._test_behaviours())
        results.extend(self._test_scenes())
        results.extend(self._test_worlds())
        results.extend(self._test_cutscenes())
        return results

    def summary(self, results: list[SelfTestResult]) -> str:
        """Produce a short human-readable summary."""
        total = len(results)
        failed = [r for r in results if not r.ok]
        warning_count = sum(len(r.warnings) for r in results)
        lines = [
            f"[SelfTest] {total - len(failed)}/{total} checks passed. warnings={warning_count}",
        ]
        for result in failed:
            if result.message:
                lines.append(f"  - {result.name}: {result.message}")
            else:
                lines.append(f"  - {result.name}: failed")
        if warning_count:
            for result in results:
                if not result.warnings:
                    continue
                preview = result.warnings[:3]
                for warn in preview:
                    lines.append(f"  ! {result.name}: {warn}")
                if len(result.warnings) > len(preview):
                    lines.append(f"  ! {result.name}: ... (+{len(result.warnings) - len(preview)} more)")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _test_behaviours(self) -> list[SelfTestResult]:
        """Instantiate every registered behaviour with a dummy entity."""
        results: list[SelfTestResult] = []
        for name, cls in self.behaviour_registry.items():
            test_name = f"behaviour:{name}"
            try:
                entity = _DummyEntity()
                behaviour = cast(Any, cls)(entity=entity, window=self.window, **{})
                if hasattr(behaviour, "on_init"):
                    behaviour.on_init()
                if hasattr(behaviour, "update"):
                    behaviour.update(0.016)
                results.append(SelfTestResult(test_name, True))
            except Exception as exc:  # noqa: BLE001
                results.append(SelfTestResult(test_name, False, message=str(exc)))
        return results

    def _wrap_collision_for_selftest(self) -> None:
        """Allow behaviours that call optional_arcade.arcade collision helpers with plain lists."""
        if getattr(optional_arcade.arcade, "_mesh_selftest_collision_wrapped", False):
            return
        original = optional_arcade.arcade.check_for_collision_with_list

        def _wrapper(sprite: optional_arcade.arcade.Sprite, sprite_list: Any):
            if not isinstance(sprite_list, optional_arcade.arcade.SpriteList):
                tmp: optional_arcade.arcade.SpriteList = optional_arcade.arcade.SpriteList()
                tmp.extend(sprite_list or [])
                sprite_list = tmp
            return original(sprite, sprite_list)

        optional_arcade.arcade.check_for_collision_with_list = _wrapper
        setattr(optional_arcade.arcade, "_mesh_selftest_collision_wrapped", True)

    def _list_scene_paths(self) -> Iterable[Path]:
        scenes_root = Path("scenes")
        if scenes_root.exists():
            yield from sorted(scenes_root.glob("*.json"), key=lambda p: p.name)

    def _test_scenes(self) -> list[SelfTestResult]:
        """Validate all known scenes via SceneLoader."""
        results: list[SelfTestResult] = []
        for scene_path in self._list_scene_paths():
            label = f"scene:{scene_path}"
            try:
                report = self._scene_loader.validate_scene_file(str(scene_path))
                if report.errors:
                    results.append(
                        SelfTestResult(label, False, message="; ".join(report.errors[:3]), warnings=report.warnings),
                    )
                else:
                    warnings = list(report.warnings)
                    # Promote behaviour validation details about unknown fields / missing required params as warnings
                    for entity, behaviours in report.behaviour_details.items():
                        for beh, messages in behaviours.items():
                            for msg in messages:
                                if "UNKNOWN" in msg or "missing required" in msg:
                                    warnings.append(f"{entity} {beh}: {msg}")
                    results.append(SelfTestResult(label, True, warnings=warnings))
            except Exception as exc:  # noqa: BLE001
                results.append(SelfTestResult(label, False, message=str(exc)))
        return results

    def _list_world_paths(self) -> Iterable[Path]:
        default_path = Path("worlds/main_world.json")
        if default_path.exists():
            yield default_path
        worlds_root = Path("worlds")
        if worlds_root.exists():
            for candidate in sorted(worlds_root.glob("*.json"), key=lambda p: p.name):
                if candidate == default_path:
                    continue
                yield candidate

    def _test_worlds(self) -> list[SelfTestResult]:
        """Load configured world files to catch JSON/structural errors."""
        results: list[SelfTestResult] = []
        for world_path in self._list_world_paths():
            label = f"world:{world_path}"
            try:
                with world_path.open("r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                WorldController(raw)
                results.append(SelfTestResult(label, True))
            except Exception as exc:  # noqa: BLE001
                results.append(SelfTestResult(label, False, message=str(exc)))
        return results

    def _list_cutscene_paths(self) -> Iterable[Path]:
        default = Path("cutscenes.json")
        if default.exists():
            yield default
        cs_dir = Path("cutscenes")
        if cs_dir.exists():
            yield from sorted(cs_dir.glob("*.json"), key=lambda p: p.name)

    def _test_cutscenes(self) -> list[SelfTestResult]:
        """Validate cutscene definition files."""
        results: list[SelfTestResult] = []
        for path in self._list_cutscene_paths():
            label = f"cutscene:{path}"
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    payload = {"cutscenes": raw}
                elif isinstance(raw, dict):
                    payload = raw
                else:
                    raise ValueError("Cutscene root must be object or array")
                cutscenes = payload.get("cutscenes") or []
                warnings: list[str] = []
                if not isinstance(cutscenes, list):
                    raise ValueError("'cutscenes' must be an array")
                for entry in cutscenes:
                    if not isinstance(entry, dict):
                        raise ValueError("cutscene entries must be objects")
                    cid = entry.get("id")
                    if not cid or not isinstance(cid, str):
                        raise ValueError("cutscene missing string id")
                    steps = entry.get("steps") or []
                    if not isinstance(steps, list):
                        raise ValueError(f"cutscene '{cid}' steps must be a list")
                    for idx, step in enumerate(steps):
                        if not isinstance(step, dict):
                            raise ValueError(f"cutscene '{cid}' step {idx} must be an object")
                        if "type" not in step:
                            warnings.append(f"cutscene '{cid}' step {idx} missing type")
                results.append(SelfTestResult(label, True, warnings=warnings))
            except Exception as exc:  # noqa: BLE001
                results.append(SelfTestResult(label, False, message=str(exc)))
        return results
