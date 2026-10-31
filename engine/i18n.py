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


def _read_table(path: Any) -> Dict[str, str]:
    try:
        if path is not None and Path(path).exists():
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {str(k): str(v) for k, v in raw.items() if isinstance(k, str)}
    except Exception:  # noqa: BLE001  # REASON: malformed locale files should fall back to an empty translation table
        return {}
    return {}


def _load_locale(code: str) -> Dict[str, str]:
    """The engine's interface text for ``code``, with the game's own ``locales/<code>.json`` laid over it key by key:
    a game's file can add or change messages without listing the engine's (Milestone 21B.1: a game has no
    ``locales/`` of its own, or only some keys, and menus showed raw keys).

    The engine's text is its first bundled copy that isn't the game's own file (H9.2: an exported game's folder is
    both the game's and the engine's, so its ``locales/`` are the game's and the engine's copy is in
    ``share/mesh-engine/locales``; before, exports had neither and showed raw keys)."""
    code = str(code or "").strip().lower() or "en"
    cached = _LOCALE_CACHE.get(code)
    if cached is not None:
        return cached
    from .repo_root import bundled_data_roots  # noqa: PLC0415

    game_path = Path(resolve_path(f"locales/{code}.json")).resolve()
    engine_path = next((p for p in (root / "locales" / f"{code}.json" for root in bundled_data_roots())
                        if p.is_file() and p.resolve() != game_path), None)
    data = _read_table(engine_path)
    data.update(_read_table(game_path))
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
