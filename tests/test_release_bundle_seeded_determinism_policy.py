from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

from mesh_cli.release_bundle import DEFAULT_CAMPAIGN, DEFAULT_SEED, handle


_WINDOWS_ABS_RE = re.compile(r"[A-Za-z]:[\\/]")
_UNIX_ABS_RE = re.compile(r"(^|[\\s\"'])/(home|users|tmp|var|etc)/", re.IGNORECASE)
_HOST_KEYS = {"cwd", "home", "host", "hostname", "machine", "repo_root", "user", "username"}


def _make_args(**overrides: Any) -> argparse.Namespace:
    data: dict[str, Any] = {
        "command": "release",
        "release_command": "bundle",
        "out": "release_bundle.zip",
        "seed": DEFAULT_SEED,
        "campaign": DEFAULT_CAMPAIGN,
        "report_format": "text",
        "quiet": True,
        "deterministic_timestamp": None,
    }
    data.update(overrides)
    return argparse.Namespace(**data)


def _fake_step_stable(name: str):
    def _step(work_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
        out = work_dir / name
        out.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "name": name,
            "seed": seed,
            "campaign": campaign,
            "summary": "stable",
        }
        (out / f"{name}_report.json").write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        (out / f"{name}_report.txt").write_text("stable report\n", encoding="utf-8")
        return 0, {"dir": f"{name}/"}

    return name, _step


def _find_host_keys(value: Any, *, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value.keys(), key=str):
            key_str = str(key)
            next_path = f"{path}.{key_str}" if path else key_str
            if key_str.lower() in _HOST_KEYS:
                found.append(next_path)
            found.extend(_find_host_keys(value[key], path=next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_find_host_keys(item, path=f"{path}[{index}]"))
    return found


def test_seeded_bundle_is_byte_identical(tmp_path: Path, monkeypatch) -> None:
    pipeline = [_fake_step_stable("alpha"), _fake_step_stable("beta")]
    monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", pipeline)
    monkeypatch.setattr(
        "mesh_cli.release_bundle._write_release_notes_files",
        lambda work_dir, since=None, until="HEAD": (
            (work_dir / "release_notes.json").write_text('{"notes":"stable"}\n', encoding="utf-8"),
            (work_dir / "release_notes.txt").write_text("stable notes\n", encoding="utf-8"),
        ),
    )

    zip_a = tmp_path / "a.zip"
    zip_b = tmp_path / "b.zip"
    assert handle(_make_args(out=str(zip_a), seed=123, quiet=True)) == 0
    assert handle(_make_args(out=str(zip_b), seed=123, quiet=True)) == 0

    bytes_a = zip_a.read_bytes()
    bytes_b = zip_b.read_bytes()
    assert hashlib.sha256(bytes_a).hexdigest() == hashlib.sha256(bytes_b).hexdigest()
    assert bytes_a == bytes_b


def test_seeded_bundle_reports_have_no_absolute_paths(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path.cwd().resolve()

    def _noisy_report_step(work_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
        out = work_dir / "reporting"
        out.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "repo_root": str(repo_root),
            "host": "host-a",
            "summary": {"path": str(repo_root / "nested" / "thing.txt")},
        }
        (out / "artifact_report.json").write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        (out / "artifact_report.txt").write_text(
            f"repo={repo_root}\npath={repo_root / 'nested' / 'thing.txt'}\n",
            encoding="utf-8",
        )
        return 0, {"dir": "reporting/"}

    monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", [("reporting", _noisy_report_step)])
    monkeypatch.setattr(
        "mesh_cli.release_bundle._write_release_notes_files",
        lambda work_dir, since=None, until="HEAD": None,
    )

    zip_path = tmp_path / "clean.zip"
    assert handle(_make_args(out=str(zip_path), seed=123, quiet=True)) == 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in sorted(zf.namelist()):
            lower = name.lower()
            if not (lower.endswith(".json") or lower.endswith(".txt")):
                continue
            if not any(token in lower for token in ("report", "audit", "manifest")):
                continue
            text = zf.read(name).decode("utf-8", errors="ignore")
            assert not _WINDOWS_ABS_RE.search(text), f"absolute windows path leaked in {name}"
            assert not _UNIX_ABS_RE.search(text), f"absolute unix path leaked in {name}"
            if lower.endswith(".json"):
                payload = json.loads(text)
                host_hits = _find_host_keys(payload)
                assert not host_hits, f"host-specific keys leaked in {name}: {host_hits}"


def test_quiet_suppresses_info_logs(tmp_path: Path, monkeypatch, capsys) -> None:
    logger = logging.getLogger("engine.release_bundle_policy_test")
    handler = logging.StreamHandler(sys.stderr)
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    def _chatty_step(work_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
        out = work_dir / "chatty"
        out.mkdir(parents=True, exist_ok=True)
        logger.info("chatty info from subsystem")
        print("[Mesh][Quests] Quest 'test_quest' has no stages; skipping")
        (out / "chatty_report.json").write_text('{"ok": true}\n', encoding="utf-8")
        return 0, {"dir": "chatty/"}

    monkeypatch.setattr("mesh_cli.release_bundle.BUNDLE_PIPELINE", [("chatty", _chatty_step)])
    monkeypatch.setattr(
        "mesh_cli.release_bundle._write_release_notes_files",
        lambda work_dir, since=None, until="HEAD": None,
    )

    zip_path = tmp_path / "quiet.zip"
    try:
        assert handle(_make_args(out=str(zip_path), seed=123, quiet=True)) == 0
    finally:
        logger.handlers.clear()

    captured = capsys.readouterr()
    combined = f"{captured.out}\n{captured.err}"
    assert "INFO:" not in combined
    assert "chatty info from subsystem" not in combined
    assert "[Mesh][Quests]" not in combined
