from __future__ import annotations


def normalize_scene_path(value: str) -> str:
    """Normalize scene-path strings for presentation/reporting.

    - Always uses forward slashes.
    - Strips redundant leading "./" segments.
    - Does not perform any filesystem resolution.
    """
    text = str(value or "").strip()
    if not text:
        return text
    text = text.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text

