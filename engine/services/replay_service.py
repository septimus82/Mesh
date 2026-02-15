from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, cast

from engine.persistence_io import write_json_atomic


class DebugBundleLike(Protocol):
    def to_dict(self, *, deterministic: bool = False) -> dict[str, Any]: ...


class DebugBundleBuilder(Protocol):
    def __call__(
        self,
        window: Any | None,
        editor: Any | None = None,
        *,
        deterministic: bool = False,
    ) -> DebugBundleLike: ...


JsonWriter = Callable[[Path, Any], None]


@dataclass(frozen=True, slots=True)
class ReplayService:
    """Deterministic replay/debug bundle orchestration helpers."""

    build_debug_bundle: DebugBundleBuilder
    json_writer: JsonWriter

    def build_scene_snapshot(self, window: Any, *, compact: bool = False) -> dict[str, Any]:
        payload = window.scene_controller.build_scene_snapshot(compact=bool(compact))
        if isinstance(payload, dict):
            return cast(dict[str, Any], payload)
        raise TypeError("scene snapshot serializer must return a dict payload")

    def build_debug_bundle_payload(
        self,
        *,
        window: Any | None,
        editor: Any | None = None,
        deterministic: bool = False,
    ) -> dict[str, Any]:
        bundle = self.build_debug_bundle(
            window,
            editor,
            deterministic=bool(deterministic),
        )
        payload = bundle.to_dict(deterministic=bool(deterministic))
        if not isinstance(payload, dict):
            raise TypeError("debug bundle serializer must return a dict payload")
        if deterministic:
            render = payload.get("render")
            if isinstance(render, dict) and "plan_digest" in render:
                render["plan_digest"] = "deterministic"
        return payload

    def export_debug_bundle(
        self,
        *,
        window: Any | None,
        out_path: Path,
        editor: Any | None = None,
        deterministic: bool = False,
    ) -> dict[str, Any]:
        payload = self.build_debug_bundle_payload(
            window=window,
            editor=editor,
            deterministic=bool(deterministic),
        )
        self.json_writer(Path(out_path), payload)
        return payload


def _default_json_writer(path: Path, payload: Any) -> None:
    write_json_atomic(
        path,
        payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )


def build_replay_service(
    build_debug_bundle: DebugBundleBuilder | None = None,
    json_writer: JsonWriter | None = None,
) -> ReplayService:
    if build_debug_bundle is None:
        from engine.editor.debug_bundle import build_debug_bundle as build_debug_bundle_impl

        build_debug_bundle = build_debug_bundle_impl
    if json_writer is None:
        json_writer = _default_json_writer
    return ReplayService(
        build_debug_bundle=build_debug_bundle,
        json_writer=json_writer,
    )
