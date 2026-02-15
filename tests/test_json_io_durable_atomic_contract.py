from __future__ import annotations

from pathlib import Path

from engine import json_io


def test_write_text_atomic_non_durable_does_not_require_fsync(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fsync_calls: list[int] = []

    def _fsync(fd: int) -> None:
        fsync_calls.append(fd)
        raise AssertionError("fsync must not be called when durable=False")

    monkeypatch.setattr(json_io.os, "fsync", _fsync)

    target = tmp_path / "plain.txt"
    json_io.write_text_atomic(target, "alpha\nbeta\n", durable=False)
    assert target.read_text(encoding="utf-8") == "alpha\nbeta\n"
    assert fsync_calls == []


def test_write_text_atomic_durable_fsyncs_file_and_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fsync_calls: list[int] = []
    open_calls: list[tuple[str, int]] = []
    close_calls: list[int] = []
    dir_fd = 4242

    def _fsync(fd: int) -> None:
        fsync_calls.append(int(fd))

    def _open(path: str, flags: int) -> int:
        open_calls.append((str(path), int(flags)))
        return dir_fd

    def _close(fd: int) -> None:
        close_calls.append(int(fd))

    monkeypatch.setattr(json_io.os, "fsync", _fsync)
    monkeypatch.setattr(json_io.os, "open", _open)
    monkeypatch.setattr(json_io.os, "close", _close)

    target = tmp_path / "durable.json"
    json_io.write_text_atomic(target, '{"k":"v"}\n', durable=True)

    assert target.read_text(encoding="utf-8") == '{"k":"v"}\n'
    assert len(open_calls) == 1
    assert open_calls[0][0] == str(target.parent)
    assert dir_fd in fsync_calls
    assert dir_fd in close_calls
    assert len(fsync_calls) >= 2


def test_write_json_atomic_durable_replaces_with_final_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(json_io.os, "fsync", lambda _fd: None)
    target = tmp_path / "payload.json"

    json_io.write_json_atomic(target, {"value": 1}, durable=True)
    json_io.write_json_atomic(target, {"value": 2}, durable=True)

    assert json_io.read_json(target) == {"value": 2}
    assert not target.with_suffix(".json.tmp").exists()


def test_write_text_atomic_durable_swallow_dir_fsync_open_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(json_io.os, "fsync", lambda _fd: None)

    def _open_raises(_path: str, _flags: int) -> int:
        raise OSError("dir fsync unsupported")

    monkeypatch.setattr(json_io.os, "open", _open_raises)

    target = tmp_path / "fallback.txt"
    json_io.write_text_atomic(target, "ok\n", durable=True)
    assert target.read_text(encoding="utf-8") == "ok\n"
