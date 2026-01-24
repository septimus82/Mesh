from __future__ import annotations

import hashlib
import json
from typing import Any


def normalize_floats(obj: Any, decimals: int) -> Any:
    if isinstance(obj, dict):
        return {key: normalize_floats(value, decimals) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [normalize_floats(value, decimals) for value in obj]
    if isinstance(obj, bool) or obj is None:
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        value = round(obj, decimals)
        if value == 0.0:
            value = 0.0
        return value
    return obj


def canonical_json_bytes(obj: Any) -> bytes:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_payload(payload: dict[str, Any], *, decimals: int = 6) -> str:
    normalized = normalize_floats(payload, decimals)
    return sha256_hex(canonical_json_bytes(normalized))
