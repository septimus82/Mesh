from __future__ import annotations

import subprocess

from mesh_cli.release_notes import (
    format_release_notes_text,
    generate_release_notes,
    release_notes_to_dict,
)


def _cp(args: list[str], *, code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=code, stdout=out, stderr=err)


def test_generate_release_notes_is_stable_in_deterministic_mode(monkeypatch) -> None:
    def _fake_run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args == ["--version"]:
            return _cp(args, out="git version 2.45.0\n")
        if args == ["describe", "--tags", "--abbrev=0"]:
            return _cp(args, out="v0.3.9\n")
        if args == ["log", "--no-merges", "--pretty=%s", "v0.3.9..HEAD"]:
            return _cp(args, out="feat: add release notes\nfix: repair manifest seal\n")
        if args == ["rev-parse", "HEAD"]:
            return _cp(args, out="abc123\n")
        if args == ["status", "--porcelain"]:
            return _cp(args, out="")
        return _cp(args, code=1, err="unsupported")

    monkeypatch.setattr("mesh_cli.release_notes._run_git", _fake_run_git)

    notes_a = generate_release_notes(deterministic=True, since=None, until=None)
    notes_b = generate_release_notes(deterministic=True, since=None, until=None)

    assert release_notes_to_dict(notes_a) == release_notes_to_dict(notes_b)
    assert format_release_notes_text(notes_a) == format_release_notes_text(notes_b)


def test_generate_release_notes_section_order_is_fixed(monkeypatch) -> None:
    def _fake_run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args == ["--version"]:
            return _cp(args, out="git version 2.45.0\n")
        if args == ["describe", "--tags", "--abbrev=0"]:
            return _cp(args, out="v0.3.9\n")
        if args == ["log", "--no-merges", "--pretty=%s", "v0.3.9..HEAD"]:
            return _cp(
                args,
                out=(
                    "docs: update ci guide\n"
                    "feat: add quest\n"
                    "fix: handle null flags\n"
                    "test: add coverage\n"
                    "chore: tune pipeline\n"
                    "misc commit title\n"
                ),
            )
        if args == ["rev-parse", "HEAD"]:
            return _cp(args, out="abc123\n")
        if args == ["status", "--porcelain"]:
            return _cp(args, out="")
        return _cp(args, code=1)

    monkeypatch.setattr("mesh_cli.release_notes._run_git", _fake_run_git)
    notes = generate_release_notes(deterministic=True, since=None, until=None)
    titles = [section.title for section in notes.sections]
    assert titles == ["Features", "Fixes", "Tooling", "Tests", "Docs", "Other"]


def test_generate_release_notes_gracefully_handles_missing_git(monkeypatch) -> None:
    monkeypatch.setattr("mesh_cli.release_notes._run_git", lambda _args: None)
    notes = generate_release_notes(deterministic=True, since=None, until=None)
    payload = release_notes_to_dict(notes)
    assert payload["generated_mode"] == "deterministic"
    assert payload["sections"][0]["title"] == "Other"
    assert payload["sections"][0]["items"] == ["Git metadata unavailable; no commit log."]


def test_generate_release_notes_classifies_conventional_prefixes(monkeypatch) -> None:
    def _fake_run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args == ["--version"]:
            return _cp(args, out="git version 2.45.0\n")
        if args == ["describe", "--tags", "--abbrev=0"]:
            return _cp(args, out="v0.3.9\n")
        if args == ["log", "--no-merges", "--pretty=%s", "v0.3.9..HEAD"]:
            return _cp(
                args,
                out=(
                    "feat: add episode one intro\n"
                    "fix(renderer): resolve shadow bleed\n"
                    "perf: speed up pathfinding\n"
                    "refactor!: split release module\n"
                    "chore: harden ci\n"
                    "test: add release notes tests\n"
                    "docs: add release docs\n"
                    "ship release candidate\n"
                ),
            )
        if args == ["rev-parse", "HEAD"]:
            return _cp(args, out="abc123\n")
        if args == ["status", "--porcelain"]:
            return _cp(args, out="")
        return _cp(args, code=1)

    monkeypatch.setattr("mesh_cli.release_notes._run_git", _fake_run_git)
    notes = generate_release_notes(deterministic=True, since=None, until=None)
    by_section = {section.title: section.items for section in notes.sections}
    assert by_section["Features"] == ["add episode one intro"]
    assert by_section["Fixes"] == ["resolve shadow bleed"]
    assert by_section["Performance"] == ["speed up pathfinding"]
    assert by_section["Refactor"] == ["split release module"]
    assert by_section["Tooling"] == ["harden ci"]
    assert by_section["Tests"] == ["add release notes tests"]
    assert by_section["Docs"] == ["add release docs"]
    assert by_section["Other"] == ["ship release candidate"]

