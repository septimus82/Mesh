"""Save/Load system for Mesh Engine."""

from __future__ import annotations

import sys
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from .diagnostics import add_exception as diag_add_exception
from .diagnostics import error as diag_error
from .diagnostics import info as diag_info
from .diagnostics import warn as diag_warn
from .save_runtime import constants as save_constants
from .save_runtime import io as save_io
from .save_runtime import payloads as save_payloads
from .save_runtime.restore_policy import SLOT_POLICY
from .save_runtime.save_diagnostics import SaveDiagnosticsAggregator
from .save_runtime.ux_codes import (
    LOAD_APPLY_FAILED,
    LOAD_FALLBACK_TO_START_SCENE,
    LOAD_NOT_FOUND,
    LOAD_PARSE_FAILED,
    LOAD_SCHEMA_INVALID,
    SAVE_IO_PERMISSION,
    SAVE_SERIALIZE_FAILED,
    SAVE_SLOT_INVALID,
    SAVE_WRITE_FAILED,
)

if TYPE_CHECKING:
    from .game import GameWindow


_DIAG_SOURCE = "engine.save_manager"


def _classify_save_exception(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, PermissionError):
        return SAVE_IO_PERMISSION, "Check write permissions for the save directory."
    if isinstance(exc, (TypeError, ValueError)):
        return SAVE_SERIALIZE_FAILED, "The save payload is invalid. Retry after restarting the scene."
    return SAVE_WRITE_FAILED, "Retry saving after checking disk space and write permissions."


_SLOT_RE = re.compile(r"(\d+)")


def _slot_index(slot_name: str | None) -> int | None:
    raw = str(slot_name or "").strip()
    if not raw:
        return None
    match = _SLOT_RE.search(raw)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _diag_context(
    *,
    operation: str,
    save_path: Path | str | None,
    slot_name: str | None = None,
    pointer: str = "$",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(save_path, Path):
        normalized_path = save_path.as_posix()
    else:
        normalized_path = str(save_path or "").replace("\\", "/")
    context: dict[str, Any] = {
        "operation": str(operation),
        "pointer": str(pointer),
        "save_path": normalized_path,
    }
    slot = _slot_index(slot_name)
    if slot is not None:
        context["slot"] = int(slot)
    if extra:
        for key in sorted(extra.keys()):
            context[str(key)] = extra[key]
    return context


class SaveManager:
    """Manages saving and loading game state to disk."""

    def __init__(self, window: GameWindow, save_dir: str = save_constants.DEFAULT_SAVE_DIR) -> None:
        self.window = window
        self.save_dir = Path(save_dir)
        self._ensure_save_dir()
        self._last_loaded_signature: tuple[str, int] | None = None
        self._last_saved_signature: str | None = None

    def _ensure_save_dir(self) -> None:
        if not self.save_dir.exists():
            self.save_dir.mkdir(parents=True, exist_ok=True)

    def get_save_path(self, slot_name: str) -> Path:
        """Return the full path for a given save slot."""
        raw_name = str(slot_name or "").strip()
        clean_name = "".join(c for c in raw_name if c.isalnum() or c in "_-")
        fallback_name = clean_name or "autosave"
        fallback_path = self.save_dir / f"{fallback_name}.json"
        if not clean_name:
            diag_warn(
                SAVE_SLOT_INVALID,
                f"Invalid save slot '{raw_name}'. Using default slot name 'autosave'.",
                _DIAG_SOURCE,
                context=_diag_context(
                    operation="save_or_load",
                    save_path=fallback_path,
                    slot_name=raw_name,
                    pointer="$/slot",
                ),
                hint="Use letters, numbers, '_' or '-' in slot names.",
            )
            clean_name = "autosave"
        elif clean_name != raw_name:
            diag_warn(
                SAVE_SLOT_INVALID,
                f"Save slot '{raw_name}' was normalized to '{clean_name}'.",
                _DIAG_SOURCE,
                context=_diag_context(
                    operation="save_or_load",
                    save_path=fallback_path,
                    slot_name=raw_name,
                    pointer="$/slot",
                    extra={"normalized_slot": clean_name},
                ),
                hint="Use letters, numbers, '_' or '-' in slot names to avoid normalization.",
            )
        return self.save_dir / f"{clean_name}.json"

    def save_game(self, slot_name: str, compact: bool = False) -> bool:
        """Save the current game state to a slot."""
        path = self.get_save_path(slot_name)
        try:
            snapshot, content_hash = save_payloads.build_slot_payload(
                self.window,
                slot_name,
                compact=compact,
                timestamp=self._get_timestamp(),
            )

            # Atomic write so partial saves never corrupt the existing slot file.
            # Keep the same JSON formatting (indent=2, sort_keys=True) with standardized trailing newline.
            save_io.write_json_pretty_atomic(path, snapshot)

            # Toast if content changed or first save
            if content_hash != self._last_saved_signature:
                if hasattr(self.window, "player_hud"):
                    self.window.player_hud.enqueue_toast("Game Saved")
                self._last_saved_signature = content_hash

            sys.stderr.write(f"[Mesh][Save] Game saved to '{path}'\n")
            return True
        except Exception as exc:
            code, hint = _classify_save_exception(exc)
            diag_error(
                code,
                f"Failed to save slot '{slot_name}': {exc}",
                _DIAG_SOURCE,
                location=path.as_posix(),
                context=_diag_context(
                    operation="save",
                    save_path=path,
                    slot_name=slot_name,
                    pointer="$",
                ),
                hint=hint,
            )
            sys.stderr.write(f"[Mesh][Save] ERROR: Failed to save game: {exc}\n")
            return False

    def load_game(self, slot_name: str) -> bool:
        """Load a game state from a slot."""
        editor = getattr(self.window, "editor_controller", None)
        active = getattr(editor, "active", False) if editor is not None else False
        if isinstance(active, bool) and active:
            blocker = getattr(editor, "confirm_unsaved_changes", None)
            if callable(blocker):
                blocked = blocker("Load Game", lambda: self._load_game_impl(slot_name))
                if isinstance(blocked, bool) and blocked:
                    return True
        return self._load_game_impl(slot_name)

    def _load_game_impl(self, slot_name: str) -> bool:
        path = self.get_save_path(slot_name)
        if not path.exists():
            diag_warn(
                LOAD_NOT_FOUND,
                f"Save slot '{slot_name}' was not found.",
                _DIAG_SOURCE,
                location=path.as_posix(),
                context=_diag_context(
                    operation="load",
                    save_path=path,
                    slot_name=slot_name,
                    pointer="$",
                ),
                hint="Start a new game and save once before using Continue/Load.",
            )
            sys.stderr.write(f"[Mesh][Save] Save file '{path}' not found\n")
            self._fallback_to_start_scene(slot_name=slot_name, failed_path=path, reason_code=LOAD_NOT_FOUND)
            return False

        try:
            ok, payload_or_error = save_io.load_slot_payload(path, policy=SLOT_POLICY)
            if not ok:
                msg = str(payload_or_error or "")
                code = self._derive_load_failure_code(msg)
                hint = self._derive_load_failure_hint(code)
                if code == LOAD_NOT_FOUND:
                    diag_warn(
                        code,
                        f"Load failed for slot '{slot_name}'.",
                        _DIAG_SOURCE,
                        location=path.as_posix(),
                        context=_diag_context(
                            operation="load",
                            save_path=path,
                            slot_name=slot_name,
                            pointer="$",
                            extra={"error": msg},
                        ),
                        hint=hint,
                    )
                else:
                    diag_error(
                        code,
                        f"Load failed for slot '{slot_name}'.",
                        _DIAG_SOURCE,
                        location=path.as_posix(),
                        context=_diag_context(
                            operation="load",
                            save_path=path,
                            slot_name=slot_name,
                            pointer="$",
                            extra={"error": msg},
                        ),
                        hint=hint,
                    )
                if msg:
                    sys.stderr.write(msg + "\n")
                self._fallback_to_start_scene(slot_name=slot_name, failed_path=path, reason_code=code)
                return False
            data = cast(dict[str, Any], payload_or_error)

            # 1. Reset global state
            # We need to ensure the state is clean before loading the scene,
            # otherwise the scene load might merge with existing state.
            # However, SceneController.load_scene merges state.
            # So we should extract the state from the save and force-set it.
            apply_diags = SaveDiagnosticsAggregator()
            applied = save_payloads.apply_loaded_payload(
                self.window,
                data,
                mode="slot",
                policy=SLOT_POLICY,
                diagnostics=apply_diags,
                source=path.as_posix(),
            )
            save_io.record_load_attempt(
                kind="slot_apply",
                path=path,
                ok=bool(applied),
                aggregator=apply_diags,
            )
            if not applied:
                if SLOT_POLICY.write_sidecars_on_failure:
                    save_io.write_diagnostics_sidecars(path, apply_diags)
                primary = apply_diags.primary()
                pointer = "$"
                inner_code = ""
                if primary is not None:
                    context = primary.context if isinstance(primary.context, dict) else {}
                    pointer = str(context.get("pointer", "$") or "$")
                    inner_code = str(primary.code or "")
                diag_error(
                    LOAD_APPLY_FAILED,
                    f"Failed to apply loaded save slot '{slot_name}'.",
                    _DIAG_SOURCE,
                    location=path.as_posix(),
                    context=_diag_context(
                        operation="load",
                        save_path=path,
                        slot_name=slot_name,
                        pointer=pointer,
                        extra={"apply_code": inner_code},
                    ),
                    hint="Start a new game, then create a fresh save in this slot.",
                )
                sys.stderr.write(save_io.format_load_error("[Mesh][Save]", apply_diags) + "\n")
                self._fallback_to_start_scene(slot_name=slot_name, failed_path=path, reason_code=LOAD_APPLY_FAILED)
                return False

            # 2. Determine which scene to load
            # If the save file IS a valid scene (which build_scene_snapshot produces),
            # we can load it directly as a scene.
            # However, SceneController.load_scene expects a path to a file on disk.
            # We can pass the path to the save file itself!

            # But wait, load_scene reads the file again.
            # That's fine.

            # Check signature to avoid spamming "Loaded"
            current_signature = (str(path), path.stat().st_mtime_ns)
            should_toast = current_signature != self._last_loaded_signature
            self._last_loaded_signature = current_signature

            if hasattr(self.window, "player_hud"):
                self.window.player_hud.clear_toasts()
                if should_toast:
                    self.window.player_hud.enqueue_toast("Loaded")

            sys.stderr.write(f"[Mesh][Save] Loading save from '{path}'\n")
            self.window.request_scene_change(str(path))

            return True
        except Exception as exc:
            diag_add_exception(
                LOAD_APPLY_FAILED,
                exc,
                _DIAG_SOURCE,
                location=path.as_posix(),
                context=_diag_context(
                    operation="load",
                    save_path=path,
                    slot_name=slot_name,
                    pointer="$",
                ),
                severity="error",
                hint="Start a new game and create a fresh save slot.",
            )
            sys.stderr.write(f"[Mesh][Save] ERROR: Failed to load game: {exc}\n")
            self._fallback_to_start_scene(slot_name=slot_name, failed_path=path, reason_code=LOAD_APPLY_FAILED)
            return False

    def _derive_load_failure_code(self, message: str) -> str:
        message_lower = str(message or "").lower()
        if "not found" in message_lower:
            return LOAD_NOT_FOUND

        snapshot = save_io.get_save_runtime_diagnostics_snapshot()
        attempt = snapshot.get("last_load_attempt", {})
        rows: list[dict[str, Any]] = []
        if isinstance(attempt, dict):
            diagnostics = attempt.get("diagnostics", {})
            if isinstance(diagnostics, dict):
                raw_rows = diagnostics.get("diagnostics", [])
                if isinstance(raw_rows, list):
                    rows = [row for row in raw_rows if isinstance(row, dict)]

        raw_codes = [str(row.get("code", "") or "").strip().lower() for row in rows]
        if any(code == "save.load.schema_validation_error" for code in raw_codes):
            return LOAD_SCHEMA_INVALID
        if any(code == "save.load.schema_migration_error" for code in raw_codes):
            return LOAD_SCHEMA_INVALID
        if any(code == "save.load.read_error" for code in raw_codes):
            return LOAD_PARSE_FAILED
        if any(code == "save.load.invalid_root" for code in raw_codes):
            return LOAD_PARSE_FAILED
        if any(code == "save.load.format_migration_error" for code in raw_codes):
            return LOAD_SCHEMA_INVALID
        return LOAD_PARSE_FAILED

    @staticmethod
    def _derive_load_failure_hint(code: str) -> str:
        if code == LOAD_NOT_FOUND:
            return "Start a new game and save once before using Continue/Load."
        if code == LOAD_SCHEMA_INVALID:
            return "This save is incompatible with the current version. Create a new save."
        return "The save data appears corrupted. Restore from a backup or create a new save."

    def _fallback_to_start_scene(self, *, slot_name: str, failed_path: Path, reason_code: str) -> None:
        cfg = getattr(self.window, "engine_config", None)
        target_scene = str(getattr(cfg, "start_scene", "") or "").strip()
        requester = getattr(self.window, "request_scene_change", None)
        if not target_scene or not callable(requester):
            return
        try:
            requester(target_scene)
            diag_info(
                LOAD_FALLBACK_TO_START_SCENE,
                f"Load failed for slot '{slot_name}'. Falling back to start scene.",
                _DIAG_SOURCE,
                location=target_scene,
                context=_diag_context(
                    operation="load",
                    save_path=failed_path,
                    slot_name=slot_name,
                    pointer="$",
                    extra={
                        "reason_code": str(reason_code or ""),
                        "target_scene": target_scene,
                    },
                ),
                hint="Try a different slot or delete the corrupt save.",
            )
        except Exception as exc:  # noqa: BLE001
            diag_add_exception(
                LOAD_FALLBACK_TO_START_SCENE,
                exc,
                _DIAG_SOURCE,
                location=target_scene,
                context=_diag_context(
                    operation="load",
                    save_path=failed_path,
                    slot_name=slot_name,
                    pointer="$",
                    extra={"target_scene": target_scene},
                ),
                severity="warning",
                hint="Try starting a new game manually from the main menu.",
            )

    def list_saves(self) -> list[str]:
        """Return a list of available save slots."""
        if not self.save_dir.exists():
            return []
        return sorted([f.stem for f in self.save_dir.glob("*.json")])

    def _get_timestamp(self) -> str:
        import datetime
        return datetime.datetime.now().isoformat()
