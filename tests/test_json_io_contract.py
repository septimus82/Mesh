from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from engine import json_io


def test_dumps_stable_is_deterministic_and_sorted() -> None:
    payload = {"b": 1, "a": 2}
    first = json_io.dumps_stable(payload)
    second = json_io.dumps_stable(payload)
    assert first == second
    assert first.index('"a"') < first.index('"b"')


def test_write_json_atomic_roundtrip_utf8(tmp_path) -> None:
    payload = {"name": "ÅÄÖ"}
    path = tmp_path / "payload.json"
    json_io.write_json_atomic(path, payload)
    assert json_io.read_json(path) == payload


def test_write_json_atomic_formatting(tmp_path) -> None:
    payload = {"a": 1, "b": {"c": 2}}
    path = tmp_path / "format.json"
    json_io.write_json_atomic(path, payload)
    text = path.read_text(encoding="utf-8")
    assert "\r" not in text
    assert text.endswith("\n")
    assert "\n  \"a\": 1" in text
    assert ": " in text


def test_write_json_atomic_replaces(tmp_path) -> None:
    path = tmp_path / "replace.json"
    json_io.write_json_atomic(path, {"b": 2})
    json_io.write_json_atomic(path, {"a": 1})
    assert json_io.read_json(path) == {"a": 1}
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_write_json_atomic_success_leaves_no_temp_sibling(tmp_path) -> None:
    path = tmp_path / "success.json"

    json_io.write_json_atomic(path, {"ok": True})

    assert json_io.read_json(path) == {"ok": True}
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_write_json_atomic_failed_write_cleans_temp_and_preserves_destination(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "payload.json"
    path.write_text('{"sentinel": 1}\n', encoding="utf-8")
    real_open = open
    tmp_path_expected = path.with_suffix(path.suffix + ".tmp")

    class _ExplodingWriter:
        def __init__(self, handle) -> None:
            self._handle = handle

        def __enter__(self):
            self._handle.__enter__()
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return self._handle.__exit__(exc_type, exc, tb)

        def write(self, _text: str) -> int:
            raise OSError("boom")

        def flush(self) -> None:
            self._handle.flush()

        def fileno(self) -> int:
            return self._handle.fileno()

    def _open_with_failing_write(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        if file == tmp_path_expected and "w" in mode:
            return _ExplodingWriter(handle)
        return handle

    monkeypatch.setattr(json_io, "open", _open_with_failing_write, raising=False)

    with pytest.raises(OSError, match="boom"):
        json_io.write_json_atomic(path, {"updated": True})

    assert path.read_text(encoding="utf-8") == '{"sentinel": 1}\n'
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_coerce_path_rejects_non_pathlike() -> None:
    with pytest.raises(TypeError, match="expected str or Path"):
        json_io._coerce_path(MagicMock())
    with pytest.raises(TypeError, match="expected str or Path"):
        json_io._coerce_path(object())


def test_write_json_atomic_rejects_non_pathlike() -> None:
    with pytest.raises(TypeError, match="expected str or Path"):
        json_io.write_json_atomic(MagicMock(), {"any": "payload"})
