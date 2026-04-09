from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from engine.persistence_io import dumps_json_deterministic, write_json_atomic, write_text_atomic

PROMOTE_EMBED_JSON = "promote/promote_report.json"
PROMOTE_EMBED_TXT = "promote/promote_report.txt"


def _read_manifest_from_zip(zip_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        raw = zf.read("package_manifest.json")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("package_manifest.json must be a JSON object")
    return data


def _determine_version_from_rc_manifest(manifest_data: dict[str, Any]) -> str | None:
    provenance = manifest_data.get("provenance")
    if isinstance(provenance, dict):
        for key in ("rc_version", "tool_version", "engine_version"):
            value = str(provenance.get(key, "") or "").strip()
            if value:
                return value
    for key in ("engine_version",):
        value = str(manifest_data.get(key, "") or "").strip()
        if value:
            return value
    return None


def _extract_zip_to_work_dir(zip_path: Path, work_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in sorted(zf.infolist(), key=lambda row: row.filename):
            rel = str(info.filename or "")
            pp = PurePosixPath(rel)
            if pp.is_absolute() or ".." in pp.parts:
                raise ValueError(f"Unsafe archive path during promotion: {rel}")
            target = work_dir.joinpath(*pp.parts)
            if info.is_dir() or rel.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(rel))


def _write_embedded_promote_reports(
    work_dir: Path,
    report: dict[str, Any],
    *,
    embedded_json_name: str = PROMOTE_EMBED_JSON,
    embedded_txt_name: str = PROMOTE_EMBED_TXT,
) -> None:
    from . import release as release_mod

    promote_json = work_dir / Path(embedded_json_name)
    promote_txt = work_dir / Path(embedded_txt_name)
    promote_json.parent.mkdir(parents=True, exist_ok=True)
    promote_txt.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        promote_json,
        report,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )
    write_text_atomic(
        promote_txt,
        release_mod._format_promote_report_text(report),
        encoding="utf-8",
    )


def _prepare_packaging_work_dir(work_dir: Path) -> None:
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)


def _inspect_rc_bundle_notes_manifest(
    zip_path: Path,
    *,
    expected_notes_payload: dict[str, Any] | None,
    expected_notes_text: str | None,
) -> int:
    with zipfile.ZipFile(zip_path, "r") as zf:
        embedded_notes_payload = json.loads(zf.read("release_notes.json"))
        embedded_notes_text = zf.read("release_notes.txt").decode("utf-8")
        if expected_notes_payload is not None and embedded_notes_payload != expected_notes_payload:
            raise ValueError("embedded release_notes.json mismatch")
        if expected_notes_text is not None and embedded_notes_text != expected_notes_text:
            raise ValueError("embedded release_notes.txt mismatch")
        manifest_data = json.loads(zf.read("package_manifest.json"))
    return int(manifest_data.get("file_count", 0))


def _rebuild_promoted_zip_with_report(
    *,
    work_dir: Path,
    out_zip_path: Path,
    report: dict[str, Any],
    rc_manifest: dict[str, Any],
    timestamp: str,
) -> None:
    _write_embedded_promote_reports(
        work_dir,
        json.loads(dumps_json_deterministic(report)),
    )
    _rebuild_promoted_zip(
        work_dir=work_dir,
        out_zip_path=out_zip_path,
        seed=int(rc_manifest.get("seed", 123)),
        campaign=str(rc_manifest.get("campaign", "mini_campaign_01") or "mini_campaign_01"),
        timestamp=timestamp,
    )


def _rebuild_promoted_zip(
    *,
    work_dir: Path,
    out_zip_path: Path,
    seed: int,
    campaign: str,
    timestamp: str,
) -> None:
    from mesh_cli.bundle_verify import MANIFEST_NAME, MANIFEST_TEXT_NAME

    from . import release_bundle

    files: list[release_bundle.FileEntry] = []
    for path in sorted(work_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(work_dir).as_posix()
        if rel in (MANIFEST_NAME, MANIFEST_TEXT_NAME):
            continue
        files.append(release_bundle.FileEntry(archive_path=rel, disk_path=path))

    release_bundle._build_manifest_with_seal(
        work_dir=work_dir,
        seed=seed,
        campaign=campaign,
        timestamp=timestamp,
        base_files=files,
    )

    final_files: list[release_bundle.FileEntry] = []
    for path in sorted(work_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(work_dir).as_posix()
            final_files.append(release_bundle.FileEntry(archive_path=rel, disk_path=path))
    final_files.sort(key=lambda row: row.archive_path)

    out_zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in final_files:
            info = zipfile.ZipInfo(filename=entry.archive_path, date_time=release_bundle._ZIP_FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, entry.disk_path.read_bytes())
