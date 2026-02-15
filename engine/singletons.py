from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Callable

from engine.gameplay_event_bus import GameplayEventBus
from engine.rng_service import RNGService, RNGStream, get_rng, rng_service


@dataclass(frozen=True, slots=True)
class ServiceRegistry:
    """Centralized access point for module-level mutable singletons."""

    rng_service: RNGService
    get_rng_stream: Callable[[str | None], RNGStream]
    gameplay_event_bus_factory: Callable[[], GameplayEventBus]
    log_once_seen: set[str]
    log_once_counts: dict[str, int]

    def create_gameplay_event_bus(self) -> GameplayEventBus:
        return self.gameplay_event_bus_factory()

    def snapshot_singletons(self) -> dict[str, int | bool]:
        modules = _load_singleton_modules()
        action_registry = modules["engine.action_runtime.registry"]
        editor_input = modules["engine.editor_runtime.input"]
        behaviours_pkg = modules["engine.behaviours"]
        encounter_sets = modules["engine.encounter_sets"]

        warned: set[str] | object = getattr(editor_input, "_shortcut_conflicts_warned", set())
        actions = getattr(action_registry, "_ACTIONS", None)
        required = getattr(action_registry, "_REQUIRED", None)
        builtins_loaded = bool(getattr(behaviours_pkg, "_BUILTINS_LOADED", False))
        theme_manager = getattr(encounter_sets, "_THEME_MANAGER", None)

        return {
            "rng_stream_count": len(getattr(self.rng_service, "_streams", {})),
            "editor_shortcut_conflicts_warned": len(warned) if isinstance(warned, set) else 0,
            "action_registry_cached_actions": 0 if actions is None else len(actions),
            "action_registry_cached_required": 0 if required is None else len(required),
            "behaviours_builtins_loaded": builtins_loaded,
            "encounter_theme_manager_initialized": bool(theme_manager is not None),
            "log_once_seen": len(self.log_once_seen),
            "log_once_keys": len(self.log_once_counts),
        }

    def reset_mutable_singletons(self, *, seed: int | None = None) -> None:
        modules = _load_singleton_modules()
        action_registry = modules["engine.action_runtime.registry"]
        editor_input = modules["engine.editor_runtime.input"]
        behaviours_pkg = modules["engine.behaviours"]
        encounter_sets = modules["engine.encounter_sets"]

        # RNG service is globally shared and must be reset first for deterministic tests.
        self.rng_service.reset()
        if seed is not None:
            self.rng_service.seed(int(seed))

        setattr(action_registry, "_ACTIONS", None)
        setattr(action_registry, "_REQUIRED", None)

        warned = getattr(editor_input, "_shortcut_conflicts_warned", None)
        if isinstance(warned, set):
            warned.clear()

        setattr(behaviours_pkg, "_BUILTINS_LOADED", False)
        setattr(encounter_sets, "_THEME_MANAGER", None)
        self.log_once_seen.clear()
        self.log_once_counts.clear()


_REGISTRY: ServiceRegistry | None = None


def _load_singleton_modules() -> dict[str, ModuleType]:
    import engine.action_runtime.registry as action_registry
    import engine.editor_runtime.input as editor_input
    import engine.behaviours as behaviours_pkg
    import engine.encounter_sets as encounter_sets

    return {
        "engine.action_runtime.registry": action_registry,
        "engine.editor_runtime.input": editor_input,
        "engine.behaviours": behaviours_pkg,
        "engine.encounter_sets": encounter_sets,
    }


def _build_registry() -> ServiceRegistry:
    return ServiceRegistry(
        rng_service=rng_service,
        get_rng_stream=get_rng,
        gameplay_event_bus_factory=GameplayEventBus,
        log_once_seen=set(),
        log_once_counts={},
    )


def get_registry() -> ServiceRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


def reset_registry_for_tests(*, seed: int | None = None) -> ServiceRegistry:
    global _REGISTRY
    _REGISTRY = _build_registry()
    _REGISTRY.reset_mutable_singletons(seed=seed)
    return _REGISTRY
