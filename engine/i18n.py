"""Minimal localization helpers for Mesh Engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .paths import resolve_path

_ACTIVE_LOCALE: str = "en"
_LOCALE_CACHE: Dict[str, Dict[str, str]] = {}


def set_locale(locale_code: str) -> None:
    """Set the active locale (best-effort)."""
    code = str(locale_code or "").strip().lower()
    if not code:
        code = "en"
    global _ACTIVE_LOCALE
    _ACTIVE_LOCALE = code


def _load_locale(code: str) -> Dict[str, str]:
    code = str(code or "").strip().lower() or "en"
    cached = _LOCALE_CACHE.get(code)
    if cached is not None:
        return cached
    path = resolve_path(f"locales/{code}.json")
    data: Dict[str, str] = {}
    try:
        if Path(path).exists():
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = {
                    str(k): str(v)
                    for k, v in raw.items()
                    if isinstance(k, str)
                }
    except Exception:  # noqa: BLE001  # REASON: malformed locale files should fall back to an empty translation table
        data = {}
    _LOCALE_CACHE[code] = data
    return data


def tr(key: str, **fmt: Any) -> str:
    """Translate a key using the active locale."""
    raw_key = str(key or "")
    data = _load_locale(_ACTIVE_LOCALE)
    text = data.get(raw_key)
    if text is None and _ACTIVE_LOCALE != "en":
        text = _load_locale("en").get(raw_key)
    if text is None:
        return raw_key
    if fmt:
        try:
            return text.format(**fmt)
        except Exception:  # noqa: BLE001  # REASON: translation formatting failures should fall back to the untranslated template text
            return text
    return text
