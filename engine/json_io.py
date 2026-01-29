from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _coerce_path(path: str | Path) -> Path:
    return path if isinstance(path, Path) else Path(path)


def dumps_stable(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
    )


def write_text_atomic(path: str | Path, text: str, *, encoding: str = "utf-8") -> None:
    target = _coerce_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    with open(tmp_path, "w", encoding=encoding, newline="\n") as handle:
        handle.write(text)
    os.replace(tmp_path, target)


def write_json_atomic(path: str | Path, payload: Any, *, trailing_newline: bool = True) -> None:
    text = dumps_stable(payload)
    if trailing_newline and not text.endswith("\n"):
        text += "\n"
    write_text_atomic(path, text, encoding="utf-8")


def read_json(path: str | Path) -> Any:
    target = _coerce_path(path)
    with open(target, "r", encoding="utf-8") as handle:
        return json.load(handle)
