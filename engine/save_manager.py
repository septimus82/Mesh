"""Save/Load system for Mesh Engine."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .save_runtime import constants as save_constants
from .save_runtime import io as save_io
from .save_runtime import payloads as save_payloads
from .save_runtime.restore_policy import SLOT_POLICY
from .save_runtime.save_diagnostics import SaveDiagnosticsAggregator

if TYPE_CHECKING:
    from .game import GameWindow

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
        clean_name = "".join(c for c in slot_name if c.isalnum() or c in "_-")
        if not clean_name:
            clean_name = "autosave"
        return self.save_dir / f"{clean_name}.json"

    def save_game(self, slot_name: str, compact: bool = False) -> bool:
        """Save the current game state to a slot."""
        try:
            path = self.get_save_path(slot_name)
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
        try:
            path = self.get_save_path(slot_name)
            ok, payload_or_error = save_io.load_slot_payload(path, policy=SLOT_POLICY)
            if not ok:
                msg = str(payload_or_error or "")
                if msg:
                    sys.stderr.write(msg + "\n")
                return False
            data: dict = payload_or_error  # type: ignore[assignment]

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
                sys.stderr.write(save_io.format_load_error("[Mesh][Save]", apply_diags) + "\n")
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
            sys.stderr.write(f"[Mesh][Save] ERROR: Failed to load game: {exc}\n")
            return False

    def list_saves(self) -> list[str]:
        """Return a list of available save slots."""
        if not self.save_dir.exists():
            return []
        return sorted([f.stem for f in self.save_dir.glob("*.json")])

    def _get_timestamp(self) -> str:
        import datetime
        return datetime.datetime.now().isoformat()
