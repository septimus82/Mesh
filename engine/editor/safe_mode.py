from __future__ import annotations

import os

_SAFE_MODE_ENV = "MESH_SAFE_MODE"


def is_safe_mode_enabled() -> bool:
    value = str(os.environ.get(_SAFE_MODE_ENV, "") or "").strip()
    return value == "1"
