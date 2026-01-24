from __future__ import annotations

from pathlib import Path


def _sorted_paths(paths: list[Path]) -> list[Path]:
    return sorted(paths, key=lambda p: p.as_posix())


def discover_scene_paths(repo_root: Path) -> list[Path]:
    """Discover scene JSON files in a deterministic order.

    This mirrors the project layout patterns used by tooling:
    - scenes/**/*.json
    - packs/**/scenes/**/*.json
    """
    root = Path(repo_root)
    found: list[Path] = []

    scenes_dir = root / "scenes"
    if scenes_dir.exists():
        found.extend([p for p in scenes_dir.rglob("*.json") if p.is_file()])

    packs_dir = root / "packs"
    if packs_dir.exists():
        for scenes_subdir in packs_dir.glob("**/scenes"):
            if scenes_subdir.is_dir():
                found.extend([p for p in scenes_subdir.rglob("*.json") if p.is_file()])

    return _sorted_paths(found)


def discover_world_paths(repo_root: Path) -> list[Path]:
    """Discover world JSON files in a deterministic order: worlds/*.json."""
    root = Path(repo_root)
    worlds_dir = root / "worlds"
    if not worlds_dir.exists():
        return []
    return _sorted_paths([p for p in worlds_dir.glob("*.json") if p.is_file()])


def discover_scene_files_under(directory: Path) -> list[Path]:
    """Discover *.json under a directory recursively in a deterministic order."""
    base = Path(directory)
    if not base.exists():
        return []
    return _sorted_paths([p for p in base.rglob("*.json") if p.is_file()])


def resolve_validation_targets(path: str | Path | None, repo_root: Path) -> list[Path]:
    """Resolve a path argument to a list of validation targets.

    Handles the common case where "." or empty path should fall back to
    worlds/main_world.json or scan worlds/ for JSON files.

    Rules:
    - If path is empty/None/"." then:
      * If repo_root/worlds/main_world.json exists -> return [that]
      * else if repo_root/worlds exists -> return sorted list of all *.json under worlds
      * else return []
    - If path exists and is a directory:
      * Scan for *.json files recursively, sorted lexicographically
    - If path exists and is a file:
      * return [path]
    - If path does not exist:
      * return []

    Returns:
        Sorted list of Path objects (lexicographic by posix path).
    """
    root = Path(repo_root)

    # Normalize empty/None/"." to default
    if path is None or str(path).strip() in ("", "."):
        main_world = root / "worlds" / "main_world.json"
        if main_world.exists() and main_world.is_file():
            return [main_world]
        worlds_dir = root / "worlds"
        if worlds_dir.exists() and worlds_dir.is_dir():
            return _sorted_paths([p for p in worlds_dir.rglob("*.json") if p.is_file()])
        return []

    # Resolve relative to repo_root if not absolute
    target = Path(path)
    if not target.is_absolute():
        target = root / target

    if not target.exists():
        return []

    if target.is_file():
        return [target]

    # Directory: scan for JSON files
    if target.is_dir():
        return _sorted_paths([p for p in target.rglob("*.json") if p.is_file()])

    return []

