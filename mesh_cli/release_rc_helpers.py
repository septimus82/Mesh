from __future__ import annotations

import subprocess


def _git_run(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        from mesh_cli import release as release_mod

        release_mod._log_swallow("RELS-001", "git unavailable")
        return None


def _git_available() -> bool:
    from mesh_cli import release as release_mod

    result = release_mod._git_run(["--version"])
    return result is not None and result.returncode == 0


def _git_tag_exists(tag_name: str) -> bool | None:
    from mesh_cli import release as release_mod

    result = release_mod._git_run(["rev-parse", "-q", "--verify", f"refs/tags/{tag_name}"])
    if result is None:
        return None
    return result.returncode == 0


def _default_tag_message(version: str, notes_text: str | None = None) -> str:
    from mesh_cli import release as release_mod

    text = notes_text
    if text is None:
        notes = release_mod.generate_release_notes(deterministic=True, since=None, until="HEAD")
        text = release_mod.format_release_notes_text(notes)
    header = "Mesh Release Notes"
    for line in text.splitlines():
        if line.strip():
            header = line.strip()
            break
    return f"{header} v{version}"


def _create_local_tag(*, tag_name: str, message: str) -> tuple[str, str | None]:
    from mesh_cli import release as release_mod

    exists = release_mod._git_tag_exists(tag_name)
    if exists is None:
        return "skipped", "git unavailable"
    if exists:
        return "existing", f"tag already exists: {tag_name}"
    created = release_mod._git_run(["tag", "-a", tag_name, "-m", message])
    if created is None:
        return "failed", "git execution failed while creating tag"
    if created.returncode != 0:
        detail = (created.stderr or created.stdout or "").strip()
        if not detail:
            detail = "unknown git tag error"
        return "failed", detail
    return "created", None
