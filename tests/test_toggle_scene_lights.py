from engine.behaviours.toggle_scene_lights import ToggleSceneLights
from engine.events import MeshEventBus


class DummyLighting:
    def __init__(self):
        self.calls = []

    def configure_scene_lights(self, lights):
        self.calls.append(list(lights))


class DummySceneController:
    def __init__(self, scene):
        self._loaded_scene_data = scene


class DummyWindow:
    def __init__(self, scene):
        self.scene_controller = DummySceneController(scene)
        self.event_bus = MeshEventBus()
        self.lighting = DummyLighting()


def test_toggle_scene_lights_group_toggle():
    scene = {"lights": [{"enabled": True, "group": "room"}, {"enabled": True, "group": "other"}]}
    window = DummyWindow(scene)
    beh = ToggleSceneLights(entity=None, window=window, listen_event="flip", group="room", indices=[], mode="toggle")
    window.event_bus.emit("flip")
    assert scene["lights"][0]["enabled"] is False
    assert scene["lights"][1]["enabled"] is True
    assert window.lighting.calls, "configure_scene_lights not called"


def test_toggle_scene_lights_indices_on_off():
    scene = {"lights": [{"enabled": True}, {"enabled": False}]}
    window = DummyWindow(scene)
    beh = ToggleSceneLights(entity=None, window=window, listen_event="all_on", indices=[0, 1], group="", mode="on")
    window.event_bus.emit("all_on")
    assert scene["lights"][0]["enabled"] is True
    assert scene["lights"][1]["enabled"] is True
    beh_off = ToggleSceneLights(entity=None, window=window, listen_event="all_off", indices=[0, 1], group="", mode="off")
    window.event_bus.emit("all_off")
    assert scene["lights"][0]["enabled"] is False
    assert scene["lights"][1]["enabled"] is False


def test_no_listen_event_does_not_subscribe():
    scene = {"lights": [{"enabled": True}]}
    window = DummyWindow(scene)
    beh = ToggleSceneLights(entity=None, window=window, listen_event="", group="", indices=[], mode="toggle")
    # emitting unrelated event should not change state or crash
    window.event_bus.emit("anything")
    assert scene["lights"][0]["enabled"] is True
