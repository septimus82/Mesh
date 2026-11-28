"""F7: a hot reload checks the replacement scene before it takes the running one down.

Both reload routes (``transitions.reload_scene``, immediate, and ``scene_lifecycle_controller.handle_pending_scene_load``
for a queued reload) first load the scene the way a reload would, through the scene loader itself (an open Studio
document before the file, migration, the schema, ``validate_scene``), but strictly: a scene the loader would replace
with an empty one is refused rather than loaded empty. Only a scene that passes is then built, from that very load
(handed over here, not read again). A refused reload changes nothing: sprites, layers, subscriptions, queued events,
player, camera, game state, room memory and asset caches are as they were, and the scene keeps running.

Every attempt leaves one result on the scene controller (``last_reload_result``), the same for the person (the
hot-reload error the game and editor show) and for an AI (the editor's live read, ``last_reload``):
``{ok, reason, stage, route, scene_path, message, previous_scene_preserved, can_retry, errors, errors_total}``.

A scene that passes the check can still fail while it is built (a behaviour, a texture, the GPU): that is stage
``construction``, after the running scene was cleared, so ``previous_scene_preserved`` is false then. Reload again
once it is fixed.
"""

from __future__ import annotations

import json
from pathlib import PurePath
from typing import Any

from engine.scene_loader import SceneValidationFailed
from engine.schema_validation import SchemaValidationError
from engine.swallowed_exceptions import _log_swallow

MAX_ERRORS = 10
_HANDED_OVER = "_reload_checked_scene"


def result(*, ok: bool, scene_path: str, route: str, reason: str | None = None, stage: str | None = None,
           message: str = "", preserved: bool = False, errors: list[str] | None = None) -> dict[str, Any]:
    """The outcome of one reload attempt. ``previous_scene_preserved``: the scene running before it still is."""
    errors = [str(e) for e in errors or []]
    return {"ok": ok, "reason": reason, "stage": stage, "route": route, "scene_path": scene_path, "message": message,
            "previous_scene_preserved": preserved, "can_retry": True, "errors": errors[:MAX_ERRORS],
            "errors_total": len(errors)}


def check(controller: Any, scene_path: str, route: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """``(scene, None)``: the scene as a reload would load it; ``(None, refusal)``: why it can't be, nothing changed.
    ``(None, None)``: no scene loader to check with (a stand-in window), the reload goes ahead as before."""
    load = getattr(getattr(getattr(controller, "window", None), "scene_loader", None), "load_scene", None)
    if not callable(load):
        return None, None
    name = PurePath(scene_path).name or scene_path
    errors: list[str] = []
    try:
        scene = load(scene_path, strict=True)
    except FileNotFoundError as err:
        reason, detail = "scene_missing", f"{name} doesn't exist" if str(err).startswith("Scene file not found") else str(err)
    except SceneValidationFailed as err:
        reason, detail, errors = "scene_invalid", f"{name} isn't a valid scene: {err.errors[0]}", err.errors
    except SchemaValidationError as err:
        reason, detail = "schema_invalid", f"{name} doesn't match the scene format at '{err.json_pointer or '/'}': {err.message}"
        errors = [f"{err.json_pointer or '/'}: {err.message}"]
    except json.JSONDecodeError as err:
        reason, detail = "invalid_json", f"{name} isn't valid JSON (line {err.lineno}, column {err.colno}: {err.msg})"
    except UnicodeDecodeError as err:
        reason, detail = "scene_unreadable", f"{name} isn't UTF-8 text ({err.reason})"
    except OSError as err:
        reason, detail = "scene_unreadable", f"{name} can't be read ({err.strerror or err})"
    except Exception as err:  # noqa: BLE001  # REASON: the loader's other errors (a migration, a root that isn't an object) refuse the reload too
        _log_swallow("RELOAD-001", f"hot reload refused: {scene_path} can't be loaded")
        reason, detail = "scene_invalid", f"{name} can't be loaded ({type(err).__name__}: {err})"
    else:
        return (scene if isinstance(scene, dict) else None), None
    message = (f"Scene not reloaded: {detail}. The scene that was running is still running, unchanged; fix it and "
               "reload again.")
    return None, result(ok=False, scene_path=scene_path, route=route, reason=reason, stage="preflight",
                        message=message, preserved=True, errors=errors or [detail])


def hand_over(controller: Any, scene_path: str, scene: dict[str, Any] | None) -> None:
    """Give the checked scene to the load that follows (``take``), so it is built from what was checked."""
    setattr(controller, _HANDED_OVER, (scene_path, scene) if scene is not None else None)


def take(controller: Any, scene_path: str) -> dict[str, Any] | None:
    """The scene handed over for ``scene_path`` (once), else None: the load reads it itself."""
    handed = getattr(controller, _HANDED_OVER, None)
    setattr(controller, _HANDED_OVER, None)
    return handed[1] if handed and handed[0] == scene_path else None


def publish(controller: Any, outcome: dict[str, Any]) -> None:
    """Record ``outcome`` as the last reload's, and show or clear the hot-reload error the person sees."""
    controller.last_reload_result = outcome
    window = getattr(controller, "window", None)
    if outcome["ok"]:
        controller._last_hot_reload_error_message = ""
        controller._last_hot_reload_error_scene = ""
        clear = getattr(window, "clear_hot_reload_error", None)
        if callable(clear):
            clear()
        return
    controller._last_hot_reload_error_message = outcome["message"]
    controller._last_hot_reload_error_scene = outcome["scene_path"]
    show = getattr(window, "set_hot_reload_error", None)
    if callable(show):
        show(outcome["message"], outcome["scene_path"])
