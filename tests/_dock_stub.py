from __future__ import annotations

from engine.editor.editor_dock_model import DockStateSnapshot
from engine.editor.editor_shell_layout import DOCK_WIDTH, resolve_effective_dock_widths


class DockStub:
    def __init__(
        self,
        left_tab: str = "Outliner",
        right_tab: str = "Inspector",
        left_w: int | None = None,
        right_w: int | None = None,
        left_collapsed: bool = False,
        right_collapsed: bool = False,
        viewport_maximized: bool = False,
    ) -> None:
        self.left_tab = left_tab
        self.right_tab = right_tab
        self.rev = 0
        self._left_w = int(DOCK_WIDTH if left_w is None else left_w)
        self._right_w = int(DOCK_WIDTH if right_w is None else right_w)
        self._left_collapsed = bool(left_collapsed)
        self._right_collapsed = bool(right_collapsed)
        self._viewport_maximized = bool(viewport_maximized)
        self._drag_active: str | None = None
        self._hover_tab: tuple[str, str] | None = None
        self._hover_tab_rect: tuple[float, float, float, float] | None = None

    def get_snapshot(self) -> DockStateSnapshot:
        return DockStateSnapshot(
            left_tab=self.left_tab,
            right_tab=self.right_tab,
            rev=self.rev,
        )

    def set_left_tab(self, tab: str, *, force: bool = False) -> None:  # noqa: ARG002
        self.left_tab = str(tab)
        self.rev += 1

    def set_right_tab(self, tab: str, *, force: bool = False) -> None:  # noqa: ARG002
        self.right_tab = str(tab)
        self.rev += 1

    def set_active_tab(self, dock: str, tab: str, *, force: bool = False) -> None:  # noqa: ARG002
        if dock == "left":
            self.set_left_tab(tab, force=force)
        elif dock == "right":
            self.set_right_tab(tab, force=force)

    def apply_tab_change(self, _host: object | None, dock: str, tab: str) -> bool:
        self.set_active_tab(dock, tab, force=True)
        if dock == "left":
            self.set_left_collapsed(False)
        elif dock == "right":
            self.set_right_collapsed(False)
        return True

    def get_left_width(self) -> int:
        return self._left_w

    def set_left_width(self, value: int) -> None:
        self._left_w = int(value)

    def get_right_width(self) -> int:
        return self._right_w

    def set_right_width(self, value: int) -> None:
        self._right_w = int(value)

    def get_left_collapsed(self) -> bool:
        return self._left_collapsed

    def set_left_collapsed(self, value: bool) -> None:
        self._left_collapsed = bool(value)

    def get_right_collapsed(self) -> bool:
        return self._right_collapsed

    def set_right_collapsed(self, value: bool) -> None:
        self._right_collapsed = bool(value)

    def get_viewport_maximized(self) -> bool:
        return self._viewport_maximized

    def set_viewport_maximized(self, value: bool) -> None:
        self._viewport_maximized = bool(value)

    def toggle_left_dock(self, _host: object | None = None) -> None:
        self.set_left_collapsed(not self.get_left_collapsed())

    def toggle_right_dock(self, _host: object | None = None) -> None:
        self.set_right_collapsed(not self.get_right_collapsed())

    def get_drag_active(self) -> str | None:
        return self._drag_active

    def set_drag_active(self, value: str | None) -> None:
        self._drag_active = value

    def begin_drag(self, _host: object | None, which: str, _mouse_x: float) -> bool:
        self._drag_active = str(which)
        return True

    def update_drag(self, _host: object | None, _mouse_x: float, _window_width: int) -> bool:
        return True

    def end_drag(self, _host: object | None) -> bool:
        self._drag_active = None
        return True

    def set_hover_tab(
        self,
        dock: str | None,
        tab: str | None,
        rect: tuple[float, float, float, float] | None,
    ) -> None:
        if dock and tab and rect is not None:
            self._hover_tab = (str(dock), str(tab))
            self._hover_tab_rect = rect
        else:
            self._hover_tab = None
            self._hover_tab_rect = None

    def get_hover_tab(self) -> tuple[str, str] | None:
        return self._hover_tab

    def get_hover_tab_rect(self) -> tuple[float, float, float, float] | None:
        return self._hover_tab_rect

    def get_effective_dock_widths(self, window_w: int) -> tuple[int, int]:
        left_eff, right_eff = resolve_effective_dock_widths(
            left_collapsed=self._left_collapsed,
            right_collapsed=self._right_collapsed,
            viewport_maximized=self._viewport_maximized,
            left_w=self._left_w,
            right_w=self._right_w,
            window_width=int(window_w),
        )
        return (int(left_eff), int(right_eff))


def make_dock_stub(
    left_tab: str = "Outliner",
    right_tab: str = "Inspector",
    left_w: int | None = None,
    right_w: int | None = None,
    left_collapsed: bool = False,
    right_collapsed: bool = False,
    viewport_maximized: bool = False,
) -> DockStub:
    return DockStub(
        left_tab=left_tab,
        right_tab=right_tab,
        left_w=left_w,
        right_w=right_w,
        left_collapsed=left_collapsed,
        right_collapsed=right_collapsed,
        viewport_maximized=viewport_maximized,
    )
