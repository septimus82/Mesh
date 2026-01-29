from __future__ import annotations

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
