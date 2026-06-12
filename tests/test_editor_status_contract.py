from __future__ import annotations

from types import SimpleNamespace

from engine.editor_status import (
    HINT_LABEL,
    build_editor_operation_banner,
    build_editor_status,
)


class _StubSceneController:
    def __init__(self, path: str, name: str | None = None) -> None:
        self.current_scene_path = path
        self._loaded_scene_data = {"name": name} if name else {}

    @property
    def current_scene_data(self) -> dict[str, str]:
        return self._loaded_scene_data


def test_dirty_state_label() -> None:
    scene_controller = _StubSceneController("scenes/test_scene.json", name="Test Scene")
    editor = SimpleNamespace(
        window=SimpleNamespace(scene_controller=scene_controller),
        dirty_state=SimpleNamespace(is_dirty=False),
        scene_dirty=False,
        selected_entity=None,
        lights_tool_active=False,
        occluder_tool_active=False,
    )

    status = build_editor_status(editor)
    assert status["dirty_label"] == "Saved"

    editor.dirty_state.is_dirty = True
    status = build_editor_status(editor)
    assert status["dirty_label"] == "Unsaved"


def test_selection_label_modes() -> None:
    scene_controller = _StubSceneController("scenes/test_scene.json")
    editor = SimpleNamespace(
        window=SimpleNamespace(scene_controller=scene_controller),
        dirty_state=SimpleNamespace(is_dirty=False),
        scene_dirty=False,
        lights_tool_active=False,
        occluder_tool_active=False,
    )

    sprite = SimpleNamespace(mesh_name="chest_01", mesh_entity_data={"mesh_name": "chest_01"})
    editor.selected_entity = sprite
    status = build_editor_status(editor)
    assert status["selection_label"] == "Entity: chest_01"

    editor.lights_tool_active = True
    editor.lights_selection = 0
    editor._get_scene_lights = lambda: [{"name": "torch_3"}]
    status = build_editor_status(editor)
    assert status["selection_label"] == "Light: torch_3"

    editor.lights_tool_active = False
    editor.occluder_tool_active = True
    editor.occluder_selection = 1
    editor._get_scene_occluders = lambda: [{}, {}]
    status = build_editor_status(editor)
    assert status["selection_label"] == "Occluder: poly_2"


def test_hint_label_stable() -> None:
    scene_controller = _StubSceneController("")
    editor = SimpleNamespace(
        window=SimpleNamespace(scene_controller=scene_controller),
        dirty_state=SimpleNamespace(is_dirty=False),
        scene_dirty=False,
        selected_entity=None,
        lights_tool_active=False,
        occluder_tool_active=False,
    )

    status = build_editor_status(editor)
    assert status["hint_label"] == HINT_LABEL


# -----------------------------------------------------------------------------
# Operation Banner Tests
# -----------------------------------------------------------------------------


def _make_minimal_controller() -> SimpleNamespace:
    """Create minimal controller stub for banner tests."""
    scene_controller = _StubSceneController("scenes/test.json", name="Test")
    return SimpleNamespace(
        window=SimpleNamespace(scene_controller=scene_controller),
        dirty_state=SimpleNamespace(is_dirty=False),
        scene_dirty=False,
        selected_entity=None,
        lights_tool_active=False,
        occluder_tool_active=False,
        # Operation state defaults
        _marquee_active=False,
        _alt_dup_active=False,
        entity_dragging=False,
        _rotate_drag_active=False,
        _scale_drag_active=False,
        _move_preview_delta_xy=None,
        _rotate_preview_delta_deg=None,
        _scale_preview_factor=None,
    )


class TestOperationBannerAltDup:
    """Tests for alt-drag duplicate banner."""

    def test_alt_dup_active_shows_banner(self) -> None:
        """Alt-dup active should show ALT-DUP banner with cancel hints."""
        controller = _make_minimal_controller()
        controller._alt_dup_active = True

        banner = build_editor_operation_banner(controller)

        assert banner is not None
        assert "ALT-DUP:" in banner
        assert "(RMB/Esc cancel)" in banner

    def test_alt_dup_inactive_no_banner(self) -> None:
        """Alt-dup inactive should not produce banner (by itself)."""
        controller = _make_minimal_controller()
        controller._alt_dup_active = False

        banner = build_editor_operation_banner(controller)

        assert banner is None


class TestOperationBannerMove:
    """Tests for move transform banner."""

    def test_move_drag_shows_banner(self) -> None:
        """Move drag active should show MOVE banner with delta."""
        controller = _make_minimal_controller()
        controller.entity_dragging = True
        controller.selected_entity = SimpleNamespace()  # Non-None
        controller._move_preview_delta_xy = (16.0, -8.0)

        banner = build_editor_operation_banner(controller)

        assert banner is not None
        assert "MOVE:" in banner
        assert "Dx +16.0" in banner
        assert "Dy -8.0" in banner
        assert "(Shift snap)" in banner

    def test_move_drag_negative_delta(self) -> None:
        """Move drag with negative delta should show minus signs."""
        controller = _make_minimal_controller()
        controller.entity_dragging = True
        controller.selected_entity = SimpleNamespace()
        controller._move_preview_delta_xy = (-5.0, -10.0)

        banner = build_editor_operation_banner(controller)

        assert banner is not None
        assert "Dx -5.0" in banner
        assert "Dy -10.0" in banner


class TestOperationBannerRotate:
    """Tests for rotate transform banner."""

    def test_rotate_drag_shows_banner(self) -> None:
        """Rotate drag active should show ROTATE banner with angle."""
        controller = _make_minimal_controller()
        controller._rotate_drag_active = True
        controller._rotate_preview_delta_deg = 45.0

        banner = build_editor_operation_banner(controller)

        assert banner is not None
        assert "ROTATE:" in banner
        assert "Dth +45.0deg" in banner
        assert "(Shift 15deg snap)" in banner

    def test_rotate_drag_negative_angle(self) -> None:
        """Rotate drag with negative angle should show minus sign."""
        controller = _make_minimal_controller()
        controller._rotate_drag_active = True
        controller._rotate_preview_delta_deg = -30.0

        banner = build_editor_operation_banner(controller)

        assert banner is not None
        assert "Dth -30.0deg" in banner


class TestOperationBannerScale:
    """Tests for scale transform banner."""

    def test_scale_drag_shows_banner(self) -> None:
        """Scale drag active should show SCALE banner with factor."""
        controller = _make_minimal_controller()
        controller._scale_drag_active = True
        controller._scale_preview_factor = 1.50

        banner = build_editor_operation_banner(controller)

        assert banner is not None
        assert "SCALE:" in banner
        assert "x1.50" in banner
        assert "(Shift 0.1 snap)" in banner

    def test_scale_drag_small_factor(self) -> None:
        """Scale drag with small factor should show correctly."""
        controller = _make_minimal_controller()
        controller._scale_drag_active = True
        controller._scale_preview_factor = 0.75

        banner = build_editor_operation_banner(controller)

        assert banner is not None
        assert "x0.75" in banner


class TestOperationBannerMarquee:
    """Tests for marquee select banner."""

    def test_marquee_active_shows_banner(self) -> None:
        """Marquee active should show MARQUEE banner."""
        controller = _make_minimal_controller()
        controller._marquee_active = True

        banner = build_editor_operation_banner(controller)

        assert banner is not None
        assert "MARQUEE:" in banner
        assert "(Esc cancel)" in banner


class TestOperationBannerPrecedence:
    """Tests for operation banner precedence."""

    def test_marquee_wins_over_alt_dup(self) -> None:
        """Marquee should take precedence over alt-dup."""
        controller = _make_minimal_controller()
        controller._marquee_active = True
        controller._alt_dup_active = True

        banner = build_editor_operation_banner(controller)

        assert banner is not None
        assert "MARQUEE:" in banner
        assert "ALT-DUP:" not in banner

    def test_alt_dup_wins_over_move_drag(self) -> None:
        """Alt-dup should take precedence over move drag."""
        controller = _make_minimal_controller()
        controller._alt_dup_active = True
        controller.entity_dragging = True
        controller.selected_entity = SimpleNamespace()
        controller._move_preview_delta_xy = (10.0, 20.0)

        banner = build_editor_operation_banner(controller)

        assert banner is not None
        assert "ALT-DUP:" in banner
        assert "MOVE:" not in banner

    def test_alt_dup_wins_over_rotate_drag(self) -> None:
        """Alt-dup should take precedence over rotate drag."""
        controller = _make_minimal_controller()
        controller._alt_dup_active = True
        controller._rotate_drag_active = True
        controller._rotate_preview_delta_deg = 45.0

        banner = build_editor_operation_banner(controller)

        assert banner is not None
        assert "ALT-DUP:" in banner
        assert "ROTATE:" not in banner

    def test_rotate_wins_over_move(self) -> None:
        """Rotate drag should take precedence over move drag."""
        controller = _make_minimal_controller()
        controller._rotate_drag_active = True
        controller._rotate_preview_delta_deg = 15.0
        controller.entity_dragging = True
        controller.selected_entity = SimpleNamespace()
        controller._move_preview_delta_xy = (5.0, 5.0)

        banner = build_editor_operation_banner(controller)

        assert banner is not None
        assert "ROTATE:" in banner
        assert "MOVE:" not in banner

    def test_scale_wins_over_move(self) -> None:
        """Scale drag should take precedence over move drag."""
        controller = _make_minimal_controller()
        controller._scale_drag_active = True
        controller._scale_preview_factor = 2.0
        controller.entity_dragging = True
        controller.selected_entity = SimpleNamespace()
        controller._move_preview_delta_xy = (5.0, 5.0)

        banner = build_editor_operation_banner(controller)

        assert banner is not None
        assert "SCALE:" in banner
        assert "MOVE:" not in banner


class TestOperationBannerNoneActive:
    """Tests for when no operation is active."""

    def test_none_active_returns_none(self) -> None:
        """No operation active should return None."""
        controller = _make_minimal_controller()

        banner = build_editor_operation_banner(controller)

        assert banner is None

    def test_status_unchanged_when_no_operation(self) -> None:
        """Status center text should be selection label when no operation."""
        controller = _make_minimal_controller()
        sprite = SimpleNamespace(mesh_name="test_entity", mesh_entity_data={"mesh_name": "test_entity"})
        controller.selected_entity = sprite

        status = build_editor_status(controller)

        assert status["operation_banner"] is None
        assert status["selection_label"] == "Entity: test_entity"

    def test_status_banner_replaces_selection_when_active(self) -> None:
        """Operation banner should be used instead of selection when active."""
        controller = _make_minimal_controller()
        sprite = SimpleNamespace(mesh_name="test_entity", mesh_entity_data={"mesh_name": "test_entity"})
        controller.selected_entity = sprite
        controller._alt_dup_active = True

        status = build_editor_status(controller)

        assert status["operation_banner"] is not None
        assert "ALT-DUP:" in status["operation_banner"]
        # Selection label is still computed but banner takes precedence in display
        assert status["selection_label"] == "Entity: test_entity"
