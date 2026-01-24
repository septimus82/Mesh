"""
Arcade Stub for Headless Testing.
This module provides a stub implementation of the arcade library for use in headless environments
where the real arcade library cannot be installed or run (e.g. CI/CD pipelines without display).
"""

from types import SimpleNamespace
from typing import Any, Tuple, Optional, List

# ----------------------------------------------------------------------------
# CONSTANTS & NAMESPACES
# ----------------------------------------------------------------------------

# Colors
color = SimpleNamespace(
    WHITE=(255, 255, 255),
    BLACK=(0, 0, 0),
    RED=(255, 0, 0),
    GREEN=(0, 255, 0),
    BLUE=(0, 0, 255),
    YELLOW=(255, 255, 0),
    CYAN=(0, 255, 255),
    MAGENTA=(255, 0, 255),
    TRANSPARENT_BLACK=(0, 0, 0, 0),
    GRAY=(128, 128, 128),
    DARK_GRAY=(169, 169, 169),
    LIGHT_GRAY=(211, 211, 211),
)

# Keys (GLFW Standards / Arcade Standards)
key = SimpleNamespace(
    # Functions
    F1=65470, F2=65471, F3=65472, F4=65473, F5=65474, F6=65475,
    F7=65476, F8=65477, F9=65478, F10=65479, F11=65480, F12=65481,
    
    # Arrows
    UP=65362, DOWN=65364, LEFT=65361, RIGHT=65363,
    
    # Modifiers
    LSHIFT=65505, RSHIFT=65506, LCTRL=65507, RCTRL=65508, LALT=65513, RALT=65514,
    MOD_SHIFT=1, MOD_CTRL=2, MOD_ALT=4,
    
    # Special
    ENTER=65293, RETURN=65293, ESCAPE=65307, BACKSPACE=65288, TAB=65289, SPACE=32,
    DELETE=65535, HOME=65360, END=65367, PAGEUP=65365, PAGEDOWN=65366, PAGE_UP=65365, PAGE_DOWN=65366,
    
    # Numbers
    KEY_0=48, KEY_1=49, KEY_2=50, KEY_3=51, KEY_4=52,
    KEY_5=53, KEY_6=54, KEY_7=55, KEY_8=56, KEY_9=57,
    
    # Letters
    A=97, B=98, C=99, D=100, E=101, F=102, G=103, H=104, I=105, J=106,
    K=107, L=108, M=109, N=110, O=111, P=112, Q=113, R=114, S=115, T=116,
    U=117, V=118, W=119, X=120, Y=121, Z=122,
    
    # Symbols
    GRAVE=96, MINUS=45, EQUAL=61, LBRACKET=91, RBRACKET=93, BACKSLASH=92,
    SEMICOLON=59, APOSTROPHE=39, COMMA=44, PERIOD=46, SLASH=47
)

# Mouse buttons (pyglet/arcade standards)
MOUSE_BUTTON_LEFT = 1
MOUSE_BUTTON_MIDDLE = 2
MOUSE_BUTTON_RIGHT = 4

# System mouse cursors (subset)
class SystemMouseCursor:
    DEFAULT = "default"
    HAND = "hand"
    MOVE = "move"
    SIZE_WE = "size_we"
    SIZE_NS = "size_ns"
    CROSSHAIR = "crosshair"

# GL Constants
gl = SimpleNamespace(
    GL_NEAREST=0,
    GL_LINEAR=1,
)

# ----------------------------------------------------------------------------
# CLASSES
# ----------------------------------------------------------------------------

class Window:
    """Stub Window class."""
    def __init__(self, width: int = 800, height: int = 600, title: str = "Stub", **kwargs):
        self.width = width
        self.height = height
        self.title = title
        self.ctx = SimpleNamespace()
        
    def show_view(self, view: Any):
        pass
        
    def run(self):
        pass
        
    def set_mouse_visible(self, visible: bool):
        pass
        
    def set_location(self, x: int, y: int):
        pass

    def set_mouse_cursor(self, cursor: Any) -> None:
        pass

class View:
    """Stub View class."""
    def __init__(self):
        self.window = None
        
    def on_show(self):
        pass
        
    def on_show_view(self):
        pass
        
    def on_hide_view(self):
        pass
        
    def on_draw(self):
        pass
        
    def on_update(self, delta_time: float):
        pass
        
    def on_key_press(self, symbol: int, modifiers: int):
        pass
        
    def on_key_release(self, symbol: int, modifiers: int):
        pass
        
    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        pass

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        pass

class Sprite:
    """Stub Sprite class."""
    def __init__(self, filename: str = None, scale: float = 1.0, **kwargs):
        self.position = (0, 0)
        self.center_x = 0.0
        self.center_y = 0.0
        self.change_x = 0.0
        self.change_y = 0.0
        self.angle = 0.0
        self.change_angle = 0.0
        self.scale = scale
        self.width = 10.0 * scale
        self.height = 10.0 * scale
        self.alpha = 255
        self.color = (255, 255, 255)
        self.visible = True
        self.texture = None
        
    def draw(self):
        pass
        
    def update(self):
        pass
        
    def kill(self):
        pass
        
    def remove_from_sprite_lists(self):
        pass
        
    def collides_with_list(self, sprite_list: "SpriteList") -> List["Sprite"]:
        return []

class SpriteList(list):
    """Stub SpriteList class."""
    def __init__(self, use_spatial_hash=False):
        super().__init__()
        self.use_spatial_hash = use_spatial_hash
        
    def draw(self, **kwargs):
        pass
        
    def update(self):
        pass
        
    def update_animation(self, delta_time: float = 1/60):
        pass

class Texture:
    """Stub Texture class."""
    def __init__(self, name: str, image=None, **kwargs):
        self.name = name
        self.width = 10
        self.height = 10

class Text:
    """Stub Text class."""
    def __init__(self, text: str, start_x: float = 0.0, start_y: float = 0.0, **kwargs):
        if "x" in kwargs:
            start_x = kwargs["x"]
        if "y" in kwargs:
            start_y = kwargs["y"]
        self.text = text
        self.x = start_x
        self.y = start_y

# ----------------------------------------------------------------------------
# FUNCTIONS
# ----------------------------------------------------------------------------

def load_texture(file_name: str, **kwargs) -> Texture:
    return Texture(file_name)

def start_render():
    pass

def set_background_color(color: Tuple[int, int, int]):
    pass

def draw_text(text: str, start_x: float, start_y: float, color: Tuple[int, int, int], font_size: float = 12, **kwargs):
    pass

def draw_rectangle_filled(center_x: float, center_y: float, width: float, height: float, color: Tuple[int, int, int], **kwargs):
    pass

def draw_rectangle_outline(center_x: float, center_y: float, width: float, height: float, color: Tuple[int, int, int], border_width: float = 1, **kwargs):
    pass

def draw_circle_filled(center_x: float, center_y: float, radius: float, color: Tuple[int, int, int], **kwargs):
    pass

def draw_line(start_x: float, start_y: float, end_x: float, end_y: float, color: Tuple[int, int, int], line_width: float = 1, **kwargs):
    pass

def set_mouse_cursor(cursor: Any) -> None:
    pass

def draw_lrwh_rectangle_textured(bottom_left_x: float, bottom_left_y: float, width: float, height: float, texture: Texture, **kwargs):
    pass

def draw_polygon_filled(points: List[Tuple[float, float]], color: Tuple[int, int, int], **kwargs):
    pass

def schedule(function, interval):
    pass

def unschedule(function):
    pass
