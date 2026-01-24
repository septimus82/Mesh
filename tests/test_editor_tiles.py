import arcade

from engine.editor_controller import EditorModeController


class DummyTilemapInstance:
    def __init__(self):
        self.layer_data = {"ground": [0, 0, 0, 0]}
        self.layer_dimensions = (2, 2)
        self.tile_size = (16, 16)
        self.layer_offsets = {"ground": (0.0, 0.0)}
        self.layer_lookup = {"ground": []}
        self.tilesets = [type("TS", (), {"first_gid": 1, "tile_count": 4, "contains": lambda self, gid: True})()]


class DummySceneController:
    def __init__(self):
        self.tilemap_instance = DummyTilemapInstance()

    def set_tile(self, layer: str, col: int, row: int, gid: int):
        data = self.tilemap_instance.layer_data[layer]
        width, _ = self.tilemap_instance.layer_dimensions
        idx = row * width + col
        old = data[idx]
        data[idx] = gid
        return (old, gid)


class DummyWindow:
    def __init__(self):
        from engine.config import EngineConfig
        cfg = EngineConfig()
        self.width = cfg.width
        self.height = cfg.height
        self.paused = False
        self.scene_controller = DummySceneController()
        self.screen_to_world = lambda x, y: (x, y)


def test_tile_paint_and_undo_redo():
    window = DummyWindow()
    controller = EditorModeController(window)
    controller.active = True

    controller.toggle_tile_panel()
    assert controller.tile_panel_active

    controller._paint_tile_at(8, 8, 2)
    data = window.scene_controller.tilemap_instance.layer_data["ground"]
    assert data[2] == 2  # row 1, col 0

    controller.undo_last()
    data = window.scene_controller.tilemap_instance.layer_data["ground"]
    assert data[2] == 0

    controller.redo_last()
    data = window.scene_controller.tilemap_instance.layer_data["ground"]
    assert data[2] == 2


def test_tile_panel_not_available_without_tilemap():
    window = DummyWindow()
    window.scene_controller.tilemap_instance = None
    controller = EditorModeController(window)
    controller.active = True
    controller.toggle_tile_panel()
    assert controller.tile_panel_active is False
