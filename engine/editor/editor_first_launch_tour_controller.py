"""First-launch tour controller for the Mesh editor.

Shows a 5-step modal walkthrough on first editor open (tour_completed=False).
Subsequent launches skip the tour. Users can replay via the command palette.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Locked tour step content
# ---------------------------------------------------------------------------

TOUR_STEPS: tuple[str, ...] = (
    (
        "Welcome to Mesh Editor!\n\n"
        "This is your scene authoring workspace. Press Next to learn the basics, "
        "or Skip to dive in."
    ),
    "This is the scene viewport. Click an entity to select it. Drag to pan. Scroll to zoom.",
    (
        "Press Ctrl+P at any time to open the command palette. Type to fuzzy-find any action "
        "— try 'Build for Windows' to package your game."
    ),
    (
        "Press F6 to playtest from the current scene. "
        "Press Esc to return to the editor exactly where you left off."
    ),
    (
        "You're ready! Edit scenes/ to add content. "
        "The Problems panel surfaces issues as you go. Have fun building."
    ),
)

TOUR_STEP_COUNT = len(TOUR_STEPS)


class EditorTourController:
    """Owns tour state, step progression, and persistence."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor
        self.is_active: bool = False
        self.current_step: int = 0
        # Skip-confirmation sub-modal
        self.skip_confirm_open: bool = False
        self.skip_confirm_index: int = 0  # 0 = "Yes, don't show again", 1 = "Keep touring"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def maybe_start(self) -> None:
        """Start the tour if config.tour_completed is False."""
        config = self._get_config()
        if config is None:
            return
        if not getattr(config, "tour_completed", True):
            self.start()

    def start(self) -> None:
        """Start (or restart) the tour from step 0."""
        self.is_active = True
        self.current_step = 0
        self.skip_confirm_open = False
        self.skip_confirm_index = 0

    def advance(self) -> None:
        """Advance to the next step, or complete on the final step."""
        if not self.is_active:
            return
        if self.current_step >= TOUR_STEP_COUNT - 1:
            self.complete()
        else:
            self.current_step += 1

    def complete(self) -> None:
        """Mark tour finished and persist flag."""
        self.is_active = False
        self.skip_confirm_open = False
        self._persist(True)

    def request_skip(self) -> None:
        """Open the skip-confirmation sub-modal (triggered by Esc or Skip button)."""
        if not self.is_active:
            return
        self.skip_confirm_open = True
        self.skip_confirm_index = 0

    def confirm_skip(self, *, dont_show_again: bool) -> None:
        """Resolve the skip-confirmation modal.

        Args:
            dont_show_again: If True, sets tour_completed=True and closes.
                             If False, returns to the tour.
        """
        self.skip_confirm_open = False
        self.skip_confirm_index = 0
        if dont_show_again:
            self.skip()
        # else: fall back into the active tour

    def skip(self) -> None:
        """Immediately close the tour and persist tour_completed=True."""
        self.is_active = False
        self.skip_confirm_open = False
        self._persist(True)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_text(self) -> str:
        """Return the locked text for the current step."""
        idx = max(0, min(self.current_step, TOUR_STEP_COUNT - 1))
        return TOUR_STEPS[idx]

    @property
    def is_final_step(self) -> bool:
        return self.current_step >= TOUR_STEP_COUNT - 1

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _persist(self, value: bool) -> None:
        """Write tour_completed to EngineConfig and flush to disk if possible."""
        config = self._get_config()
        if config is None:
            return
        try:
            config.tour_completed = value
            config_path = getattr(config, "_config_path", None)
            if config_path is not None:
                from engine.config import save_config  # noqa: PLC0415
                save_config(config, config_path)
        except Exception:  # noqa: BLE001  # REASON: persistence failure must not crash the editor
            pass

    def _get_config(self) -> Any:
        """Resolve EngineConfig from the editor or its window."""
        # Direct attribute — used by tests (SimpleNamespace) and future callers.
        config = getattr(self._editor, "config", None)
        if config is not None:
            return config
        # Real EditorModeController path: editor.window.engine_config
        window = getattr(self._editor, "window", None)
        if window is not None:
            return getattr(window, "engine_config", None)
        return None
