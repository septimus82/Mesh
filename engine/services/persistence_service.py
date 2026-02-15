from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from engine.diagnostics import Diagnostic, DiagnosticLevel, diagnostics_to_text
from engine.game_runtime.undo import UndoFrame
from engine.log_utils import format_kv, get_logger, normalize_path


class SceneFlowRuntime(Protocol):
    def load_scene(self, window: Any, scene_path: str) -> dict[str, Any]: ...
    def request_scene_reload(self, window: Any, *, clear_assets: bool = False) -> None: ...
    def request_reload_current_scene(self, window: Any, *, clear_assets: bool = False) -> None: ...
    def request_scene_change(self, window: Any, scene_path: str) -> None: ...
    def queue_scene_change(self, window: Any, scene_path: str, *, spawn_id: str | None = None) -> None: ...
    def reload_scene(self, window: Any, new_path: str | None = None) -> bool: ...
    def reload_current_scene(self, window: Any) -> None: ...
    def warp_to_scene(self, window: Any, scene_path: str) -> None: ...


class SceneOpsRuntime(Protocol):
    def mark_scene_dirty(self, window: Any, reason: str) -> None: ...
    def record_recent_scene(self, window: Any, scene_path: str) -> None: ...
    def get_recent_scenes(self, window: Any) -> list[str]: ...
    def clear_scene_dirty(self, window: Any) -> None: ...
    def reload_scene_from_disk(self, window: Any) -> bool: ...
    def persist_scene_to_disk(self, window: Any) -> Any: ...
    def save_scene_as(self, window: Any, new_scene_path: str) -> Any: ...


class UndoRuntime(Protocol):
    def undo_enabled(self, window: Any) -> bool: ...
    def snapshot_current_authored_scene_payload(self, window: Any) -> UndoFrame | None: ...
    def push_undo_frame(self, window: Any, reason: str) -> bool: ...
    def undo(self, window: Any) -> bool: ...
    def redo(self, window: Any) -> bool: ...


@dataclass(frozen=True, slots=True)
class PersistenceService:
    """Scene flow + persistence + undo orchestration facade."""

    scene_flow: SceneFlowRuntime
    scene_ops: SceneOpsRuntime
    undo_runtime: UndoRuntime
    strict: bool = True

    def _handle_runtime_error(
        self,
        *,
        op: str,
        exc: Exception,
        context: dict[str, Any] | None = None,
    ) -> None:
        logger = get_logger("engine.services.persistence_service")
        ctx = dict(context or {})
        if "scene_path" in ctx:
            ctx["scene_path"] = normalize_path(str(ctx["scene_path"]))
        diag = Diagnostic(
            level=DiagnosticLevel.ERROR,
            code="persistence.runtime_error",
            message=f"{op} failed: {type(exc).__name__}: {exc}",
            context=ctx,
            hint="Fix the referenced content path or disable strict mode for best-effort execution.",
        )
        logger.error("%s", diagnostics_to_text((diag,)).strip())
        logger.debug("context %s", format_kv(ctx))

    def load_scene(self, window: Any, scene_path: str) -> dict[str, Any]:
        try:
            return self.scene_flow.load_scene(window, str(scene_path))
        except Exception as exc:  # noqa: BLE001
            self._handle_runtime_error(op="load_scene", exc=exc, context={"scene_path": scene_path})
            if self.strict:
                raise
            return {}

    def request_scene_reload(self, window: Any, *, clear_assets: bool = False) -> None:
        try:
            self.scene_flow.request_scene_reload(window, clear_assets=bool(clear_assets))
        except Exception as exc:  # noqa: BLE001
            self._handle_runtime_error(op="request_scene_reload", exc=exc, context={})
            if self.strict:
                raise

    def request_reload_current_scene(self, window: Any, *, clear_assets: bool = False) -> None:
        try:
            self.scene_flow.request_reload_current_scene(window, clear_assets=bool(clear_assets))
        except Exception as exc:  # noqa: BLE001
            self._handle_runtime_error(op="request_reload_current_scene", exc=exc, context={})
            if self.strict:
                raise

    def request_scene_change(self, window: Any, scene_path: str) -> None:
        try:
            self.scene_flow.request_scene_change(window, str(scene_path))
        except Exception as exc:  # noqa: BLE001
            self._handle_runtime_error(op="request_scene_change", exc=exc, context={"scene_path": scene_path})
            if self.strict:
                raise

    def queue_scene_change(self, window: Any, scene_path: str, *, spawn_id: str | None = None) -> None:
        try:
            self.scene_flow.queue_scene_change(window, str(scene_path), spawn_id=spawn_id)
        except Exception as exc:  # noqa: BLE001
            self._handle_runtime_error(
                op="queue_scene_change",
                exc=exc,
                context={"scene_path": scene_path, "spawn_id": ("" if spawn_id is None else spawn_id)},
            )
            if self.strict:
                raise

    def mark_scene_dirty(self, window: Any, reason: str) -> None:
        self.scene_ops.mark_scene_dirty(window, str(reason))

    def record_recent_scene(self, window: Any, scene_path: str) -> None:
        self.scene_ops.record_recent_scene(window, str(scene_path))

    def get_recent_scenes(self, window: Any) -> list[str]:
        return self.scene_ops.get_recent_scenes(window)

    def clear_scene_dirty(self, window: Any) -> None:
        self.scene_ops.clear_scene_dirty(window)

    def undo_enabled(self, window: Any) -> bool:
        return bool(self.undo_runtime.undo_enabled(window))

    def snapshot_current_authored_scene_payload(self, window: Any) -> UndoFrame | None:
        frame = self.undo_runtime.snapshot_current_authored_scene_payload(window)
        if frame is None:
            return None
        return UndoFrame(
            scene_path=frame.scene_path,
            authored_scene_payload=frame.authored_scene_payload,
            dirty_counter=frame.dirty_counter,
            reason=frame.reason,
            ts_counter=frame.ts_counter,
        )

    def push_undo_frame(self, window: Any, reason: str) -> bool:
        return bool(self.undo_runtime.push_undo_frame(window, str(reason)))

    def undo(self, window: Any) -> bool:
        return bool(self.undo_runtime.undo(window))

    def redo(self, window: Any) -> bool:
        return bool(self.undo_runtime.redo(window))

    def reload_scene_from_disk(self, window: Any) -> bool:
        try:
            return bool(self.scene_ops.reload_scene_from_disk(window))
        except Exception as exc:  # noqa: BLE001
            self._handle_runtime_error(op="reload_scene_from_disk", exc=exc, context={})
            if self.strict:
                raise
            return False

    def persist_scene_to_disk(self, window: Any) -> Any:
        try:
            return self.scene_ops.persist_scene_to_disk(window)
        except Exception as exc:  # noqa: BLE001
            self._handle_runtime_error(op="persist_scene_to_disk", exc=exc, context={})
            if self.strict:
                raise
            return None

    def save_scene_as(self, window: Any, new_scene_path: str) -> Any:
        try:
            return self.scene_ops.save_scene_as(window, str(new_scene_path))
        except Exception as exc:  # noqa: BLE001
            self._handle_runtime_error(op="save_scene_as", exc=exc, context={"scene_path": new_scene_path})
            if self.strict:
                raise
            return None

    def reload_scene(self, window: Any, new_path: str | None = None) -> bool:
        try:
            return bool(self.scene_flow.reload_scene(window, new_path))
        except Exception as exc:  # noqa: BLE001
            self._handle_runtime_error(
                op="reload_scene",
                exc=exc,
                context={"scene_path": ("" if new_path is None else new_path)},
            )
            if self.strict:
                raise
            return False

    def reload_current_scene(self, window: Any) -> None:
        self.scene_flow.reload_current_scene(window)

    def warp_to_scene(self, window: Any, scene_path: str) -> None:
        self.scene_flow.warp_to_scene(window, str(scene_path))


def build_persistence_service(
    scene_flow: SceneFlowRuntime | None = None,
    scene_ops: SceneOpsRuntime | None = None,
    undo_runtime: UndoRuntime | None = None,
    *,
    strict: bool = True,
) -> PersistenceService:
    if scene_flow is None:
        from engine.game_runtime import scene_flow as scene_flow_runtime

        scene_flow = scene_flow_runtime
    if scene_ops is None:
        from engine.game_runtime import scene_ops as scene_ops_runtime

        scene_ops = scene_ops_runtime
    if undo_runtime is None:
        from engine.game_runtime import undo as undo_runtime_impl

        undo_runtime = undo_runtime_impl
    return PersistenceService(
        scene_flow=scene_flow,
        scene_ops=scene_ops,
        undo_runtime=undo_runtime,
        strict=bool(strict),
    )
