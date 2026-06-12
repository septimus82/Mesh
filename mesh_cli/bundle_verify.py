"""
CLI command: ``mesh_cli bundle verify``

Verifies the integrity of a Mesh release bundle ZIP:

- ZIP structure is valid and readable
- ``package_manifest.json`` is present and parseable
- Every file listed in the manifest exists in the archive
- SHA-256 hashes match for every listed file
- No absolute paths or path-traversal components (``..``) in archive entries
- Every non-directory file is either hash-verified via manifest coverage,
  verified by the manifest integrity seal, or explicitly excluded

Returns exit code 0 on success, 1 on failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import PurePosixPath
from typing import Any, cast

from engine.diagnostics import Diagnostic, DiagnosticLevel, sort_diagnostics
from engine.log_utils import normalize_path

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(subparsers: argparse._SubParsersAction) -> None:
    verify_parser = subparsers.add_parser(
        "bundle",
        help="Bundle utilities",
        description="Verify or inspect release bundle ZIPs",
    )
    verify_sub = verify_parser.add_subparsers(dest="bundle_command", help="Bundle subcommand")

    vp = verify_sub.add_parser(
        "verify",
        help="Verify integrity of a release bundle ZIP",
        description="Check manifest hashes, paths, and structure",
    )
    vp.add_argument("zip", nargs="?", help="Path to the release bundle ZIP file")
    vp.add_argument(
        "--zip",
        dest="zip_opt",
        help="Path to the release bundle ZIP file",
    )
    vp.add_argument(
        "--strict",
        action="store_true",
        default=True,
        dest="verify_strict",
        help="Require every verifiable file to be manifest-covered or explicitly justified (default)",
    )
    vp.add_argument(
        "--no-strict",
        action="store_false",
        dest="verify_strict",
        help="Allow unresolved extras (still reported)",
    )
    vp.add_argument(
        "--json",
        action="store_true",
        dest="verify_json",
        help="Output verification report as JSON",
    )



def handle(args: argparse.Namespace) -> int:
    cmd = getattr(args, "bundle_command", None)
    if cmd == "verify":
        return _handle_verify(args)
    print("[Mesh][Bundle] Error: missing bundle subcommand (try: verify)")
    return 2


# ---------------------------------------------------------------------------
# Verify implementation
# ---------------------------------------------------------------------------

MANIFEST_NAME = "package_manifest.json"
MANIFEST_TEXT_NAME = "package_manifest.txt"
MANIFEST_SEAL_NAME = "manifest_seal.json"

SEAL_SCHEMA_VERSION = 1
SEAL_MODE = "manifest_projection_v1"
SEAL_PLACEHOLDER_SHA256 = "<seal-self-reference>"
SEAL_PLACEHOLDER_SIZE = -1


@dataclass(frozen=True)
class ExcludeRule:
    pattern: str
    reason: str


@dataclass(frozen=True)
class VerifyOptions:
    strict: bool = True
    exclude: tuple[ExcludeRule, ...] = ()


DEFAULT_EXCLUDE_RULES: tuple[ExcludeRule, ...] = ()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dumps_json_compact(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _display_zip(zip_path: str | PurePosixPath) -> str:
    raw = normalize_path(str(zip_path))
    pp = PurePosixPath(raw)
    if pp.is_absolute():
        return pp.name
    return raw or "bundle.zip"


def _is_directory_entry(info: zipfile.ZipInfo) -> bool:
    filename = info.filename or ""
    return info.is_dir() or filename.endswith("/")


def _find_exclude_reason(path: str, rules: tuple[ExcludeRule, ...]) -> str | None:
    for rule in rules:
        if fnmatch(path, rule.pattern):
            return rule.reason
    return None


def _count_by_reason(skipped: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in skipped:
        reason = str(row.get("reason", "") or "")
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _project_manifest_dict_for_seal(manifest_data: dict[str, Any]) -> dict[str, Any]:
    projected_any = json.loads(_dumps_json_compact(manifest_data))
    if not isinstance(projected_any, dict):
        return {}
    projected = cast(dict[str, Any], projected_any)
    files = projected.get("files")
    if isinstance(files, dict):
        seal_entry = files.get(MANIFEST_SEAL_NAME)
        if isinstance(seal_entry, dict):
            patched = dict(seal_entry)
            patched["sha256"] = SEAL_PLACEHOLDER_SHA256
            if "size" in patched:
                patched["size"] = SEAL_PLACEHOLDER_SIZE
            files[MANIFEST_SEAL_NAME] = patched
    return projected


def _project_manifest_text_for_seal(text: str) -> str:
    pattern = rf"^  {re.escape(MANIFEST_SEAL_NAME)}  \([^)]*\)  sha256:.*$"
    projected = re.sub(pattern, f"  {MANIFEST_SEAL_NAME}  (<seal-entry>)", text, flags=re.MULTILINE)
    return projected


def compute_manifest_seal_payload(
    manifest_json_bytes: bytes,
    manifest_txt_bytes: bytes,
    *,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic manifest seal payload from manifest files.

    The package manifest projection masks the seal's own hash/size to avoid
    self-referential hashing cycles.
    """
    manifest_data = json.loads(manifest_json_bytes)
    projected_manifest = _project_manifest_dict_for_seal(manifest_data)
    projected_manifest_bytes = _dumps_json_compact(projected_manifest).encode("utf-8")

    manifest_txt = manifest_txt_bytes.decode("utf-8")
    projected_txt = _project_manifest_text_for_seal(manifest_txt)
    projected_txt_bytes = projected_txt.encode("utf-8")

    payload: dict[str, Any] = {
        "schema_version": SEAL_SCHEMA_VERSION,
        "mode": SEAL_MODE,
        "sha256_package_manifest_json": _sha256_bytes(projected_manifest_bytes),
        "sha256_package_manifest_txt": _sha256_bytes(projected_txt_bytes),
        "size_package_manifest_json": len(manifest_json_bytes),
        "size_package_manifest_txt": len(manifest_txt_bytes),
    }
    if provenance:
        payload["provenance"] = provenance
    return payload


def _verify_manifest_seal(
    *,
    zf: zipfile.ZipFile,
    zip_file_set: set[str],
    manifest_set: set[str],
    strict: bool,
    errors: list[str],
    warnings: list[str],
    counts: dict[str, int],
) -> tuple[bool, set[str]]:
    """Verify package manifest files via manifest_seal.json when needed."""
    handled: set[str] = set()
    candidates = {
        path for path in (MANIFEST_NAME, MANIFEST_TEXT_NAME)
        if path in zip_file_set and path not in manifest_set
    }
    if not candidates:
        return False, handled

    handled |= candidates

    missing_canonical = {
        path for path in (MANIFEST_NAME, MANIFEST_TEXT_NAME)
        if path not in zip_file_set
    }
    if missing_canonical:
        message = "Manifest seal cannot run; missing files: " + ", ".join(sorted(missing_canonical))
        if strict:
            errors.append(message)
        else:
            warnings.append(message)
        return False, handled

    if MANIFEST_SEAL_NAME not in zip_file_set:
        message = f"Missing {MANIFEST_SEAL_NAME} required for manifest sealing"
        if strict:
            errors.append(message)
        else:
            warnings.append(message)
        return False, handled

    if strict and MANIFEST_SEAL_NAME not in manifest_set:
        errors.append(f"{MANIFEST_SEAL_NAME} must be listed in package manifest under strict mode")

    try:
        seal_raw = zf.read(MANIFEST_SEAL_NAME)
        seal_data = json.loads(seal_raw)
    except (KeyError, RuntimeError, TypeError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        message = f"Cannot parse {MANIFEST_SEAL_NAME}: {exc}"
        if strict:
            errors.append(message)
        else:
            warnings.append(message)
        return False, handled

    if not isinstance(seal_data, dict):
        message = f"{MANIFEST_SEAL_NAME} is not a JSON object"
        if strict:
            errors.append(message)
        else:
            warnings.append(message)
        return False, handled

    valid = True

    schema_version = seal_data.get("schema_version")
    if schema_version != SEAL_SCHEMA_VERSION:
        message = (
            f"{MANIFEST_SEAL_NAME} schema_version mismatch "
            f"(expected {SEAL_SCHEMA_VERSION}, got {schema_version})"
        )
        valid = False
        if strict:
            errors.append(message)
        else:
            warnings.append(message)

    mode = str(seal_data.get("mode", "") or "")
    if mode != SEAL_MODE:
        message = f"{MANIFEST_SEAL_NAME} mode mismatch (expected '{SEAL_MODE}', got '{mode}')"
        valid = False
        if strict:
            errors.append(message)
        else:
            warnings.append(message)

    try:
        manifest_json_raw = zf.read(MANIFEST_NAME)
        manifest_txt_raw = zf.read(MANIFEST_TEXT_NAME)
        computed = compute_manifest_seal_payload(
            manifest_json_raw,
            manifest_txt_raw,
            provenance=None,
        )
    except Exception as exc:
        message = f"Cannot compute manifest seal hashes: {exc}"
        if strict:
            errors.append(message)
        else:
            warnings.append(message)
        return False, handled

    expected_json = str(seal_data.get("sha256_package_manifest_json", "") or "")
    actual_json = computed["sha256_package_manifest_json"]
    if expected_json != actual_json:
        valid = False
        message = (
            "Manifest seal mismatch for package_manifest.json "
            f"(expected {expected_json[:16]}..., got {actual_json[:16]}...)"
        )
        if strict:
            errors.append(message)
        else:
            warnings.append(message)

    expected_txt = str(seal_data.get("sha256_package_manifest_txt", "") or "")
    actual_txt = computed["sha256_package_manifest_txt"]
    if expected_txt != actual_txt:
        valid = False
        message = (
            "Manifest seal mismatch for package_manifest.txt "
            f"(expected {expected_txt[:16]}..., got {actual_txt[:16]}...)"
        )
        if strict:
            errors.append(message)
        else:
            warnings.append(message)

    expected_size_json = seal_data.get("size_package_manifest_json")
    actual_size_json = computed["size_package_manifest_json"]
    if expected_size_json != actual_size_json:
        valid = False
        message = (
            "Manifest seal size mismatch for package_manifest.json "
            f"(expected {expected_size_json}, got {actual_size_json})"
        )
        if strict:
            errors.append(message)
        else:
            warnings.append(message)

    expected_size_txt = seal_data.get("size_package_manifest_txt")
    actual_size_txt = computed["size_package_manifest_txt"]
    if expected_size_txt != actual_size_txt:
        valid = False
        message = (
            "Manifest seal size mismatch for package_manifest.txt "
            f"(expected {expected_size_txt}, got {actual_size_txt})"
        )
        if strict:
            errors.append(message)
        else:
            warnings.append(message)

    if valid:
        counts["sealed_manifest_files"] = len(candidates)
    return valid, handled


def verify_zip(
    zip_path: str | PurePosixPath,
    *,
    options: VerifyOptions | None = None,
) -> dict[str, Any]:
    """Verify a release bundle ZIP and return the report dict.

    This is the reusable core - no stdout, no exit codes.
    """
    verify_options = options or VerifyOptions(strict=True, exclude=DEFAULT_EXCLUDE_RULES)
    report: dict[str, Any] = {
        "zip": _display_zip(zip_path),
        "ok": False,
        "errors": [],
        "warnings": [],
        "diagnostics": [],
        "strict": bool(verify_options.strict),
        "sealed_manifest_verified": False,
        "counts": {
            "total_zip_entries": 0,
            "directory_entries": 0,
            "verifiable_files": 0,
            "manifest_files": 0,
            "verified_files": 0,
            "sealed_manifest_files": 0,
            "skipped_files": 0,
            "extra_files": 0,
            "missing_files": 0,
            "hash_mismatches": 0,
        },
        "skipped": [],
        "extras": [],
        "missing": [],
        "mismatches": [],
        "exclude_rules": [
            {"pattern": rule.pattern, "reason": rule.reason}
            for rule in verify_options.exclude
        ],
        # Compatibility aliases for older consumers.
        "file_count": 0,
        "verified_count": 0,
    }

    errors: list[str] = report["errors"]
    warnings: list[str] = report["warnings"]
    counts: dict[str, int] = report["counts"]

    # ---- Open ZIP ----
    try:
        zf = zipfile.ZipFile(str(zip_path), "r")
    except (zipfile.BadZipFile, FileNotFoundError, OSError) as exc:
        errors.append(f"Cannot open ZIP: {exc}")
        return report

    with zf:
        infos = list(zf.infolist())
        all_names = [i.filename for i in infos]
        names = sorted(set(all_names))

        counts["total_zip_entries"] = len(infos)
        directory_entries = [i for i in infos if _is_directory_entry(i)]
        counts["directory_entries"] = len(directory_entries)

        # ---- Path safety ----
        for name in names:
            pp = PurePosixPath(name)
            if pp.is_absolute():
                errors.append(f"Absolute path in archive: {name}")
            if ".." in pp.parts:
                errors.append(f"Path traversal in archive: {name}")

        seen_paths: set[str] = set()
        duplicate_paths: list[str] = []
        for name in all_names:
            if name in seen_paths:
                duplicate_paths.append(name)
            else:
                seen_paths.add(name)
        if duplicate_paths:
            for path in sorted(set(duplicate_paths)):
                errors.append(f"Duplicate archive entry: {path}")

        # ---- Manifest present? ----
        if MANIFEST_NAME not in seen_paths:
            errors.append(f"Missing {MANIFEST_NAME} in ZIP")
            return report

        # ---- Parse manifest ----
        try:
            raw = zf.read(MANIFEST_NAME)
            manifest = json.loads(raw)
        except (KeyError, RuntimeError, TypeError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            errors.append(f"Cannot parse {MANIFEST_NAME}: {exc}")
            return report

        files: dict[str, Any] = manifest.get("files", {})
        if not isinstance(files, dict):
            errors.append("Manifest 'files' is not a dict")
            return report

        zip_file_set = {i.filename for i in infos if not _is_directory_entry(i)}
        counts["verifiable_files"] = len(zip_file_set)
        manifest_set = set(files.keys())
        counts["manifest_files"] = len(manifest_set)

        missing = sorted(manifest_set - zip_file_set)
        report["missing"] = missing
        counts["missing_files"] = len(missing)
        for path in missing:
            errors.append(f"Missing file: {path}")

        # ---- Hash verification for manifest-listed files ----
        verified_manifest_entries = 0
        mismatches: list[dict[str, str]] = []
        for archive_path in sorted(manifest_set & zip_file_set):
            entry = files.get(archive_path)
            if not isinstance(entry, dict):
                errors.append(f"Manifest entry is not an object: {archive_path}")
                continue
            expected_sha = str(entry.get("sha256", "") or "")
            if not expected_sha:
                errors.append(f"Manifest missing sha256: {archive_path}")
                continue
            actual_sha = _sha256_bytes(zf.read(archive_path))
            if actual_sha != expected_sha:
                mismatches.append(
                    {
                        "path": archive_path,
                        "expected_sha256": expected_sha,
                        "actual_sha256": actual_sha,
                    }
                )
                errors.append(
                    f"Hash mismatch: {archive_path} "
                    f"(expected {expected_sha[:16]}..., got {actual_sha[:16]}...)"
                )
            else:
                verified_manifest_entries += 1
        mismatches.sort(key=lambda row: row["path"])
        report["mismatches"] = mismatches
        counts["hash_mismatches"] = len(mismatches)

        # ---- Extras, exclusions, and sealed manifest classification ----
        extras_all = sorted(zip_file_set - manifest_set)

        seal_ok, seal_handled = _verify_manifest_seal(
            zf=zf,
            zip_file_set=zip_file_set,
            manifest_set=manifest_set,
            strict=verify_options.strict,
            errors=errors,
            warnings=warnings,
            counts=counts,
        )
        report["sealed_manifest_verified"] = seal_ok

        unresolved = [path for path in extras_all if path not in seal_handled]
        skipped: list[dict[str, str]] = []
        extras: list[str] = []
        for path in unresolved:
            reason = _find_exclude_reason(path, verify_options.exclude)
            if reason is not None:
                skipped.append({"path": path, "reason": reason})
            else:
                extras.append(path)

        skipped.sort(key=lambda row: row["path"])
        report["skipped"] = skipped
        counts["skipped_files"] = len(skipped)

        report["extras"] = sorted(extras)
        counts["extra_files"] = len(report["extras"])

        if report["extras"]:
            for path in report["extras"]:
                warnings.append(f"Extra file not in manifest: {path}")
            if verify_options.strict:
                errors.append(
                    f"Strict coverage failed: {len(report['extras'])} extra file(s) not listed in manifest"
                )

        if skipped:
            reason_counts = _count_by_reason(skipped)
            details = ", ".join(f"{count} {reason}" for reason, count in reason_counts.items())
            warnings.append(f"Skipped {len(skipped)} file(s): {details}")

        counts["verified_files"] = verified_manifest_entries + int(counts.get("sealed_manifest_files", 0) or 0)

    report["file_count"] = counts["total_zip_entries"]
    report["verified_count"] = counts["verified_files"]
    report["diagnostics"] = [item.to_dict() for item in _build_bundle_diagnostics(report)]
    report["ok"] = len(errors) == 0
    return report


def _build_bundle_diagnostics(report: dict[str, Any]) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []

    for msg in cast(list[str], report.get("errors", [])):
        diagnostics.append(
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="bundle.verify.error",
                message=str(msg),
                context={},
                hint=None,
            )
        )
    for msg in cast(list[str], report.get("warnings", [])):
        diagnostics.append(
            Diagnostic(
                level=DiagnosticLevel.WARN,
                code="bundle.verify.warning",
                message=str(msg),
                context={},
                hint=None,
            )
        )

    for path in cast(list[str], report.get("extras", [])):
        diagnostics.append(
            Diagnostic(
                level=DiagnosticLevel.WARN,
                code="bundle.verify.extra_file",
                message=f"Extra file not in manifest: {path}",
                context={"path": path},
                hint="Add file to package_manifest.json or explicit exclusion rule.",
            )
        )
    for path in cast(list[str], report.get("missing", [])):
        diagnostics.append(
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="bundle.verify.missing_file",
                message=f"Missing file from archive: {path}",
                context={"path": path},
                hint="Rebuild bundle so package_manifest.json matches archive contents.",
            )
        )
    for row in cast(list[dict[str, str]], report.get("mismatches", [])):
        diagnostics.append(
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="bundle.verify.hash_mismatch",
                message=f"SHA-256 mismatch: {row.get('path', '')}",
                context={
                    "path": str(row.get("path", "") or ""),
                    "expected_sha256": str(row.get("expected_sha256", "") or ""),
                    "actual_sha256": str(row.get("actual_sha256", "") or ""),
                },
                hint="Rebuild bundle and ensure deterministic inputs.",
            )
        )

    for row in cast(list[dict[str, str]], report.get("skipped", [])):
        diagnostics.append(
            Diagnostic(
                level=DiagnosticLevel.INFO,
                code="bundle.verify.skipped_file",
                message=f"Skipped file: {row.get('path', '')}",
                context={
                    "path": str(row.get("path", "") or ""),
                    "reason": str(row.get("reason", "") or ""),
                },
                hint=None,
            )
        )

    return sort_diagnostics(diagnostics)


def format_verify_text(report: dict[str, Any]) -> str:
    """Format a verify report dict as human-readable text."""
    lines: list[str] = []
    lines.append(f"Mesh Bundle Verify: {report.get('zip', '')}")
    lines.append(f"  Strict: {bool(report.get('strict', True))}")
    lines.append(f"  Sealed Manifest Verified: {bool(report.get('sealed_manifest_verified', False))}")
    ok = report.get("ok", False)
    errors = list(report.get("errors", []))
    warnings = list(report.get("warnings", []))
    counts = report.get("counts", {})

    total_zip_entries = int(counts.get("total_zip_entries", report.get("file_count", 0)))
    directory_entries = int(counts.get("directory_entries", 0))
    verifiable_files = int(counts.get("verifiable_files", total_zip_entries))
    manifest_files = int(counts.get("manifest_files", 0))
    verified_files = int(counts.get("verified_files", report.get("verified_count", 0)))
    sealed_manifest_files = int(counts.get("sealed_manifest_files", 0))
    skipped_files = int(counts.get("skipped_files", 0))
    extra_files = int(counts.get("extra_files", 0))
    missing_files = int(counts.get("missing_files", 0))
    hash_mismatches = int(counts.get("hash_mismatches", 0))

    lines.append(f"  Entries: total={total_zip_entries}, directories={directory_entries}, verifiable={verifiable_files}")
    lines.append(
        "  Coverage: "
        f"manifest={manifest_files}, verified={verified_files}, sealed={sealed_manifest_files}, skipped={skipped_files}"
    )
    lines.append(f"  Delta: extras={extra_files}, missing={missing_files}, mismatches={hash_mismatches}")

    if errors:
        for e in errors[:5]:
            lines.append(f"  ERROR: {e}")
        if len(errors) > 5:
            lines.append(f"  ERROR: ... {len(errors) - 5} more")
    if warnings:
        for w in warnings[:5]:
            lines.append(f"  WARN:  {w}")
        if len(warnings) > 5:
            lines.append(f"  WARN:  ... {len(warnings) - 5} more")

    skipped = report.get("skipped", [])
    if isinstance(skipped, list):
        for row in skipped[:5]:
            path = row.get("path", "")
            reason = row.get("reason", "")
            lines.append(f"  SKIP:  {path} ({reason})")
        if len(skipped) > 5:
            lines.append(f"  SKIP:  ... {len(skipped) - 5} more")

    extras = report.get("extras", [])
    if isinstance(extras, list):
        for path in extras[:5]:
            lines.append(f"  EXTRA: {path}")
        if len(extras) > 5:
            lines.append(f"  EXTRA: ... {len(extras) - 5} more")

    missing = report.get("missing", [])
    if isinstance(missing, list):
        for path in missing[:5]:
            lines.append(f"  MISS:  {path}")
        if len(missing) > 5:
            lines.append(f"  MISS:  ... {len(missing) - 5} more")

    mismatches = report.get("mismatches", [])
    if isinstance(mismatches, list):
        for row in mismatches[:5]:
            path = row.get("path", "")
            expected_sha = str(row.get("expected_sha256", "") or "")
            actual_sha = str(row.get("actual_sha256", "") or "")
            lines.append(
                "  HASH:  "
                f"{path} expected={expected_sha[:16]}... actual={actual_sha[:16]}..."
            )
        if len(mismatches) > 5:
            lines.append(f"  HASH:  ... {len(mismatches) - 5} more")

    if ok:
        lines.append(f"  Result: OK ({verified_files}/{verifiable_files} verifiable files verified)")
    else:
        lines.append(f"  Result: FAILED ({len(errors)} errors)")
    return "\n".join(lines)


def _handle_verify(args: argparse.Namespace) -> int:
    zip_path = str(getattr(args, "zip_opt", "") or "").strip() or str(getattr(args, "zip", "") or "").strip()
    if not zip_path:
        print("[Mesh][Bundle] Error: missing zip path (use positional ZIP or --zip)")
        return 2

    use_json = getattr(args, "verify_json", False)
    strict = bool(getattr(args, "verify_strict", True))
    options = VerifyOptions(strict=strict, exclude=DEFAULT_EXCLUDE_RULES)
    report = verify_zip(zip_path, options=options)
    return _finish(report, use_json)


def _finish(report: dict[str, Any], use_json: bool) -> int:
    if use_json:
        from engine.persistence_io import dumps_json_deterministic

        sys.stdout.write(dumps_json_deterministic(report))
        sys.stdout.write("\n")
    else:
        _print_text(report)
    return 0 if report.get("ok") else 1


def _print_text(report: dict[str, Any]) -> None:
    print(format_verify_text(report))
