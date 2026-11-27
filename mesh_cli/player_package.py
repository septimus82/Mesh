from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from engine.persistence_io import dumps_json_deterministic, write_json_atomic
from engine.runtime_only import DEFAULT_SMOKE_SCENE, FORBIDDEN_EDITOR_PREFIXES
from engine.swallowed_exceptions import _log_swallow

DEFAULT_RUNTIME_ENTRY = "python -m mesh_cli play-runtime --headless-smoke"
_PACKAGE_SOURCE_ROOTS: tuple[str, ...] = ("engine", "mesh_cli")
_NON_RUNTIME_FILE_SUFFIXES: tuple[str, ...] = (".pyc", ".pyo")


def _normalize_relpath(path: str | Path) -> str:
    return str(path).replace("\\", "/").strip()


def _is_forbidden_editor_relpath(relpath: str, *, forbidden_prefixes: tuple[str, ...]) -> bool:
    normalized = _normalize_relpath(relpath)
    if not normalized:
        return False
    if normalized.startswith("engine/editor"):
        return True
    if "/editor/" in f"/{normalized}":
        return True
    for prefix in forbidden_prefixes:
        module_path = prefix.replace(".", "/")
        if normalized == f"{module_path}.py" or normalized.startswith(f"{module_path}/"):
            return True
    return False


def _iter_source_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root_name in _PACKAGE_SOURCE_ROOTS:
        root = repo_root / root_name
        if not root.exists() or not root.is_dir():
            continue
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts:
                continue
            if path.suffix in _NON_RUNTIME_FILE_SUFFIXES:
                continue
            files.append(path)
    return files


def _resolve_repo_root(start: Path) -> Path:
    try:
        from engine.repo_root import get_repo_root

        resolved = get_repo_root(start=start, strict=False)
        if resolved is not None:
            return Path(resolved).resolve()
    except (ImportError, OSError, RuntimeError, ValueError):
        _log_swallow("PLAY-003", "mesh_cli/player_package.py pass-only blanket swallow")
        pass
    return start.resolve()


def build_manifest_payload(
    *,
    package_root: str,
    included_files: list[str],
    excluded_prefixes: list[str],
    content_roots_included: list[str],
    total_bytes: int,
    forbidden_hits: list[str],
) -> dict[str, Any]:
    included_sorted = sorted(_normalize_relpath(path) for path in included_files)
    excluded_sorted = sorted(str(item) for item in excluded_prefixes)
    content_roots_sorted = sorted(str(item) for item in content_roots_included)
    forbidden_sorted = sorted(_normalize_relpath(path) for path in forbidden_hits)
    return {
        "schema_version": 1,
        "created_by": "mesh_cli package-player",
        "package_root": _normalize_relpath(package_root),
        "included_files": included_sorted,
        "excluded_prefixes": excluded_sorted,
        "runtime_entry": DEFAULT_RUNTIME_ENTRY,
        "content_roots_included": content_roots_sorted,
        "checks": {
            "file_count": int(len(included_sorted)),
            "total_bytes": int(total_bytes),
            "forbidden_hits": forbidden_sorted,
        },
    }


def _run_packaged_runtime_smoke(
    package_dir: Path,
    *,
    diagnostics_artifact: str | None,
) -> tuple[bool, int]:
    smoke_artifact_rel = "runtime_smoke.json"
    diagnostics_artifact_path = str(diagnostics_artifact or "runtime_diagnostics_snapshot.json").strip()
    if not diagnostics_artifact_path:
        diagnostics_artifact_path = "runtime_diagnostics_snapshot.json"
    cmd = [
        sys.executable,
        "-m",
        "mesh_cli",
        "play-runtime",
        "--headless-smoke",
        "--smoke-scene",
        DEFAULT_SMOKE_SCENE,
        "--smoke-artifact",
        smoke_artifact_rel,
        "--diagnostics-artifact",
        diagnostics_artifact_path,
    ]
    result = subprocess.run(cmd, cwd=str(package_dir), capture_output=True, text=True)
    return int(result.returncode) == 0, int(result.returncode)


def _inside(path: Path, out_root: Path, stage: Path) -> Path:
    """``path``, moved from the output folder into the build folder when it points into the output (the earlier
    package stays untouched while the new one is built)."""
    full = Path(os.path.abspath(path))
    return stage / full.relative_to(out_root) if full.is_relative_to(out_root) else path


def package_player_bundle(
    *,
    out_dir: str,
    manifest_path: str | None = None,
    smoke: bool = False,
    smoke_diagnostics_artifact: str | None = None,
) -> int:
    """Build the player package into ``out_dir``: built beside it, then swapped in only when complete and its checks
    pass (#749). An existing ``out_dir`` is replaced only when empty or an earlier package exactly as built; a folder
    that is, or holds, the project, the repository, the home folder or a drive root, or lies inside the packaged
    sources, is refused before anything is touched."""
    from engine.tooling.export_bundle import ExportError, build_into, seal_bundle

    cwd = Path.cwd()
    repo_root = _resolve_repo_root(cwd)
    out_root = Path(os.path.abspath(repo_root / out_dir))  # (not resolved: a link given as --out is refused, never followed)

    def build(stage: Path) -> int:
        if _build_package(stage, out_root, repo_root, manifest_path=manifest_path, smoke=smoke,
                          smoke_diagnostics_artifact=smoke_diagnostics_artifact) != 0:
            raise ExportError("the player package was not built (see above)")
        seal_bundle(stage, "mesh package-player")
        return 0

    result = build_into(out_root, build, tag="[Mesh][PackagePlayer]", created_by="mesh package-player",
                        protected=(repo_root, cwd),
                        sources=[repo_root / name for name in _PACKAGE_SOURCE_ROOTS])
    return 0 if result == 0 else 1


def _build_package(
    stage: Path,
    out_root: Path,
    repo_root: Path,
    *,
    manifest_path: str | None,
    smoke: bool,
    smoke_diagnostics_artifact: str | None,
) -> int:
    """Write the package into ``stage`` (reported as ``out_root``, where it will be); 0 when its checks pass."""
    included_files: list[str] = []
    excluded_prefixes = sorted(set(FORBIDDEN_EDITOR_PREFIXES))

    for source_path in _iter_source_files(repo_root):
        rel = _normalize_relpath(source_path.relative_to(repo_root))
        if _is_forbidden_editor_relpath(rel, forbidden_prefixes=FORBIDDEN_EDITOR_PREFIXES):
            continue
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        included_files.append(rel)

    smoke_scene_source = repo_root / DEFAULT_SMOKE_SCENE
    if not smoke_scene_source.exists() or not smoke_scene_source.is_file():
        print(f"[Mesh][PackagePlayer] ERROR: {DEFAULT_SMOKE_SCENE} is missing")
        return 1
    smoke_scene_target = stage / DEFAULT_SMOKE_SCENE
    smoke_scene_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(smoke_scene_source, smoke_scene_target)
    included_files.append(_normalize_relpath(DEFAULT_SMOKE_SCENE))

    minimal_config = {
        "content_roots": ["."],
        "input": {
            "rumble_enabled": False,
            "rumble_strength": 1.0,
        },
        "main_menu_scene": None,
        "start_scene": DEFAULT_SMOKE_SCENE,
        "world_file": None,
    }
    write_json_atomic(
        stage / "config.json",
        minimal_config,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )
    included_files.append("config.json")

    included_files = sorted(set(included_files))
    forbidden_hits = [
        rel
        for rel in included_files
        if _is_forbidden_editor_relpath(rel, forbidden_prefixes=FORBIDDEN_EDITOR_PREFIXES)
    ]
    total_bytes = int(
        sum(int((stage / rel).stat().st_size) for rel in included_files if (stage / rel).exists())
    )

    content_roots_included = sorted({"scenes"} if any(path.startswith("scenes/") for path in included_files) else set())
    package_root = _normalize_relpath(out_root.relative_to(repo_root) if out_root.is_relative_to(repo_root) else out_root)
    manifest_payload = build_manifest_payload(
        package_root=package_root,
        included_files=included_files,
        excluded_prefixes=excluded_prefixes,
        content_roots_included=content_roots_included,
        total_bytes=total_bytes,
        forbidden_hits=forbidden_hits,
    )

    manifest_target = Path(manifest_path) if manifest_path else (out_root / "manifest.json")
    if not manifest_target.is_absolute():
        manifest_target = repo_root / manifest_target
    manifest_written = _inside(manifest_target, out_root, stage)
    write_json_atomic(
        manifest_written,
        manifest_payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )

    smoke_ok = True
    smoke_rc = 0
    if smoke:
        diagnostics = smoke_diagnostics_artifact
        if diagnostics and Path(diagnostics).is_absolute():
            diagnostics = str(_inside(Path(diagnostics), out_root, stage))
        smoke_ok, smoke_rc = _run_packaged_runtime_smoke(
            stage,
            diagnostics_artifact=diagnostics,
        )

    manifest_sorted = bool(manifest_payload["included_files"] == sorted(manifest_payload["included_files"]))
    expected_manifest_text = dumps_json_deterministic(
        manifest_payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )
    manifest_canonical_json = False
    if manifest_written.exists():
        manifest_canonical_json = manifest_written.read_text(encoding="utf-8") == expected_manifest_text
    check_payload = {
        "ok": bool(len(forbidden_hits) == 0 and smoke_ok and manifest_sorted and manifest_canonical_json),
        "package_root": package_root,
        "manifest_path": _normalize_relpath(manifest_target.relative_to(repo_root) if manifest_target.is_relative_to(repo_root) else manifest_target),
        "file_count": int(len(included_files)),
        "total_bytes": int(total_bytes),
        "forbidden_hits": sorted(forbidden_hits),
        "manifest_sorted": manifest_sorted,
        "manifest_canonical_json": bool(manifest_canonical_json),
        "smoke_ran": bool(smoke),
        "smoke_ok": bool(smoke_ok),
        "smoke_returncode": int(smoke_rc),
    }
    write_json_atomic(
        stage / "package_check.json",
        check_payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )
    if not check_payload["ok"]:
        print(dumps_json_deterministic(check_payload, indent=2, sort_keys=True, trailing_newline=True), end="")

    return 0 if check_payload["ok"] else 1


__all__ = [
    "DEFAULT_RUNTIME_ENTRY",
    "build_manifest_payload",
    "package_player_bundle",
]
