# mypy: ignore-errors
from __future__ import annotations

from typing import Iterable, Sequence


def update(self, delta_time: float) -> None:
    self.updater.handle_update(delta_time, self)


def _layer_update_order(self) -> list[str]:
    preferred = ["background", "entities", "foreground"]
    ordered: list[str] = []
    seen: set[str] = set()
    for name in preferred:
        if name in self.layers:
            ordered.append(name)
            seen.add(name)
    for name in self.layers.keys():
        if name not in seen:
            ordered.append(name)
    return ordered


def _iter_layered_sprites(self) -> Iterable[object]:
    for layer_name in self._layer_update_order():
        layer = self.layers.get(layer_name)
        if layer is None:
            continue
        for sprite in layer:
            yield sprite


def _deliver_events_to_behaviours(self, events: Sequence[object]) -> None:
    for event in events:
        for sprite in self._iter_layered_sprites():
            behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
            if not behaviours:
                continue
            for behaviour in behaviours:
                on_event = getattr(behaviour, "on_event", None)
                if not callable(on_event):
                    continue
                try:
                    on_event(event)
                except Exception as exc:  # noqa: BLE001  # REASON: behaviour event delivery should not abort the frame outside strict mode
                    if getattr(self.window, "strict_mode", False):
                        raise
                    entity_name = getattr(sprite, "mesh_name", "<unnamed>")
                    print(
                        f"[Mesh][Events] ERROR delivering '{event.type}' to"
                        f" {behaviour} on {entity_name}: {exc}",
                    )


def _pre_update_behaviour_stage(self, delta_time: float) -> None:
    for sprite in self._iter_layered_sprites():
        if getattr(sprite, "frozen", False):
            continue
        behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
        for behaviour in behaviours:
            pre = getattr(behaviour, "pre_update", None)
            if callable(pre):
                pre(delta_time)


def _update_behaviour_stage(self, delta_time: float) -> None:
    for sprite in self._iter_layered_sprites():
        if getattr(sprite, "frozen", False):
            continue
        for behaviour in getattr(sprite, "mesh_behaviours_runtime", []):
            behaviour.update(delta_time)


def _update_movement_stage(self, delta_time: float) -> None:
    for layer_name in self._layer_update_order():
        layer = self.layers.get(layer_name)
        if layer is not None:
            for sprite in layer:
                if not getattr(sprite, "frozen", False):
                    sprite.update()


def _late_update_stage(self, delta_time: float) -> None:
    for sprite in self._iter_layered_sprites():
        if getattr(sprite, "frozen", False):
            continue
        behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
        for behaviour in behaviours:
            late = getattr(behaviour, "late_update", None)
            if callable(late):
                late(delta_time)


def bind_runtime_hooks_methods(cls) -> None:
    cls._layer_update_order = _layer_update_order
    cls._iter_layered_sprites = _iter_layered_sprites
    cls._deliver_events_to_behaviours = _deliver_events_to_behaviours
    cls._pre_update_behaviour_stage = _pre_update_behaviour_stage
    cls._update_behaviour_stage = _update_behaviour_stage
    cls._update_movement_stage = _update_movement_stage
    cls._late_update_stage = _late_update_stage
    cls.update = update
