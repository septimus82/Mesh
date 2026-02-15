from __future__ import annotations

import re
import subprocess
import textwrap
from dataclasses import dataclass, field
from typing import Any, Literal

from mesh_cli.version_info import get_tool_version

GeneratedMode = Literal["deterministic", "normal"]

_SECTION_ORDER: tuple[str, ...] = (
    "Features",
    "Fixes",
    "Performance",
    "Refactor",
    "Tooling",
    "Tests",
    "Docs",
    "Other",
)
_PREFIX_TO_SECTION: dict[str, str] = {
    "feat": "Features",
    "fix": "Fixes",
    "perf": "Performance",
    "refactor": "Refactor",
    "chore": "Tooling",
    "test": "Tests",
    "docs": "Docs",
}
_MAX_ITEMS_PER_SECTION = 50
_DEFAULT_LOG_LIMIT = 50
_SUBPROCESS_TIMEOUT_S = 8


@dataclass(frozen=True)
class ReleaseSection:
    title: str
    items: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReleaseNotes:
    version: str
    generated_mode: GeneratedMode
    git_commit: str | None = None
    git_dirty: bool | None = None
    range_from: str | None = None
    range_to: str | None = None
    sections: list[ReleaseSection] = field(default_factory=list)


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_S,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None


def _git_available() -> bool:
    result = _run_git(["--version"])
    return result is not None and result.returncode == 0


def _git_rev_parse(ref: str) -> str | None:
    result = _run_git(["rev-parse", ref])
    if result is None or result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    return value or None


def _git_last_tag() -> str | None:
    result = _run_git(["describe", "--tags", "--abbrev=0"])
    if result is None or result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    return value or None


def _git_dirty() -> bool | None:
    result = _run_git(["status", "--porcelain"])
    if result is None or result.returncode != 0:
        return None
    return bool((result.stdout or "").strip())


def _git_subjects_for_range(range_expr: str) -> list[str] | None:
    result = _run_git(["log", "--no-merges", "--pretty=%s", range_expr])
    if result is None or result.returncode != 0:
        return None
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _git_subjects_recent(limit: int, until: str | None) -> list[str] | None:
    cmd = ["log", "--no-merges", "--pretty=%s", "-n", str(limit)]
    if until:
        cmd.append(until)
    result = _run_git(cmd)
    if result is None or result.returncode != 0:
        return None
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _classify_subject(subject: str) -> tuple[str, str]:
    text = subject.strip()
    if not text:
        return "Other", "empty commit subject"
    match = re.match(r"^([a-z]+)(?:\([^)]+\))?!?:\s*(.+)$", text, flags=re.IGNORECASE)
    if not match:
        return "Other", text
    prefix = match.group(1).lower()
    body = match.group(2).strip() or text
    section = _PREFIX_TO_SECTION.get(prefix, "Other")
    return section, body


def _fallback_notes(mode: GeneratedMode) -> ReleaseNotes:
    return ReleaseNotes(
        version=get_tool_version(),
        generated_mode=mode,
        sections=[ReleaseSection(title="Other", items=["Git metadata unavailable; no commit log."])],
    )


def generate_release_notes(deterministic: bool, since: str | None, until: str | None) -> ReleaseNotes:
    mode: GeneratedMode = "deterministic" if deterministic else "normal"
    if not _git_available():
        return _fallback_notes(mode)

    since_ref = (since or "").strip() or None
    until_ref = (until or "").strip() or "HEAD"
    range_from: str | None = since_ref
    subjects: list[str] | None

    if since_ref:
        subjects = _git_subjects_for_range(f"{since_ref}..{until_ref}")
    else:
        last_tag = _git_last_tag()
        if last_tag:
            range_from = last_tag
            subjects = _git_subjects_for_range(f"{last_tag}..{until_ref}")
        else:
            range_from = None
            subjects = _git_subjects_recent(_DEFAULT_LOG_LIMIT, until_ref)

    if subjects is None:
        return ReleaseNotes(
            version=get_tool_version(),
            generated_mode=mode,
            git_commit=_git_rev_parse(until_ref),
            git_dirty=_git_dirty(),
            range_from=range_from,
            range_to=until_ref,
            sections=[ReleaseSection(title="Other", items=["Git commit range unavailable; no commit log."])],
        )

    grouped: dict[str, list[str]] = {title: [] for title in _SECTION_ORDER}
    for subject in subjects:
        section, item = _classify_subject(subject)
        bucket = grouped.setdefault(section, [])
        if len(bucket) < _MAX_ITEMS_PER_SECTION:
            bucket.append(item)

    if not any(grouped[title] for title in _SECTION_ORDER):
        grouped["Other"] = ["No commits found in selected range."]

    sections: list[ReleaseSection] = []
    for title in _SECTION_ORDER:
        items = grouped.get(title, [])
        if items:
            sections.append(ReleaseSection(title=title, items=items))

    return ReleaseNotes(
        version=get_tool_version(),
        generated_mode=mode,
        git_commit=_git_rev_parse(until_ref),
        git_dirty=_git_dirty(),
        range_from=range_from,
        range_to=until_ref,
        sections=sections,
    )


def release_notes_to_dict(notes: ReleaseNotes) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_mode": notes.generated_mode,
        "git_commit": notes.git_commit,
        "git_dirty": notes.git_dirty,
        "range_from": notes.range_from,
        "range_to": notes.range_to,
        "sections": [
            {
                "items": list(section.items),
                "title": section.title,
            }
            for section in notes.sections
        ],
        "version": notes.version,
    }
    return {key: payload[key] for key in sorted(payload.keys())}


def _format_wrapped_bullet(text: str, *, width: int) -> list[str]:
    wrapped = textwrap.wrap(
        text,
        width=width,
        initial_indent="- ",
        subsequent_indent="  ",
        break_long_words=False,
        break_on_hyphens=False,
    )
    if wrapped:
        return wrapped
    return ["-"]


def format_release_notes_text(notes: ReleaseNotes, *, line_width: int = 100) -> str:
    lines: list[str] = [
        "Mesh Release Notes",
        f"Version: {notes.version}",
        f"Mode: {notes.generated_mode}",
    ]
    if notes.range_from or notes.range_to:
        lines.append(f"Range: {notes.range_from or 'auto'}..{notes.range_to or 'HEAD'}")
    if notes.git_commit:
        lines.append(f"Git Commit: {notes.git_commit}")
    if notes.git_dirty is not None:
        lines.append(f"Git Dirty: {'yes' if notes.git_dirty else 'no'}")
    lines.append("")

    for section in notes.sections:
        lines.append(f"{section.title}:")
        if section.items:
            for item in section.items:
                lines.extend(_format_wrapped_bullet(item, width=line_width))
        else:
            lines.append("- (none)")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"

