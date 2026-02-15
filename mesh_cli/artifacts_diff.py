"""CLI command: ``mesh_cli artifacts-diff``

Compares two verify bundles (base vs curr) and summarises regressions,
improvements, and changes.

Headless-safe — no engine or arcade imports.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TIMING_THRESHOLD_MS = 50


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON file; return *None* on missing/corrupt/non-dict."""
    if not path.exists() or not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _locate_report(artifacts_dir: Path) -> dict[str, Any] | None:
    """Find and read ``verify_report.json`` from an artifacts dir.

    Prefers using ``index.json`` to discover the report path, falling
    back to a direct read of ``verify_report.json``.
    """
    index = _safe_read_json(artifacts_dir / "index.json")
    if index is not None:
        written = index.get("written", {})
        if isinstance(written, dict):
            report_path = written.get("verify_report")
            if isinstance(report_path, str):
                # Normalise: strip leading artifacts/ prefix
                parts = report_path.replace("\\", "/").split("/")
                if len(parts) > 1:
                    report_path = "/".join(parts[1:])
                candidate = artifacts_dir / report_path
                data = _safe_read_json(candidate)
                if data is not None:
                    return data
    # Fallback
    return _safe_read_json(artifacts_dir / "verify_report.json")


def _get_index_schemas(artifacts_dir: Path) -> dict[str, int]:
    """Return ``{artifact_key: schema_version}`` from ``index.json``."""
    index = _safe_read_json(artifacts_dir / "index.json")
    if index is None:
        return {}
    schemas = index.get("schemas", {})
    if not isinstance(schemas, dict):
        return {}
    return {k: v for k, v in schemas.items() if isinstance(v, int)}


# ---------------------------------------------------------------------------
# Field extraction (best-effort, None-safe)
# ---------------------------------------------------------------------------


def _dig(data: dict[str, Any] | None, *keys: str) -> Any:
    """Traverse nested dicts.  Returns *None* on any miss."""
    cur: Any = data
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------

class DiffItem:
    """One changed field between base and curr."""

    __slots__ = ("field", "base_val", "curr_val", "category")

    def __init__(self, field: str, base_val: Any, curr_val: Any, category: str) -> None:
        self.field = field
        self.base_val = base_val
        self.curr_val = curr_val
        self.category = category  # regression | improvement | changed

    def __repr__(self) -> str:
        return f"DiffItem({self.field!r}, {self.base_val!r}->{self.curr_val!r}, {self.category})"


def _classify_ok_flip(base_ok: Any, curr_ok: Any) -> str | None:
    """Classify a boolean-ish ok field change.

    Returns ``'regression'``, ``'improvement'``, ``'changed'`` or *None* (no change).
    """
    # Normalise to bool|None
    def _norm(v: Any) -> bool | None:
        if v is True:
            return True
        if v is False:
            return False
        return None

    b, c = _norm(base_ok), _norm(curr_ok)
    if b == c:
        return None
    # true->false or None->false  → regression
    if c is False and b in (True, None):
        return "regression"
    # false->true or None->true   → improvement
    if c is True and b in (False, None):
        return "improvement"
    return "changed"


def compute_diff(
    base: dict[str, Any],
    curr: dict[str, Any],
    *,
    base_schemas: dict[str, int] | None = None,
    curr_schemas: dict[str, int] | None = None,
    timing_threshold_ms: int = _DEFAULT_TIMING_THRESHOLD_MS,
) -> list[DiffItem]:
    """Compare two verify_report payloads and return diff items.

    Items are returned in deterministic order (sorted by field name within
    each category, categories in order: regression, improvement, changed).
    """
    items: list[DiffItem] = []

    # --- verify_summary.ok ---
    base_ok = _dig(base, "verify_summary", "ok")
    curr_ok = _dig(curr, "verify_summary", "ok")
    cat = _classify_ok_flip(base_ok, curr_ok)
    if cat is not None:
        items.append(DiffItem("verify_summary.ok", base_ok, curr_ok, cat))

    # --- budgets ---
    for budget_key in ("exception_budget", "verify_step_budget", "authoring_trace_budget"):
        b_ok = _dig(base, "budgets", budget_key, "ok")
        c_ok = _dig(curr, "budgets", budget_key, "ok")
        cat = _classify_ok_flip(b_ok, c_ok)
        if cat is not None:
            items.append(DiffItem(f"budgets.{budget_key}.ok", b_ok, c_ok, cat))

    # --- swallowed_exceptions ---
    b_total = _dig(base, "runtime_diagnostics", "swallowed_exceptions", "total")
    c_total = _dig(curr, "runtime_diagnostics", "swallowed_exceptions", "total")
    if isinstance(b_total, (int, float)) and isinstance(c_total, (int, float)):
        if c_total > b_total:
            items.append(DiffItem("swallowed_exceptions.total", b_total, c_total, "regression"))
        elif c_total < b_total:
            items.append(DiffItem("swallowed_exceptions.total", b_total, c_total, "improvement"))

    b_distinct = _dig(base, "runtime_diagnostics", "swallowed_exceptions", "distinct")
    c_distinct = _dig(curr, "runtime_diagnostics", "swallowed_exceptions", "distinct")
    if isinstance(b_distinct, (int, float)) and isinstance(c_distinct, (int, float)):
        if c_distinct > b_distinct:
            items.append(DiffItem("swallowed_exceptions.distinct", b_distinct, c_distinct, "regression"))
        elif c_distinct < b_distinct:
            items.append(DiffItem("swallowed_exceptions.distinct", b_distinct, c_distinct, "improvement"))

    b_sw_ok = _dig(base, "runtime_diagnostics", "swallowed_exceptions", "ok")
    c_sw_ok = _dig(curr, "runtime_diagnostics", "swallowed_exceptions", "ok")
    cat = _classify_ok_flip(b_sw_ok, c_sw_ok)
    if cat is not None:
        items.append(DiffItem("swallowed_exceptions.ok", b_sw_ok, c_sw_ok, cat))

    # --- shadow_backend ---
    b_selected = _dig(base, "runtime_diagnostics", "shadow_backend", "selected")
    c_selected = _dig(curr, "runtime_diagnostics", "shadow_backend", "selected")
    if b_selected is not None and c_selected is not None and b_selected != c_selected:
        items.append(DiffItem("shadow_backend.selected", b_selected, c_selected, "changed"))

    b_reason = _dig(base, "runtime_diagnostics", "shadow_backend", "reason")
    c_reason = _dig(curr, "runtime_diagnostics", "shadow_backend", "reason")
    if b_reason is not None and c_reason is not None and b_reason != c_reason:
        items.append(DiffItem("shadow_backend.reason", b_reason, c_reason, "changed"))

    # --- timing ---
    # Skip timing comparison when base total_ms is 0 (sentinel for "no
    # timing baseline"), which avoids false regressions when comparing a
    # seed baseline against a real run.
    b_total_ms = _dig(base, "timing", "total_ms")
    c_total_ms = _dig(curr, "timing", "total_ms")
    if (
        isinstance(b_total_ms, (int, float))
        and isinstance(c_total_ms, (int, float))
        and int(b_total_ms) != 0
    ):
        delta = int(c_total_ms) - int(b_total_ms)
        if abs(delta) > timing_threshold_ms:
            cat = "regression" if delta > 0 else "improvement"
            items.append(DiffItem("timing.total_ms", int(b_total_ms), int(c_total_ms), cat))

    # --- schema_version changes (from index.json) ---
    if base_schemas and curr_schemas:
        all_keys = sorted(set(base_schemas) | set(curr_schemas))
        for key in all_keys:
            bv = base_schemas.get(key)
            cv = curr_schemas.get(key)
            if bv is not None and cv is not None and bv != cv:
                items.append(DiffItem(f"schema.{key}", bv, cv, "changed"))

    # --- deterministic sort: category order then field name ---
    _cat_order = {"regression": 0, "improvement": 1, "changed": 2}
    items.sort(key=lambda it: (_cat_order.get(it.category, 9), it.field))
    return items


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _format_val(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def format_text(items: list[DiffItem]) -> str:
    """Render diff items as plain text report."""
    sections: dict[str, list[DiffItem]] = {
        "regression": [],
        "improvement": [],
        "changed": [],
    }
    for it in items:
        sections.setdefault(it.category, []).append(it)

    lines: list[str] = ["=== Artifacts Diff ===", ""]

    # Unchanged count
    has_any = any(bool(v) for v in sections.values())

    if sections["regression"]:
        lines.append("REGRESSIONS:")
        for it in sections["regression"]:
            lines.append(f"  {it.field}: {_format_val(it.base_val)} -> {_format_val(it.curr_val)}")
        lines.append("")

    if sections["improvement"]:
        lines.append("IMPROVEMENTS:")
        for it in sections["improvement"]:
            lines.append(f"  {it.field}: {_format_val(it.base_val)} -> {_format_val(it.curr_val)}")
        lines.append("")

    if sections["changed"]:
        lines.append("CHANGED:")
        for it in sections["changed"]:
            lines.append(f"  {it.field}: {_format_val(it.base_val)} -> {_format_val(it.curr_val)}")
        lines.append("")

    if not has_any:
        lines.append("No differences detected.")
        lines.append("")

    reg = len(sections["regression"])
    imp = len(sections["improvement"])
    chg = len(sections["changed"])
    lines.append(f"Summary: {reg} regression(s), {imp} improvement(s), {chg} changed")
    return "\n".join(lines)


def format_markdown(items: list[DiffItem]) -> str:
    """Render diff items as GitHub-flavoured markdown."""
    sections: dict[str, list[DiffItem]] = {
        "regression": [],
        "improvement": [],
        "changed": [],
    }
    for it in items:
        sections.setdefault(it.category, []).append(it)

    lines: list[str] = ["# Artifacts Diff", ""]

    has_any = any(bool(v) for v in sections.values())

    if sections["regression"]:
        lines.append("## Regressions")
        lines.append("")
        lines.append("| Field | Base | Current |")
        lines.append("|-------|------|---------|")
        for it in sections["regression"]:
            lines.append(f"| `{it.field}` | {_format_val(it.base_val)} | {_format_val(it.curr_val)} |")
        lines.append("")

    if sections["improvement"]:
        lines.append("## Improvements")
        lines.append("")
        lines.append("| Field | Base | Current |")
        lines.append("|-------|------|---------|")
        for it in sections["improvement"]:
            lines.append(f"| `{it.field}` | {_format_val(it.base_val)} | {_format_val(it.curr_val)} |")
        lines.append("")

    if sections["changed"]:
        lines.append("## Changed")
        lines.append("")
        lines.append("| Field | Base | Current |")
        lines.append("|-------|------|---------|")
        for it in sections["changed"]:
            lines.append(f"| `{it.field}` | {_format_val(it.base_val)} | {_format_val(it.curr_val)} |")
        lines.append("")

    if not has_any:
        lines.append("No differences detected.")
        lines.append("")

    reg = len(sections["regression"])
    imp = len(sections["improvement"])
    chg = len(sections["changed"])
    lines.append(f"**Summary:** {reg} regression(s), {imp} improvement(s), {chg} changed")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def diff_artifacts(
    base_dir: Path,
    curr_dir: Path,
    *,
    fmt: str = "text",
    timing_threshold_ms: int = _DEFAULT_TIMING_THRESHOLD_MS,
) -> tuple[str, bool]:
    """Compare two artifact directories.

    Returns ``(formatted_output, has_regressions)``.
    """
    base_report = _locate_report(base_dir)
    curr_report = _locate_report(curr_dir)

    if base_report is None and curr_report is None:
        msg = "error: verify_report.json not found in either base or curr"
        return msg, False
    if base_report is None:
        msg = f"error: verify_report.json not found in base ({base_dir.as_posix()})"
        return msg, False
    if curr_report is None:
        msg = f"error: verify_report.json not found in curr ({curr_dir.as_posix()})"
        return msg, False

    base_schemas = _get_index_schemas(base_dir)
    curr_schemas = _get_index_schemas(curr_dir)

    items = compute_diff(
        base_report,
        curr_report,
        base_schemas=base_schemas,
        curr_schemas=curr_schemas,
        timing_threshold_ms=timing_threshold_ms,
    )

    has_regressions = any(it.category == "regression" for it in items)

    if fmt == "markdown":
        output = format_markdown(items)
    else:
        output = format_text(items)

    return output, has_regressions


# ---------------------------------------------------------------------------
# Baseline update
# ---------------------------------------------------------------------------

_BASELINE_FILES = ("verify_report.json", "index.json")


def update_baseline(baseline_dir: Path, curr_dir: Path) -> tuple[int, list[str]]:
    """Copy minimal baseline files from *curr_dir* into *baseline_dir*.

    Returns ``(exit_code, messages)`` where *messages* lists what was
    copied (or errors).  Exit 0 on success, 2 on missing source files.
    """
    messages: list[str] = []
    missing: list[str] = []

    for name in _BASELINE_FILES:
        src = curr_dir / name
        if not src.exists() or not src.is_file():
            missing.append(name)
            continue

    if missing:
        for name in missing:
            messages.append(f"error: {name} not found in {curr_dir.as_posix()}")
        return 2, messages

    baseline_dir.mkdir(parents=True, exist_ok=True)

    for name in _BASELINE_FILES:
        src = curr_dir / name
        dst = baseline_dir / name
        shutil.copy2(str(src), str(dst))
        messages.append(f"updated: {dst.as_posix()}")

    return 0, messages


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------


def _resolve_dir(raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _handle_artifacts_diff(args: argparse.Namespace) -> int:
    base_dir = _resolve_dir(args.base)
    curr_dir = _resolve_dir(args.curr)

    # --- update-baseline mode ---
    if getattr(args, "update_baseline", False):
        if not curr_dir.exists() or not curr_dir.is_dir():
            print(f"error: curr directory not found: {curr_dir.as_posix()}", file=sys.stderr)
            return 2
        code, messages = update_baseline(base_dir, curr_dir)
        for msg in messages:
            print(msg)
        return code

    # --- diff mode ---
    for label, d in [("base", base_dir), ("curr", curr_dir)]:
        if not d.exists() or not d.is_dir():
            print(f"error: {label} directory not found: {d.as_posix()}", file=sys.stderr)
            return 2

    fmt = getattr(args, "format", "text") or "text"
    fail_on_regression = getattr(args, "fail_on_regression", False)

    output, has_regressions = diff_artifacts(base_dir, curr_dir, fmt=fmt)
    print(output)

    if fail_on_regression and has_regressions:
        return 2
    return 0


def register(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "artifacts-diff",
        help="Compare two verify artifact bundles and summarise regressions",
    )
    parser.add_argument(
        "--base",
        required=True,
        help="Base (reference) artifacts directory",
    )
    parser.add_argument(
        "--curr",
        required=True,
        help="Current artifacts directory to compare against base",
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        default=False,
        help="Exit 2 if any regression detected",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        default=False,
        help="Copy minimal baseline files from --curr into --base (overwrites)",
    )
    parser.set_defaults(func=_handle_artifacts_diff)


def handle(args: argparse.Namespace) -> int:
    return _handle_artifacts_diff(args)
