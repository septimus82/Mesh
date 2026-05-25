"""Lightweight arcade fallback for headless-safe imports.

This module provides a minimal, deterministic stub surface for the parts of
Arcade that Mesh imports at runtime. It is not feature complete.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Sequence, Tuple


ColorValue = Tuple[int, int, int] | Tuple[int, int, int, int]


class _ColorNamespace:
    def __init__(self) -> None:
        self._values: Dict[str, ColorValue] = {
            "WHITE": (255, 255, 255),
            "BLACK": (0, 0, 0),
            "RED": (255, 0, 0),
            "GREEN": (0, 255, 0),
            "BLUE": (0, 0, 255),
            "YELLOW": (255, 255, 0),
            "CYAN": (0, 255, 255),
            "MAGENTA": (255, 0, 255),
            "TRANSPARENT_BLACK": (0, 0, 0, 0),
            "GRAY": (128, 128, 128),
            "DARK_GRAY": (169, 169, 169),
            "LIGHT_GRAY": (211, 211, 211),
            "SKY_BLUE": (135, 206, 235),
            "GOLD": (255, 215, 0),
            "ORANGE": (255, 165, 0),
            "LIME": (50, 205, 50),
            "LIME_GREEN": (50, 205, 50),
            "ALPINE": (100, 200, 180),
            "NEON_GREEN": (57, 255, 20),
            "DARK_BLUE_GRAY": (75, 85, 95),
            "DARK_RED": (139, 0, 0),
            "DARK_SLATE_GRAY": (47, 79, 79),
            "DARK_SPRING_GREEN": (23, 114, 69),
        }

    def __getattr__(self, name: str) -> ColorValue:
        return self._values.get(name, self._values["WHITE"])


class _KeyNamespace:
    F1 = 65470
    F2 = 65471
    F3 = 65472
    F4 = 65473
    F5 = 65474
    F6 = 65475
    F7 = 65476
    F8 = 65477
    F9 = 65478
    F10 = 65479
    F11 = 65480
    F12 = 65481

    UP = 65362
    DOWN = 65364
    LEFT = 65361
    RIGHT = 65363

    LSHIFT = 65505
    RSHIFT = 65506
    LCTRL = 65507
    RCTRL = 65508
    LALT = 65513
    RALT = 65514
    MOD_SHIFT = 1
    MOD_CTRL = 2
    MOD_ALT = 4

    ENTER = 65293
    RETURN = 65293
    NUM_ENTER = 65421
    ESCAPE = 65307
    BACKSPACE = 65288
    TAB = 65289
    SPACE = 32
    DELETE = 65535
    INSERT = 65379
    HOME = 65360
    END = 65367
    PAGEUP = 65365
    PAGEDOWN = 65366
    PAGE_UP = 65365
    PAGE_DOWN = 65366

    KEY_0 = 48
    KEY_1 = 49
    KEY_2 = 50
    KEY_3 = 51
    KEY_4 = 52
    KEY_5 = 53
    KEY_6 = 54
    KEY_7 = 55
    KEY_8 = 56
    KEY_9 = 57

    A = 97
    B = 98
    C = 99
    D = 100
    E = 101
    F = 102
    G = 103
    H = 104
    I = 105
    J = 106
    K = 107
    L = 108
    M = 109
    N = 110
    O = 111
    P = 112
    Q = 113
    R = 114
    S = 115
    T = 116
    U = 117
    V = 118
    W = 119
    X = 120
    Y = 121
    Z = 122

    GRAVE = 96
    MINUS = 45
    EQUAL = 61
    LBRACKET = 91
    RBRACKET = 93
    LEFT_BRACKET = 91
    RIGHT_BRACKET = 93
    BACKSLASH = 92
    SEMICOLON = 59
    APOSTROPHE = 39
    COMMA = 44
    PERIOD = 46
    SLASH = 47

    @staticmethod
    def key_string(value: int) -> str:
        return str(value)


class SystemMouseCursor:
    DEFAULT = "default"
    HAND = "hand"
    MOVE = "move"
    SIZE_WE = "size_we"
    SIZE_NS = "size_ns"
    CROSSHAIR = "crosshair"


SYSTEM_CURSOR_DEFAULT = SystemMouseCursor.DEFAULT
SYSTEM_CURSOR_HAND = SystemMouseCursor.HAND
SYSTEM_CURSOR_MOVE = SystemMouseCursor.MOVE
SYSTEM_CURSOR_SIZE_WE = SystemMouseCursor.SIZE_WE
SYSTEM_CURSOR_SIZE_NS = SystemMouseCursor.SIZE_NS
SYSTEM_CURSOR_CROSSHAIR = SystemMouseCursor.CROSSHAIR


MOUSE_BUTTON_LEFT = 1
MOUSE_BUTTON_MIDDLE = 2
MOUSE_BUTTON_RIGHT = 4


color = _ColorNamespace()
key = _KeyNamespace()

gl = SimpleNamespace(
    GL_NEAREST=0,
    GL_LINEAR=1,
)


class Window:
    """Stub Window class."""

    def __init__(self, width: int = 800, height: int = 600, title: str = "Stub", **kwargs: Any) -> None:
        self.width = width
        self.height = height
        self.title = title
        self.ctx = SimpleNamespace()

    def show_view(self, view: Any) -> None:
        pass

    def run(self) -> None:
        pass

    def close(self) -> None:
        pass

    def set_mouse_visible(self, visible: bool) -> None:
        pass

    def set_location(self, x: int, y: int) -> None:
        pass

    def set_mouse_cursor(self, cursor: Any) -> None:
        pass


class View:
    """Stub View class."""

    def __init__(self) -> None:
        self.window = None

    def on_show(self) -> None:
        pass

    def on_show_view(self) -> None:
        pass

    def on_hide_view(self) -> None:
        pass

    def on_draw(self) -> None:
        pass

    def on_update(self, delta_time: float) -> None:
        pass

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        pass

    def on_key_release(self, symbol: int, modifiers: int) -> None:
        pass

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> None:
        pass

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
        pass


class Texture:
    """Stub Texture class."""

    def __init__(self, name: str, image: Any = None, **kwargs: Any) -> None:
        self.name = name
        self.width = int(kwargs.get("width", 10))
        self.height = int(kwargs.get("height", 10))


class Sprite:
    """Stub Sprite class."""

    def __init__(self, filename: str | None = None, scale: float = 1.0, **kwargs: Any) -> None:
        self.position = (0.0, 0.0)
        self.center_x = 0.0
        self.center_y = 0.0
        self.change_x = 0.0
        self.change_y = 0.0
        self.angle = 0.0
        self.change_angle = 0.0
        self.scale = float(scale)
        self.width = 10.0 * self.scale
        self.height = 10.0 * self.scale
        self.alpha = 255
        self.color = (255, 255, 255)
        self.visible = True
        self.texture = kwargs.get("texture", None)
        self.filename = filename

    def draw(self) -> None:
        pass

    def update(self) -> None:
        pass

    def kill(self) -> None:
        pass

    def remove_from_sprite_lists(self) -> None:
        pass

    def collides_with_list(self, sprite_list: "SpriteList") -> List["Sprite"]:
        return []


class SpriteSolidColor(Sprite):
    def __init__(self, width: int, height: int, color: Tuple[int, int, int] = (255, 255, 255), **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.width = float(width)
        self.height = float(height)
        self.color = color


class SpriteList(list):
    """Stub SpriteList class."""

    def __init__(self, use_spatial_hash: bool = False, **kwargs: Any) -> None:
        super().__init__()
        self.use_spatial_hash = use_spatial_hash

    def draw(self, **kwargs: Any) -> None:
        pass

    def update(self) -> None:
        pass

    def update_animation(self, delta_time: float = 1 / 60) -> None:
        pass


class Sound:
    """Stub Sound class."""

    def __init__(self, file_name: str, streaming: bool = False, **kwargs: Any) -> None:
        self.file_name = file_name
        self.streaming = streaming

    def play(self, **kwargs: Any) -> None:
        pass


class Text:
    """Stub Text class."""

    def __init__(self, text: str, start_x: float = 0.0, start_y: float = 0.0, *args: Any, **kwargs: Any) -> None:
        if "x" in kwargs:
            start_x = kwargs["x"]
        if "y" in kwargs:
            start_y = kwargs["y"]
        self.text = text
        self.x = float(start_x)
        self.y = float(start_y)
        self.rotation = 0.0

    @property
    def position(self) -> Tuple[float, float]:
        return (self.x, self.y)

    @position.setter
    def position(self, value: Tuple[float, float]) -> None:
        self.x = float(value[0])
        self.y = float(value[1])

    def draw(self) -> None:
        pass


class Camera:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def use(self) -> None:
        pass

    def move_to(self, *args: Any, **kwargs: Any) -> None:
        pass

    def resize(self, *args: Any, **kwargs: Any) -> None:
        pass


class Camera2D(Camera):
    pass


camera = SimpleNamespace(Camera2D=Camera2D)


def load_texture(file_name: str, **kwargs: Any) -> Texture:
    return Texture(file_name)


def load_spritesheet(
    file_name: str,
    sprite_width: int,
    sprite_height: int,
    columns: int,
    count: int,
    margin: int = 0,
    **kwargs: Any,
) -> List[Texture]:
    count = max(0, int(count))
    return [Texture(f"{file_name}:{idx}", width=sprite_width, height=sprite_height) for idx in range(count)]


def make_soft_square_texture(size: int, color: Tuple[int, int, int], alpha: int, border: int) -> Texture:
    return Texture("soft_square", width=size, height=size)


def make_circle_texture(size: int, color: Tuple[int, int, int]) -> Texture:
    return Texture("circle", width=size, height=size)


def start_render() -> None:
    pass


def set_background_color(color_value: Tuple[int, int, int]) -> None:
    pass


def draw_text(
    text: str,
    start_x: float,
    start_y: float,
    color_value: Tuple[int, int, int],
    font_size: float = 12,
    **kwargs: Any,
) -> None:
    pass


def draw_rectangle_filled(
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    color_value: Tuple[int, int, int],
    **kwargs: Any,
) -> None:
    pass


def draw_rectangle_outline(
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    color_value: Tuple[int, int, int],
    border_width: float = 1,
    **kwargs: Any,
) -> None:
    pass


def draw_circle_filled(
    center_x: float,
    center_y: float,
    radius: float,
    color_value: Tuple[int, int, int],
    **kwargs: Any,
) -> None:
    pass


def draw_circle_outline(
    center_x: float,
    center_y: float,
    radius: float,
    color_value: Tuple[int, int, int],
    border_width: float = 1,
    **kwargs: Any,
) -> None:
    pass


def draw_line(
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    color_value: Tuple[int, int, int],
    line_width: float = 1,
    **kwargs: Any,
) -> None:
    pass


def draw_line_strip(points: Sequence[Tuple[float, float]], color_value: Tuple[int, int, int], line_width: float = 1) -> None:
    pass


def draw_lrbt_rectangle_filled(left: float, right: float, bottom: float, top: float, color_value: Tuple[int, int, int]) -> None:
    pass


def draw_lrbt_rectangle_outline(
    left: float,
    right: float,
    bottom: float,
    top: float,
    color_value: Tuple[int, int, int],
    border_width: float = 1,
) -> None:
    pass


def draw_lbwh_rectangle_outline(
    left: float,
    bottom: float,
    width: float,
    height: float,
    color_value: Tuple[int, int, int],
    border_width: float = 1,
) -> None:
    pass


def draw_lbwh_rectangle_filled(
    left: float,
    bottom: float,
    width: float,
    height: float,
    color_value: Tuple[int, int, int],
) -> None:
    pass


def draw_texture_rectangle(
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    texture: Texture,
    **kwargs: Any,
) -> None:
    pass


def draw_polygon_filled(points: Sequence[Tuple[float, float]], color_value: Tuple[int, int, int], **kwargs: Any) -> None:
    pass


def draw_lrwh_rectangle_textured(
    bottom_left_x: float,
    bottom_left_y: float,
    width: float,
    height: float,
    texture: Texture,
    **kwargs: Any,
) -> None:
    pass


def check_for_collision(sprite_a: Sprite, sprite_b: Sprite) -> bool:
    return False


def check_for_collision_with_list(sprite: Sprite, sprite_list: Iterable[Sprite]) -> List[Sprite]:
    return []


def get_sprites_at_point(point: Tuple[float, float], sprite_list: Iterable[Sprite]) -> List[Sprite]:
    return []


def get_fps() -> float:
    return 0.0


def get_window() -> Any:
    return None


def run() -> None:
    pass


def close_window() -> None:
    pass


def play_sound(sound: Sound, **kwargs: Any) -> None:
    pass


def set_mouse_cursor(cursor: Any) -> None:
    pass


def set_system_cursor(cursor: Any) -> None:
    pass


def get_game_controllers() -> List[Any]:
    return []
