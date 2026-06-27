from __future__ import annotations

from pathlib import Path
from typing import Any

import engine.optional_arcade as optional_arcade
from engine.logging_tools import get_logger

logger = get_logger(__name__)


def maybe_start_live_bridge(editor: Any) -> None:
    if not _should_start_live_bridge(editor):
        return
    existing = getattr(editor, "live_bridge", None)
    if existing is not None:
        refresh = getattr(existing, "refresh_discovery", None)
        if callable(refresh):
            try:
                refresh()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[Editor][LiveBridge] Failed to refresh live session discovery: %s", exc)
        return
    try:
        from engine.editor.live_session_bridge import EditorLiveSessionBridge  # noqa: PLC0415

        workspace_root = _workspace_root_for_editor(editor)
        bridge = EditorLiveSessionBridge(editor, workspace_root)
        bridge.start()
        logger.info("[Editor][LiveBridge] Started live session bridge root=%s", workspace_root)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Editor][LiveBridge] Live session bridge unavailable: %s", exc, exc_info=True)
        if getattr(editor, "live_bridge", None) is not None:
            setattr(editor, "live_bridge", None)


def stop_live_bridge(editor: Any) -> None:
    bridge = getattr(editor, "live_bridge", None)
    if bridge is None:
        return
    try:
        stop = getattr(bridge, "stop", None)
        if callable(stop):
            stop()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Editor][LiveBridge] Failed to stop live session bridge: %s", exc, exc_info=True)
    finally:
        if getattr(editor, "live_bridge", None) is bridge:
            setattr(editor, "live_bridge", None)


def refresh_live_bridge_scene(editor: Any) -> None:
    bridge = getattr(editor, "live_bridge", None)
    if bridge is None:
        return
    refresh = getattr(bridge, "refresh_discovery", None)
    if not callable(refresh):
        return
    try:
        refresh()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Editor][LiveBridge] Failed to refresh live session discovery: %s", exc, exc_info=True)


def _workspace_root_for_editor(editor: Any) -> Path:
    getter = getattr(editor, "_get_repo_root", None)
    if callable(getter):
        return Path(getter()).resolve()
    from engine.repo_root import get_repo_root  # noqa: PLC0415

    return get_repo_root().resolve()


def _should_start_live_bridge(editor: Any) -> bool:
    window = getattr(editor, "window", None)
    if window is None:
        return False
    config = getattr(window, "engine_config", None)
    if getattr(config, "cocreative_live_bridge_enabled", True) is False:
        return False
    if getattr(window, "_mesh_live_bridge_interactive", False) is True:
        return True
    if getattr(window, "headless_smoke", False) or getattr(window, "_headless_smoke", False):
        return False
    if not optional_arcade.has_arcade():
        return False
    if getattr(optional_arcade.arcade, "__mesh_headless_stub__", False):
        return False
    window_cls = getattr(optional_arcade.arcade, "Window", None)
    if window_cls is None or not isinstance(window, window_cls):
        return False
    return bool(getattr(editor, "active", False))
