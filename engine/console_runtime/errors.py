from __future__ import annotations


def single_line_error(text: str) -> str:
    """Normalize error text into a deterministic single-line string."""
    cleaned = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return ""
    return " ".join(cleaned.split())

