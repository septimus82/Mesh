"""Deterministic scanner for exception-handling policies.

Scans Python source files and reports:
- BLE001 suppression count  (``# noqa: BLE001``)
- Broad-catch count          (``except Exception`` / bare ``except:``)
- Silent broad-catch count   (broad catches lacking SWALLOW logging or re-raise)

Usage::

    python -m tooling.scan_exception_policies [--roots engine mesh_cli tooling] \\
        [--artifact artifacts/exception_policy_scan.json]

Exit codes:
    0  scan succeeded (artifact written)
    1  unexpected error
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_BLE001_RE = re.compile(r"#\s*noqa:.*\bBLE001\b")
_BLE001_WITH_REASON_RE = re.compile(r"#\s*noqa:.*\bBLE001\b.*#\s*REASON:")

_EXCEPT_PASS_RE = re.compile(
    r"^\s*except\s*(Exception|BaseException)?\s*"
    r"(\s+as\s+\w+)?\s*:\s*"
    r"(pass\s*$|pass\s*#)",
    re.MULTILINE,
)

# Matches ``except Exception``, ``except BaseException``, bare ``except:``
_BROAD_CATCH_RE = re.compile(
    r"^\s*except\s*(Exception|BaseException)?\s*(\s+as\s+\w+)?\s*:",
)

# Patterns that make a broad-catch "observable" (non-silent)
_SWALLOW_LOGGING_RE = re.compile(
    r"""(?x)
      _log_swallow\s*\(                        # helper call
    | logger\.\w+\s*\(.*exc_info\s*=\s*True    # logger.xxx(..., exc_info=True)
    | SWALLOW\[                                 # SWALLOW[TAG] inline
    | logger\.exception\s*\(                    # logger.exception(...)
    """,
)

_RAISE_RE = re.compile(r"^\s*raise\b")


# ---------------------------------------------------------------------------
# AST-based scanner
# ---------------------------------------------------------------------------

def _handler_is_broad(handler: ast.ExceptHandler) -> bool:
    """Return ``True`` if the handler is a broad catch.

    Broad means: bare ``except:``, ``except Exception:``, or
    ``except BaseException:``.
    """
    if handler.type is None:
        return True  # bare except:
    if isinstance(handler.type, ast.Name) and handler.type.id in (
        "Exception",
        "BaseException",
    ):
        return True
    return False


def _handler_kind(handler: ast.ExceptHandler) -> str:
    """Human label for the except clause."""
    if handler.type is None:
        return "bare-except"
    if isinstance(handler.type, ast.Name):
        return f"except-{handler.type.id}"
    return "except-other"


def _body_has_raise(body: list[ast.stmt]) -> bool:
    """Check whether the handler body contains a ``raise`` statement."""
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, ast.Raise):
            return True
    return False


def _body_lines(source_lines: list[str], handler: ast.ExceptHandler) -> str:
    """Return the source text of the except-handler body."""
    start = handler.lineno  # 1-based; body starts after ``except ...:``
    end = handler.end_lineno or start
    return "\n".join(source_lines[start:end])  # start is already past the except line


def _handler_is_silent(
    handler: ast.ExceptHandler,
    source_lines: list[str],
) -> bool:
    """A broad-catch is *silent* if it has no SWALLOW logging and no re-raise."""
    if _body_has_raise(handler.body):
        return False
    body_text = _body_lines(source_lines, handler)
    if _SWALLOW_LOGGING_RE.search(body_text):
        return False
    return True


# ---------------------------------------------------------------------------
# File scanner
# ---------------------------------------------------------------------------

def _scan_file(
    filepath: Path,
    rel_root: Path,
) -> dict[str, Any]:
    """Scan a single Python file.  Returns per-file metrics."""
    rel = filepath.relative_to(rel_root).as_posix()
    try:
        raw = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"file": rel, "ble001": 0, "ble001_missing_reason": 0, "broad": 0, "silent": []}

    lines = raw.splitlines()
    ble001_total = 0
    ble001_missing_reason = 0
    for ln in lines:
        if _BLE001_RE.search(ln):
            ble001_total += 1
            if not _BLE001_WITH_REASON_RE.search(ln):
                ble001_missing_reason += 1
    
    except_pass_count = len(_EXCEPT_PASS_RE.findall(raw))

    broad_count = 0
    silent_entries: list[dict[str, Any]] = []

    try:
        tree = ast.parse(raw, filename=str(filepath))
    except SyntaxError:
        return {
            "file": rel,
            "ble001": ble001_total,
            "ble001_missing_reason": ble001_missing_reason,
            "except_pass": except_pass_count,
            "broad": 0,
            "silent": [],
        }

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _handler_is_broad(node):
            continue
        broad_count += 1
        if _handler_is_silent(node, lines):
            silent_entries.append({
                "file": rel,
                "line": node.lineno,
                "kind": _handler_kind(node),
            })

    return {
        "file": rel,
        "ble001": ble001_total,
        "ble001_missing_reason": ble001_missing_reason,
        "except_pass": except_pass_count,
        "broad": broad_count,
        "silent": silent_entries,
    }


# ---------------------------------------------------------------------------
# Aggregate scanner
# ---------------------------------------------------------------------------

def scan(
    roots: list[str],
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Run the full exception-policy scan and return the result dict."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]

    all_files: list[Path] = []
    for root_name in sorted(roots):
        root_dir = repo_root / root_name
        if not root_dir.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(root_dir):
            dp = Path(dirpath)
            for fn in sorted(filenames):
                if fn.endswith(".py"):
                    all_files.append(dp / fn)

    # Deterministic order
    all_files.sort(key=lambda p: p.relative_to(repo_root).as_posix())

    total_ble001 = 0
    total_ble001_missing_reason = 0
    total_except_pass = 0
    total_broad = 0
    all_silent: list[dict[str, Any]] = []
    ble001_per_file: dict[str, int] = {}
    ble001_missing_reason_per_file: dict[str, int] = {}
    silent_per_file: dict[str, int] = {}

    for fp in all_files:
        result = _scan_file(fp, repo_root)
        total_ble001 += result["ble001"]
        total_ble001_missing_reason += result["ble001_missing_reason"]
        total_except_pass += result.get("except_pass", 0)
        total_broad += result["broad"]
        all_silent.extend(result["silent"])
        if result["ble001"] > 0:
            ble001_per_file[result["file"]] = result["ble001"]
        if result["ble001_missing_reason"] > 0:
            ble001_missing_reason_per_file[result["file"]] = result["ble001_missing_reason"]
        if result["silent"]:
            silent_per_file[result["file"]] = len(result["silent"])

    # Top offenders sorted descending
    ble001_top = sorted(ble001_per_file.items(), key=lambda t: (-t[1], t[0]))
    ble001_missing_reason_top = sorted(ble001_missing_reason_per_file.items(), key=lambda t: (-t[1], t[0]))
    silent_top = sorted(silent_per_file.items(), key=lambda t: (-t[1], t[0]))

    return {
        "schema_version": 1,
        "ble001_count_total": total_ble001,
        "ble001_missing_reason_count": total_ble001_missing_reason,
        "except_pass_count_total": total_except_pass,
        "broad_catch_count_total": total_broad,
        "silent_broad_catch_count_total": len(all_silent),
        "top_offenders": {
            "ble001": [{"file": f, "count": c} for f, c in ble001_top[:20]],
            "ble001_missing_reason": [{"file": f, "count": c} for f, c in ble001_missing_reason_top[:20]],
            "silent_broad_catch": [
                {"file": f, "count": c} for f, c in silent_top[:20]
            ],
        },
        "silent_broad_catches": all_silent,
        "files_scanned": len(all_files),
        "roots": sorted(roots),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan exception-handling policies across Python sources.",
    )
    parser.add_argument(
        "--roots",
        nargs="+",
        default=["engine", "mesh_cli", "tooling"],
        help="Top-level directories to scan",
    )
    parser.add_argument(
        "--artifact",
        default="artifacts/exception_policy_scan.json",
        help="Output artifact path",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    result = scan(args.roots, repo_root=repo_root)

    artifact_path = repo_root / args.artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(result, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    print(f"[exception-policy-scan] BLE001 total: {result['ble001_count_total']}")
    print(f"[exception-policy-scan] BLE001 missing REASON: {result['ble001_missing_reason_count']}")
    print(f"[exception-policy-scan] broad catches: {result['broad_catch_count_total']}")
    print(
        f"[exception-policy-scan] silent broad catches: "
        f"{result['silent_broad_catch_count_total']}"
    )
    print(f"[exception-policy-scan] artifact: {artifact_path.relative_to(repo_root).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
