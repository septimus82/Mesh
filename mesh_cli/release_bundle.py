"""
CLI command: ``mesh_cli release bundle``

Packages all release artifacts into a single reproducible ZIP:

- export bundle (shippable files + bundle manifest)
- demo run reports and artifacts (new-game, replay traces, debug bundle)
- release check reports
- audit reports
- top-level package manifest with SHA-256 hashes + metadata

Determinism guarantees:
- Stable file ordering (sorted lexicographically by archive path)
- Fixed ZIP timestamps (1980-01-01 00:00:00)
- Fixed metadata timestamp when seed is provided (default: 1980-01-01T00:00:00Z)
- Forward-slash path separators inside the archive
- No machine-specific absolute paths in manifests
"""
from __future__ import annotations

import argparse

from engine.provenance import (
    get_provenance,
    provenance_to_dict,
)
import hashlib
import io
import json
import logging
import platform
import re
import shutil
import sys
import zipfile
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from engine.persistence_io import (
    dumps_json_deterministic,
    write_json_atomic as _base_write_json_atomic,
    write_text_atomic as _base_write_text_atomic,
)
from mesh_cli.release_notes import (
    format_release_notes_text,
    generate_release_notes,
    release_notes_to_dict,
)
from mesh_cli.version_info import get_tool_version

# Fixed timestamp for deterministic ZIPs: 1980-01-01 00:00:00
_ZIP_FIXED_DATE = (1980, 1, 1, 0, 0, 0)
_DEFAULT_DETERMINISTIC_TIMESTAMP = "1980-01-01T00:00:00Z"
_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_HOST_KEYS_TO_DROP = frozenset(
    {
        "cwd",
        "home",
        "host",
        "hostname",
        "machine",
        "repo_root",
        "user",
        "username",
    }
)

DEFAULT_SEED = 42
DEFAULT_CAMPAIGN = "mini_campaign_01"
_DURABLE_WRITES_ENABLED = True


def _write_json_atomic(path: Path | str, payload: Any, **kwargs: Any) -> None:
    kwargs.setdefault("durable", _DURABLE_WRITES_ENABLED)
    _base_write_json_atomic(path, payload, **kwargs)


def _write_text_atomic(path: Path | str, text: str, **kwargs: Any) -> None:
    kwargs.setdefault("durable", _DURABLE_WRITES_ENABLED)
    _base_write_text_atomic(path, text, **kwargs)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FileEntry:
    """A single file to include in the release bundle."""

    archive_path: str  # forward-slash relative path in the zip
    disk_path: Path  # absolute path on disk

    def sha256(self) -> str:
        return _sha256(self.disk_path)

    def size(self) -> int:
        return self.disk_path.stat().st_size


@dataclass
class ReleaseBundlePlan:
    """Describes all files to include and metadata for the bundle."""

    files: list[FileEntry] = field(default_factory=list)
    seed: int = DEFAULT_SEED
    campaign: str = DEFAULT_CAMPAIGN
    work_dir: Path = field(default_factory=lambda: Path("."))
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


@dataclass
class PackageManifest:
    """Top-level manifest embedded in the ZIP."""

    schema_version: int = 1
    seed: int = DEFAULT_SEED
    campaign: str = DEFAULT_CAMPAIGN
    engine_version: str = ""
    git_hash: str | None = None
    python_version: str = ""
    platform_tag: str = ""
    created_utc: str = ""
    file_count: int = 0
    total_size: int = 0
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "seed": self.seed,
            "campaign": self.campaign,
            "engine_version": self.engine_version,
            "python_version": self.python_version,
            "platform": self.platform_tag,
            "created_utc": self.created_utc,
            "file_count": self.file_count,
            "total_size": self.total_size,
            "files": self.files,
        }
        if self.git_hash is not None:
            d["git_hash"] = self.git_hash
        if self.provenance:
            d["provenance"] = self.provenance
        return d

    def to_text(self) -> str:
        lines = [
            "Mesh Release Bundle â€” Package Manifest",
            f"Engine: {self.engine_version}",
            f"Seed: {self.seed}",
            f"Campaign: {self.campaign}",
            f"Python: {self.python_version}",
            f"Platform: {self.platform_tag}",
            f"Created: {self.created_utc}",
        ]
        if self.git_hash:
            lines.append(f"Git: {self.git_hash}")
        if self.provenance:
            from engine.provenance import Provenance, format_provenance_text as _fmt

            try:
                lines.append("")
                lines.append(_fmt(Provenance(**self.provenance)))
            except Exception:
                pass
        lines.append(f"Files: {self.file_count}  ({self.total_size:,} bytes)")
        lines.append("")
        for archive_path in sorted(self.files):
            entry = self.files[archive_path]
            size = entry.get("size", 0)
            sha = entry.get("sha256", "")[:16]
            lines.append(f"  {archive_path}  ({size:,} bytes)  sha256:{sha}â€¦")
        lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_hash() -> str | None:
    """Try to get the current git HEAD hash, return None on failure."""
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _engine_version() -> str:
    return get_tool_version()


def _utc_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_manifest_timestamp(*, seed: int | None, timestamp_override: str | None) -> str:
    """Resolve bundle metadata timestamp under deterministic-seed policy."""
    if timestamp_override:
        return timestamp_override
    if seed is not None:
        return _DEFAULT_DETERMINISTIC_TIMESTAMP
    return _utc_iso()


def _normalize_report_path(raw_value: str, *, repo_root: Path) -> str:
    raw = str(raw_value).replace("\\", "/")
    raw = raw.strip()
    repo_text = repo_root.resolve().as_posix().replace("\\", "/")
    if raw.startswith(repo_text + "/"):
        return raw[len(repo_text) + 1 :]
    if raw == repo_text:
        return "."
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    for index, part in enumerate(parts):
        if part.startswith("_work_"):
            tail = parts[index + 1 :]
            return "/".join(tail) or "."
    if _WINDOWS_ABS_RE.match(raw):
        raw = raw[2:]
    raw = raw.lstrip("/")
    return raw or "."


def _sanitize_report_payload(value: Any, *, repo_root: Path) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key in sorted(value.keys(), key=lambda item: str(item)):
            key_str = str(key)
            if key_str.lower() in _HOST_KEYS_TO_DROP:
                continue
            cleaned[key_str] = _sanitize_report_payload(value[key], repo_root=repo_root)
        return cleaned
    if isinstance(value, list):
        return [_sanitize_report_payload(item, repo_root=repo_root) for item in value]
    if isinstance(value, str):
        raw = value.replace("\\", "/")
        if _WINDOWS_ABS_RE.match(value) or value.startswith("/") or "_work_" in raw:
            return _normalize_report_path(value, repo_root=repo_root)
        return value
    return value


def _sanitize_report_text(text: str, *, repo_root: Path) -> str:
    repo = repo_root.resolve()
    repo_str_native = str(repo)
    repo_str_posix = repo.as_posix().replace("\\", "/")
    normalized = text.replace(repo_str_native, ".").replace(repo_str_posix, ".")
    parts = re.split(r"(\s+)", normalized)
    for index, token in enumerate(parts):
        if not token or token.isspace():
            continue
        strip_chars = "\"'(),"
        core = token.strip(strip_chars)
        if not core:
            continue
        core_raw = core.replace("\\", "/")
        if _WINDOWS_ABS_RE.match(core) or core.startswith("/") or "_work_" in core_raw:
            mapped = _normalize_report_path(core, repo_root=repo_root)
            parts[index] = token.replace(core, mapped)
    return "".join(parts)


def _is_report_like_path(rel_path: str) -> bool:
    rel = rel_path.replace("\\", "/").lower()
    if rel.startswith("scenes/") or "/scenes/" in rel:
        return False
    name = rel.split("/")[-1]
    if not (name.endswith(".json") or name.endswith(".txt")):
        return False
    return any(token in name for token in ("report", "audit", "manifest", "summary"))


def _sanitize_seeded_reports(work_dir: Path, *, repo_root: Path) -> None:
    for path in sorted(work_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(work_dir).as_posix()
        if not _is_report_like_path(rel):
            continue
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            cleaned = _sanitize_report_payload(payload, repo_root=repo_root)
            _write_json_atomic(path, cleaned, indent=2, sort_keys=True, trailing_newline=True)
        elif path.suffix.lower() == ".txt":
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            cleaned_text = _sanitize_report_text(text, repo_root=repo_root)
            if cleaned_text != text:
                _write_text_atomic(path, cleaned_text, encoding="utf-8")


@contextmanager
def _quiet_scope(enabled: bool):
    if not enabled:
        yield
        return
    previous_disable = logging.root.manager.disable
    sink = io.StringIO()
    logging.disable(logging.INFO)
    try:
        with redirect_stdout(sink), redirect_stderr(sink):
            yield
    finally:
        logging.disable(previous_disable)


def _version_payload(*, created_utc: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "engine_version": _engine_version(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "created_utc": created_utc,
    }
    git_hash = _git_hash()
    if git_hash:
        payload["git_hash"] = git_hash
    return payload


def _build_manifest_with_seal(
    *,
    work_dir: Path,
    seed: int,
    campaign: str,
    timestamp: str | None,
    base_files: list[FileEntry],
) -> PackageManifest:
    """Write package_manifest.*, manifest_seal.json, and return final manifest.

    The seal hashes projected manifest content so the seal file can be listed
    in the package manifest without creating a recursive hash dependency.
    """
    from mesh_cli.bundle_verify import (
        MANIFEST_NAME,
        MANIFEST_SEAL_NAME,
        MANIFEST_TEXT_NAME,
        compute_manifest_seal_payload,
    )

    manifest_json_path = work_dir / MANIFEST_NAME
    manifest_txt_path = work_dir / MANIFEST_TEXT_NAME
    seal_path = work_dir / MANIFEST_SEAL_NAME

    file_map: dict[str, FileEntry] = {entry.archive_path: entry for entry in base_files}
    if MANIFEST_SEAL_NAME not in file_map:
        # Placeholder so the first manifest pass has a deterministic seal entry.
        _write_json_atomic(
            seal_path,
            {
                "schema_version": 1,
                "mode": "manifest_projection_v1",
                "sha256_package_manifest_json": "",
                "sha256_package_manifest_txt": "",
                "size_package_manifest_json": 0,
                "size_package_manifest_txt": 0,
            },
            indent=2,
            sort_keys=True,
            trailing_newline=True,
        )
        file_map[MANIFEST_SEAL_NAME] = FileEntry(archive_path=MANIFEST_SEAL_NAME, disk_path=seal_path)

    files = [file_map[path] for path in sorted(file_map.keys())]
    seal_provenance = provenance_to_dict(get_provenance(deterministic=timestamp is not None))

    stable = False
    for _ in range(5):
        iter_plan = ReleaseBundlePlan(
            seed=seed,
            campaign=campaign,
            work_dir=work_dir,
            files=files,
        )
        iter_manifest = build_package_manifest(iter_plan, timestamp=timestamp)
        _write_json_atomic(manifest_json_path, iter_manifest.to_dict(), indent=2, sort_keys=True, trailing_newline=True)
        _write_text_atomic(manifest_txt_path, iter_manifest.to_text(), encoding="utf-8")

        seal_payload = compute_manifest_seal_payload(
            manifest_json_path.read_bytes(),
            manifest_txt_path.read_bytes(),
            provenance=seal_provenance,
        )
        seal_text = dumps_json_deterministic(seal_payload) + "\n"
        previous = seal_path.read_text(encoding="utf-8") if seal_path.exists() else ""
        if previous == seal_text:
            stable = True
            break
        _write_text_atomic(seal_path, seal_text, encoding="utf-8")

    final_plan = ReleaseBundlePlan(
        seed=seed,
        campaign=campaign,
        work_dir=work_dir,
        files=files,
    )
    final_manifest = build_package_manifest(final_plan, timestamp=timestamp)
    _write_json_atomic(manifest_json_path, final_manifest.to_dict(), indent=2, sort_keys=True, trailing_newline=True)
    _write_text_atomic(manifest_txt_path, final_manifest.to_text(), encoding="utf-8")

    # Ensure seal still matches the final manifest projection. If not, rewrite once.
    verify_payload = compute_manifest_seal_payload(
        manifest_json_path.read_bytes(),
        manifest_txt_path.read_bytes(),
        provenance=seal_provenance,
    )
    verify_text = dumps_json_deterministic(verify_payload) + "\n"
    current_text = seal_path.read_text(encoding="utf-8")
    if current_text != verify_text:
        _write_text_atomic(seal_path, verify_text, encoding="utf-8")
        final_manifest = build_package_manifest(final_plan, timestamp=timestamp)
        _write_json_atomic(manifest_json_path, final_manifest.to_dict(), indent=2, sort_keys=True, trailing_newline=True)
        _write_text_atomic(manifest_txt_path, final_manifest.to_text(), encoding="utf-8")

    if not stable and seal_path.exists():
        # Best effort fallback: keep deterministic outputs even if stabilization took all passes.
        pass

    return final_manifest


def _write_release_notes_files(
    work_dir: Path,
    *,
    since: str | None = None,
    until: str | None = "HEAD",
) -> None:
    """Write deterministic release notes files into the bundle root."""
    notes = generate_release_notes(deterministic=True, since=since, until=until)
    notes_json = work_dir / "release_notes.json"
    notes_txt = work_dir / "release_notes.txt"
    _write_json_atomic(
        notes_json,
        release_notes_to_dict(notes),
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )
    _write_text_atomic(
        notes_txt,
        format_release_notes_text(notes),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Pipeline step runners
# ---------------------------------------------------------------------------

StepFn = Callable[[Path, int, str], "tuple[int, dict[str, Any]]"]


def _step_release_check(work_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
    """Run ``release check`` into work_dir/release."""
    from mesh_cli.release import _handle_check

    release_dir = work_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    args = argparse.Namespace(
        command="release",
        release_command="check",
        repo_root=".",
        artifacts=str(release_dir),
        report=None,
        summary=None,
        deterministic=True,
        quiet=True,
    )
    code = _handle_check(args)
    return code, {"dir": "release/"}


def _step_demo_run(work_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
    """Run ``demo pipeline`` into work_dir/demo."""
    from mesh_cli.demo import run_demo

    demo_dir = work_dir / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    code, _report = run_demo(out_dir=demo_dir, seed=seed, campaign=campaign, quiet=True)
    return code, {"dir": "demo/"}


def _step_export_build(work_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
    """Run ``export build`` into work_dir/bundle."""
    from mesh_cli.export import _handle_export_build

    bundle_dir = work_dir / "bundle"
    args = argparse.Namespace(
        command="export",
        export_command="build",
        repo_root=".",
        out=str(bundle_dir),
        include_unused=False,
        allow_missing=False,
        deterministic=True,
    )
    code = _handle_export_build(args)
    return code, {"dir": "bundle/"}


def _step_collect_audits(work_dir: Path, seed: int, campaign: str) -> tuple[int, dict[str, Any]]:
    """Copy available audit artifacts into work_dir/audits."""
    audits_dir = work_dir / "audits"
    audits_dir.mkdir(parents=True, exist_ok=True)

    # Copy from release step outputs if present
    release_dir = work_dir / "release"
    copied = 0
    audit_files = [
        "asset_audit.json",
        "brush_audit.json",
        "encounter_audit_summary.json",
        "encounter_coverage_matrix.json",
        "room_audit.json",
        "stamp_audit.json",
        "macro_audit.json",
        "doctor_assets.json",
    ]
    for name in audit_files:
        src = release_dir / name
        if src.is_file():
            shutil.copy2(src, audits_dir / name)
            copied += 1

    # Also try repo artifacts dir
    repo_artifacts = Path("artifacts")
    if repo_artifacts.is_dir():
        for name in ["asset_manifest.json", "asset_deps.json"]:
            src = repo_artifacts / name
            if src.is_file() and not (audits_dir / name).exists():
                shutil.copy2(src, audits_dir / name)
                copied += 1

    return 0, {"dir": "audits/", "copied": copied}


BUNDLE_PIPELINE: list[tuple[str, StepFn]] = [
    ("release-check", _step_release_check),
    ("demo-run", _step_demo_run),
    ("export-build", _step_export_build),
    ("collect-audits", _step_collect_audits),
]


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def compute_release_bundle_plan(
    work_dir: Path,
    *,
    seed: int = DEFAULT_SEED,
    campaign: str = DEFAULT_CAMPAIGN,
    quiet: bool = False,
    pipeline: list[tuple[str, StepFn]] | None = None,
    notes_since: str | None = None,
    notes_until: str | None = "HEAD",
) -> ReleaseBundlePlan:
    """Run all steps, then scan work_dir to build a plan of files to zip."""
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    step_list = pipeline if pipeline is not None else BUNDLE_PIPELINE

    plan = ReleaseBundlePlan(seed=seed, campaign=campaign, work_dir=work_dir)

    for name, runner in step_list:
        try:
            with _quiet_scope(quiet):
                code, outputs = runner(work_dir, seed, campaign)
            if code != 0:
                plan.errors.append(f"Step '{name}' failed (exit={code})")
                return plan  # fail-fast
        except Exception as exc:
            plan.errors.append(f"Step '{name}' error: {type(exc).__name__}: {exc}")
            return plan

    try:
        _write_release_notes_files(work_dir, since=notes_since, until=notes_until)
    except Exception as exc:
        plan.errors.append(f"Step 'release-notes' error: {type(exc).__name__}: {exc}")
        return plan

    if seed is not None:
        _sanitize_seeded_reports(work_dir, repo_root=Path.cwd())

    # Scan all files under work_dir
    for p in sorted(work_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(work_dir).as_posix()
            plan.files.append(FileEntry(archive_path=rel, disk_path=p))

    return plan


def build_package_manifest(
    plan: ReleaseBundlePlan,
    *,
    timestamp: str | None = None,
) -> PackageManifest:
    """Build a PackageManifest from a completed plan.

    When *timestamp* is supplied the provenance block is built in
    deterministic mode (no volatile ``build_timestamp_utc``) so that
    repeated calls with the same inputs produce identical output.
    """
    deterministic = timestamp is not None
    manifest = PackageManifest(
        seed=plan.seed,
        campaign=plan.campaign,
        engine_version=_engine_version(),
        git_hash=_git_hash(),
        python_version=platform.python_version(),
        platform_tag=platform.platform(),
        created_utc=timestamp or _utc_iso(),
        provenance=provenance_to_dict(get_provenance(deterministic=deterministic)),
    )

    total_size = 0
    file_records: dict[str, dict[str, Any]] = {}
    for entry in plan.files:
        size = entry.size()
        sha = entry.sha256()
        total_size += size
        file_records[entry.archive_path] = {"size": size, "sha256": sha}

    manifest.files = file_records
    manifest.file_count = len(file_records)
    manifest.total_size = total_size
    return manifest


def build_release_bundle_zip(
    plan: ReleaseBundlePlan,
    zip_path: Path,
    *,
    manifest: PackageManifest | None = None,
    timestamp: str | None = None,
) -> PackageManifest:
    """Write a deterministic ZIP at *zip_path* from *plan*.

    Returns the PackageManifest that was embedded.
    """
    zip_path = zip_path.resolve()
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    build_timestamp = timestamp or _utc_iso()
    version_data = _version_payload(created_utc=build_timestamp)
    version_path = plan.work_dir / "VERSION.json"
    _write_json_atomic(version_path, version_data, indent=2, sort_keys=True, trailing_newline=True)

    from mesh_cli.bundle_verify import MANIFEST_NAME, MANIFEST_TEXT_NAME

    # Re-scan work_dir so VERSION and seal are part of manifest coverage.
    base_files: list[FileEntry] = []
    for p in sorted(plan.work_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(plan.work_dir).as_posix()
        if rel in (MANIFEST_NAME, MANIFEST_TEXT_NAME):
            continue
        base_files.append(FileEntry(archive_path=rel, disk_path=p))

    final_manifest = _build_manifest_with_seal(
        work_dir=plan.work_dir,
        seed=plan.seed,
        campaign=plan.campaign,
        timestamp=build_timestamp,
        base_files=base_files,
    )

    # Collect all files including manifest entries
    all_files: list[FileEntry] = []
    for p in sorted(plan.work_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(plan.work_dir).as_posix()
            all_files.append(FileEntry(archive_path=rel, disk_path=p))

    # Sort by archive path for determinism
    all_files.sort(key=lambda e: e.archive_path)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in all_files:
            info = zipfile.ZipInfo(filename=entry.archive_path, date_time=_ZIP_FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16  # consistent permission bits
            with open(entry.disk_path, "rb") as f:
                zf.writestr(info, f.read())

    return final_manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def register_subcommand(release_subparsers: argparse._SubParsersAction) -> None:
    """Register ``bundle`` as a subcommand of the ``release`` parser."""
    bundle_parser = release_subparsers.add_parser(
        "bundle",
        help="Package release artifacts into a reproducible ZIP.",
        description=(
            "Runs release check, demo pipeline, export build, and audit collection, "
            "then packages everything into a single deterministic ZIP with a "
            "package manifest."
        ),
    )
    bundle_parser.add_argument(
        "--out",
        required=True,
        help="Output ZIP file path (e.g. artifacts/release_bundle.zip).",
    )
    bundle_parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"RNG seed for deterministic runs (default: {DEFAULT_SEED}).",
    )
    bundle_parser.add_argument(
        "--campaign",
        default=DEFAULT_CAMPAIGN,
        help=f"Campaign identifier (default: {DEFAULT_CAMPAIGN}).",
    )
    bundle_parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="text",
        dest="report_format",
        help="Output format for the final summary (default: text).",
    )
    bundle_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress step output; only print final status.",
    )
    bundle_parser.add_argument(
        "--deterministic-timestamp",
        default=None,
        help=(
            "Optional UTC timestamp override for manifest metadata (ISO-8601). "
            "When omitted and --seed is set, defaults to 1980-01-01T00:00:00Z."
        ),
    )


def handle(args: argparse.Namespace) -> int:
    """Entry point called from ``release`` dispatch."""
    return _handle_bundle(args)


def _handle_bundle(args: argparse.Namespace) -> int:
    zip_path = Path(args.out).resolve()
    seed: int = args.seed
    campaign: str = args.campaign
    quiet: bool = getattr(args, "quiet", False)
    report_format: str = getattr(args, "report_format", "text")
    notes_since = getattr(args, "notes_since", None)
    notes_until = getattr(args, "notes_until", "HEAD")
    timestamp_override_raw = str(getattr(args, "deterministic_timestamp", "") or "").strip()
    timestamp_override = timestamp_override_raw or None

    # Use a temp working directory next to the output zip
    work_dir = zip_path.parent / f"_work_{zip_path.stem}"
    try:
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

        # Run the pipeline
        plan = compute_release_bundle_plan(
            work_dir,
            seed=seed,
            campaign=campaign,
            quiet=quiet,
            notes_since=notes_since,
            notes_until=notes_until,
        )

        if not plan.ok:
            for err in plan.errors:
                print(f"[Mesh][Release-Bundle] ERROR: {err}", file=sys.stderr)
            if not quiet:
                print("[Mesh][Release-Bundle] FAILED â€” ZIP not produced")
            return 1

        if seed is not None:
            _sanitize_seeded_reports(work_dir, repo_root=Path.cwd())

        # Build the initial ZIP (without verify reports). When seed is provided,
        # pin manifest timestamp for byte-deterministic output by default.
        ts = _resolve_manifest_timestamp(
            seed=getattr(args, "seed", None),
            timestamp_override=timestamp_override,
        )
        manifest = build_release_bundle_zip(plan, zip_path, timestamp=ts)

        # --- Self-verification ---
        verify_result = self_verify_and_embed(
            zip_path=zip_path,
            work_dir=work_dir,
            plan=plan,
            timestamp=ts,
            quiet=quiet,
        )
        if verify_result != 0:
            # Delete the bad ZIP
            if zip_path.exists():
                try:
                    zip_path.unlink()
                except OSError:
                    pass
            if not quiet:
                print("[Mesh][Release-Bundle] FAILED â€” self-verification failed, ZIP deleted")
            return 1

        # Re-read manifest from the rebuilt ZIP for final output
        with zipfile.ZipFile(zip_path, "r") as zf:
            manifest_data = json.loads(zf.read("package_manifest.json"))
        final_manifest = PackageManifest(
            seed=manifest_data.get("seed", seed),
            campaign=manifest_data.get("campaign", campaign),
            engine_version=manifest_data.get("engine_version", ""),
            git_hash=manifest_data.get("git_hash"),
            python_version=manifest_data.get("python_version", ""),
            platform_tag=manifest_data.get("platform", ""),
            created_utc=manifest_data.get("created_utc", ""),
            file_count=manifest_data.get("file_count", 0),
            total_size=manifest_data.get("total_size", 0),
            files=manifest_data.get("files", {}),
            provenance=manifest_data.get("provenance", {}),
        )

        if report_format == "json":
            sys.stdout.write(dumps_json_deterministic(final_manifest.to_dict()))
        else:
            if not quiet:
                print(final_manifest.to_text(), end="")

        if not quiet:
            size_mb = zip_path.stat().st_size / (1024 * 1024)
            print(
                f"[Mesh][Release-Bundle] OK â€” {zip_path.name} "
                f"({final_manifest.file_count} files, {size_mb:.1f} MB)"
            )
        return 0

    finally:
        # Clean up work directory
        if work_dir.exists():
            try:
                shutil.rmtree(work_dir)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Self-verification
# ---------------------------------------------------------------------------

def self_verify_and_embed(
    *,
    zip_path: Path,
    work_dir: Path,
    plan: ReleaseBundlePlan,
    timestamp: str,
    quiet: bool = False,
) -> int:
    """Run verification on the ZIP, embed reports, and rebuild.

    Returns 0 on success, 1 on failure.  On failure the caller is
    responsible for cleaning up the ZIP.
    """
    from mesh_cli.bundle_verify import (
        DEFAULT_EXCLUDE_RULES,
        VerifyOptions,
        format_verify_text,
        verify_zip,
    )

    # 1. Verify the initial ZIP
    try:
        report = verify_zip(
            str(zip_path),
            options=VerifyOptions(strict=True, exclude=DEFAULT_EXCLUDE_RULES),
        )
    except TypeError:
        # Compatibility fallback for tests monkeypatching legacy verify_zip signature.
        report = verify_zip(str(zip_path))
    if not report.get("ok"):
        # Write the failure report next to the ZIP for debugging
        fail_json = zip_path.parent / "verify_report_FAILED.json"
        fail_txt = zip_path.parent / "verify_report_FAILED.txt"
        try:
            _write_json_atomic(fail_json, report)
            _write_text_atomic(fail_txt, format_verify_text(report))
        except OSError:
            pass
        if not quiet:
            print(
                f"[Mesh][Release-Bundle] Self-verify FAILED: "
                f"{len(report.get('errors', []))} errors",
                file=sys.stderr,
            )
            if fail_json.exists():
                print(f"[Mesh][Release-Bundle] See: {fail_json}", file=sys.stderr)
        return 1

    # 2. Write verify reports into work_dir/verify/
    verify_dir = work_dir / "verify"
    verify_dir.mkdir(parents=True, exist_ok=True)

    # Strip the absolute zip path from the report for determinism
    report["zip"] = "release_bundle.zip"
    verify_json_content = dumps_json_deterministic(report)
    verify_txt_content = format_verify_text(report)

    verify_json_path = verify_dir / "verify_report.json"
    verify_txt_path = verify_dir / "verify_report.txt"
    _write_text_atomic(verify_json_path, verify_json_content)
    _write_text_atomic(verify_txt_path, verify_txt_content)

    # 3. Rebuild the ZIP with verify reports included
    #    Re-scan work_dir to include the new verify files, rebuild manifest
    updated_files: list[FileEntry] = []
    for p in sorted(work_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(work_dir).as_posix()
            # Skip the old manifest files â€” we'll rewrite them
            if rel in ("package_manifest.json", "package_manifest.txt"):
                continue
            updated_files.append(FileEntry(archive_path=rel, disk_path=p))

    version_data = _version_payload(created_utc=timestamp)
    version_path = work_dir / "VERSION.json"
    _write_json_atomic(version_path, version_data, indent=2, sort_keys=True, trailing_newline=True)
    version_entry = FileEntry(archive_path="VERSION.json", disk_path=version_path)
    if all(entry.archive_path != version_entry.archive_path for entry in updated_files):
        updated_files.append(version_entry)

    _build_manifest_with_seal(
        work_dir=work_dir,
        seed=plan.seed,
        campaign=plan.campaign,
        timestamp=timestamp,
        base_files=updated_files,
    )

    # Collect ALL files for final ZIP
    final_files: list[FileEntry] = []
    for p in sorted(work_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(work_dir).as_posix()
            final_files.append(FileEntry(archive_path=rel, disk_path=p))
    final_files.sort(key=lambda e: e.archive_path)

    # Rewrite the ZIP
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in final_files:
            info = zipfile.ZipInfo(filename=entry.archive_path, date_time=_ZIP_FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(entry.disk_path, "rb") as f:
                zf.writestr(info, f.read())

    return 0

