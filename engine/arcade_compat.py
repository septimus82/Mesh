from __future__ import annotations

from typing import Any


def capture_active_framebuffer(ctx: Any) -> Any | None:
    return getattr(ctx, "active_framebuffer", None)


def activate_framebuffer(
    fbo: Any,
    *,
    backend: str = "auto",
) -> tuple[str, Any | None]:
    """
    Bind a framebuffer across Arcade API variants.

    Returns ``(backend_name, activation_cm)`` where backend_name is one of:
    ``"fbo.use"``, ``"fbo.activate"``, ``"none"``.
    """
    if backend not in ("auto", "fbo.use", "fbo.activate"):
        raise ValueError(f"unsupported framebuffer backend selector: {backend}")

    if backend in ("auto", "fbo.use"):
        use = getattr(fbo, "use", None)
        if callable(use):
            use()
            return ("fbo.use", None)
        if backend == "fbo.use":
            return ("none", None)

    if backend in ("auto", "fbo.activate"):
        activate = getattr(fbo, "activate", None)
        if callable(activate):
            cm = activate()
            enter = getattr(cm, "__enter__", None) if cm is not None else None
            if callable(enter):
                enter()
            return ("fbo.activate", cm)
        if backend == "fbo.activate":
            return ("none", None)

    return ("none", None)


def close_framebuffer_activation(activation_cm: Any | None) -> None:
    if activation_cm is None:
        return
    exit_ = getattr(activation_cm, "__exit__", None)
    if callable(exit_):
        try:
            exit_(None, None, None)
        except Exception:  # noqa: BLE001
            pass


def clear_framebuffer(
    ctx: Any,
    fbo: Any,
    red: float,
    green: float,
    blue: float,
    alpha: float,
) -> bool:
    clear_fn = getattr(fbo, "clear", None)
    if callable(clear_fn):
        try:
            clear_fn(float(red), float(green), float(blue), float(alpha))
            return True
        except TypeError:
            try:
                clear_fn()
                return True
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    ctx_clear = getattr(ctx, "clear", None)
    if callable(ctx_clear):
        try:
            ctx_clear(float(red), float(green), float(blue), float(alpha))
            return True
        except Exception:  # noqa: BLE001
            return False
    return False


def restore_framebuffer(ctx: Any, previous_fbo: Any | None) -> None:
    try:
        screen = getattr(ctx, "screen", None)
        screen_use = getattr(screen, "use", None) if screen is not None else None
        if callable(screen_use):
            screen_use()
            return
    except Exception:  # noqa: BLE001
        pass

    if previous_fbo is None:
        return
    prev_use = getattr(previous_fbo, "use", None)
    if callable(prev_use):
        try:
            prev_use()
        except Exception:  # noqa: BLE001
            pass

