from __future__ import annotations


def try_copy_to_clipboard(text: str) -> bool:
    """
    Best-effort clipboard copy.

    Must be safe in headless/test environments: all errors are swallowed.
    """
    value = str(text or "")
    if not value:
        return False

    try:
        import warnings  # noqa: PLC0415
        import tkinter  # noqa: PLC0415

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            root = tkinter.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(value)
        root.update()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001
        return False

