from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
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


def _repo_root_from_module() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_artifacts_dir(repo_root: Path, raw: str) -> Path:
    path = Path(str(raw or "artifacts"))
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return int(value)
    return None


def _as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _text_bool(value: bool | None) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "?"


def _text_int(value: int | None) -> str:
    return str(value) if value is not None else "?"


def _read_public_api_semver(repo_root: Path) -> str:
    version_path = repo_root / "engine" / "public_api" / "version.py"
    if not version_path.exists():
        return "?"
    try:
        text = version_path.read_text(encoding="utf-8")
    except OSError:
        return "?"
    match = re.search(r'^PUBLIC_API_SEMVER\s*=\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    if match is None:
        return "?"
    value = str(match.group(1)).strip()
    return value or "?"


def _normalize_sites(value: object, *, max_sites: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, list):
        for row in value:
            if not isinstance(row, dict):
                continue
            site = row.get("site")
            count = _as_int(row.get("count"))
            if isinstance(site, str) and count is not None:
                rows.append({"site": site, "count": count})
    elif isinstance(value, dict):
        for site, count_raw in value.items():
            count = _as_int(count_raw)
            if count is None:
                continue
            rows.append({"site": str(site), "count": count})
    rows.sort(key=lambda item: (-int(item["count"]), str(item["site"])))
    return rows[: max(0, int(max_sites))]


def _normalize_steps(value: object, *, max_steps: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, list):
        for row in value:
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            ms = _as_int(row.get("ms"))
            ok = _as_bool(row.get("ok"))
            if isinstance(name, str) and ms is not None:
                rows.append({"name": name, "ms": ms, "ok": ok})
    rows.sort(key=lambda item: (-int(item["ms"]), str(item["name"])))
    return rows[: max(0, int(max_steps))]


def _format_failing_steps(steps: list[str]) -> str:
    if not steps:
        return "[]"
    return "[" + ", ".join(steps) + "]"


def _format_top_sites(sites: list[dict[str, Any]]) -> str:
    if not sites:
        return "(none)"
    parts = [f"{row['site']}={row['count']}" for row in sites]
    return "(" + ", ".join(parts) + ")"


def _extract_verify_snapshot(
    *,
    artifacts_dir: Path,
    max_sites: int,
    max_steps: int,
) -> tuple[dict[str, Any], list[str]]:
    files_read: set[str] = set()
    verify_ok: bool | None = None
    failing_steps: list[str] = []
    exception_current: int | None = None
    exception_baseline: int | None = None
    exception_ok: bool | None = None
    step_budget_ok: bool | None = None
    step_budget_worst: str | None = None
    step_budget_delta_ms: int | None = None
    authoring_trace_budget_ok: bool | None = None
    verify_total_ms: int | None = None
    swallowed_total: int | None = None
    swallowed_distinct: int | None = None
    swallowed_sites: list[dict[str, Any]] = []
    shadow_selected: str | None = None
    shadow_reason: str | None = None
    slowest_steps: list[dict[str, Any]] = []

    index_payload = _safe_read_json(artifacts_dir / "index.json")
    if index_payload is not None:
        files_read.add("index.json")

    verify_report_payload = _safe_read_json(artifacts_dir / "verify_report.json")
    if verify_report_payload is not None:
        files_read.add("verify_report.json")
        verify_summary = verify_report_payload.get("verify_summary")
        if isinstance(verify_summary, dict):
            verify_ok = _as_bool(verify_summary.get("ok"))
            raw_failing = verify_summary.get("failing_steps")
            if isinstance(raw_failing, list):
                failing_steps = sorted(str(item) for item in raw_failing)

        budgets = verify_report_payload.get("budgets")
        if isinstance(budgets, dict):
            exception_budget = budgets.get("exception_budget")
            if isinstance(exception_budget, dict):
                exception_current = _as_int(exception_budget.get("current_count"))
                exception_baseline = _as_int(exception_budget.get("baseline_count"))
                exception_ok = _as_bool(exception_budget.get("ok"))
            step_budget = budgets.get("verify_step_budget")
            if isinstance(step_budget, dict):
                step_budget_ok = _as_bool(step_budget.get("ok"))
                worst = step_budget.get("worst_offender")
                if isinstance(worst, dict):
                    name = worst.get("name")
                    if isinstance(name, str):
                        step_budget_worst = name
                    step_budget_delta_ms = _as_int(worst.get("delta_ms"))
            trace_budget = budgets.get("authoring_trace_budget")
            if isinstance(trace_budget, dict):
                authoring_trace_budget_ok = _as_bool(trace_budget.get("ok"))

        timing = verify_report_payload.get("timing")
        if isinstance(timing, dict):
            verify_total_ms = _as_int(timing.get("total_ms"))
            slowest_steps = _normalize_steps(timing.get("top5"), max_steps=max_steps)

        runtime_diagnostics = verify_report_payload.get("runtime_diagnostics")
        if isinstance(runtime_diagnostics, dict):
            swallowed = runtime_diagnostics.get("swallowed_exceptions")
            if isinstance(swallowed, dict):
                swallowed_total = _as_int(swallowed.get("total"))
                swallowed_distinct = _as_int(swallowed.get("distinct"))
                swallowed_sites = _normalize_sites(swallowed.get("top5_sites"), max_sites=max_sites)
            shadow = runtime_diagnostics.get("shadow_backend")
            if isinstance(shadow, dict):
                selected = shadow.get("selected")
                reason = shadow.get("reason")
                if isinstance(selected, str):
                    shadow_selected = selected
                if isinstance(reason, str):
                    shadow_reason = reason

    verify_all_summary_payload = _safe_read_json(artifacts_dir / "verify_all_summary.json")
    if verify_all_summary_payload is not None:
        files_read.add("verify_all_summary.json")
        if verify_ok is None:
            verify_ok = _as_bool(verify_all_summary_payload.get("ok"))
        if not failing_steps:
            raw_steps = verify_all_summary_payload.get("steps")
            rows: list[str] = []
            if isinstance(raw_steps, list):
                for row in raw_steps:
                    if not isinstance(row, dict):
                        continue
                    if row.get("ok") is False:
                        name = row.get("name")
                        if isinstance(name, str):
                            rows.append(name)
            failing_steps = sorted(rows)

    exception_budget_payload = _safe_read_json(artifacts_dir / "exception_budget.json")
    if exception_budget_payload is not None:
        files_read.add("exception_budget.json")
        if exception_current is None:
            exception_current = _as_int(exception_budget_payload.get("current_count"))
        if exception_baseline is None:
            exception_baseline = _as_int(exception_budget_payload.get("baseline_count"))
        if exception_ok is None:
            exception_ok = _as_bool(exception_budget_payload.get("ok"))

    step_budget_payload = _safe_read_json(artifacts_dir / "verify_step_budget_check.json")
    if step_budget_payload is not None:
        files_read.add("verify_step_budget_check.json")
        if step_budget_ok is None:
            step_budget_ok = _as_bool(step_budget_payload.get("ok"))
        if step_budget_worst is None or step_budget_delta_ms is None:
            offenders = step_budget_payload.get("offenders")
            rows2: list[tuple[int, str]] = []
            if isinstance(offenders, list):
                for row in offenders:
                    if not isinstance(row, dict):
                        continue
                    name = row.get("name")
                    delta = _as_int(row.get("delta_ms"))
                    if isinstance(name, str) and delta is not None:
                        rows2.append((delta, name))
            rows2.sort(key=lambda item: (-item[0], item[1]))
            if rows2:
                step_budget_delta_ms, step_budget_worst = rows2[0]
            elif step_budget_ok is True and step_budget_worst is None:
                step_budget_worst = "none"

        trace_budget_payload = _safe_read_json(artifacts_dir / "authoring_trace_budget_check.json")
        if trace_budget_payload is not None:
            files_read.add("authoring_trace_budget_check.json")
            if authoring_trace_budget_ok is None:
                authoring_trace_budget_ok = _as_bool(trace_budget_payload.get("ok"))

    verify_durations_payload = _safe_read_json(artifacts_dir / "verify_step_durations.json")
    if verify_durations_payload is not None:
        files_read.add("verify_step_durations.json")
        if verify_total_ms is None:
            verify_total_ms = _as_int(verify_durations_payload.get("total_ms"))
        steps = _normalize_steps(verify_durations_payload.get("steps"), max_steps=max_steps)
        if steps:
            slowest_steps = steps

    swallowed_payload = _safe_read_json(artifacts_dir / "swallowed_exceptions.json")
    if swallowed_payload is not None:
        files_read.add("swallowed_exceptions.json")
        if swallowed_total is None:
            swallowed_total = _as_int(swallowed_payload.get("total"))
        if swallowed_distinct is None:
            swallowed_distinct = _as_int(swallowed_payload.get("distinct"))
        if not swallowed_sites:
            swallowed_sites = _normalize_sites(swallowed_payload.get("per_site"), max_sites=max_sites)

    shadow_payload = _safe_read_json(artifacts_dir / "shadow_backend.json")
    if shadow_payload is not None:
        files_read.add("shadow_backend.json")
        if shadow_selected is None:
            selected2 = shadow_payload.get("selected")
            if isinstance(selected2, str):
                shadow_selected = selected2
        if shadow_reason is None:
            reason2 = shadow_payload.get("reason")
            if isinstance(reason2, str):
                shadow_reason = reason2

    snapshot = {
        "verify_ok": verify_ok,
        "failing_steps": failing_steps,
        "exception_current": exception_current,
        "exception_baseline": exception_baseline,
        "exception_ok": exception_ok,
        "step_budget_ok": step_budget_ok,
        "step_budget_worst": step_budget_worst,
        "step_budget_delta_ms": step_budget_delta_ms,
        "authoring_trace_budget_ok": authoring_trace_budget_ok,
        "verify_total_ms": verify_total_ms,
        "slowest_steps": slowest_steps,
        "swallowed_total": swallowed_total,
        "swallowed_distinct": swallowed_distinct,
        "swallowed_sites": swallowed_sites,
        "shadow_selected": shadow_selected,
        "shadow_reason": shadow_reason,
    }
    return snapshot, sorted(files_read)


def build_release_notes_payload(
    artifacts_dir: Path,
    *,
    title: str | None = None,
    max_sites: int = 5,
    max_steps: int = 5,
) -> dict[str, Any]:
    repo_root = _repo_root_from_module()
    package_version = get_tool_version()
    public_api_semver = _read_public_api_semver(repo_root)
    title_text = (str(title).strip() if title is not None else "") or f"Mesh Engine {package_version}"
    snapshot, files_read = _extract_verify_snapshot(
        artifacts_dir=artifacts_dir,
        max_sites=max_sites,
        max_steps=max_steps,
    )
    return {
        "schema_version": 1,
        "title": title_text,
        "package_version": package_version,
        "public_api_semver": public_api_semver,
        "bundle": artifacts_dir.as_posix(),
        "snapshot": snapshot,
        "files_read": files_read,
    }


def build_release_notes(
    artifacts_dir: Path,
    title: str | None = None,
    max_sites: int = 5,
    max_steps: int = 5,
) -> str:
    payload = build_release_notes_payload(
        artifacts_dir,
        title=title,
        max_sites=max_sites,
        max_steps=max_steps,
    )
    snapshot = payload["snapshot"] if isinstance(payload.get("snapshot"), dict) else {}
    failing_steps = snapshot.get("failing_steps") if isinstance(snapshot, dict) else []
    if not isinstance(failing_steps, list):
        failing_steps = []
    failing_steps_text = _format_failing_steps([str(item) for item in failing_steps])

    authoring_trace_budget_ok = snapshot.get("authoring_trace_budget_ok") if isinstance(snapshot, dict) else None
    include_trace_budget = isinstance(authoring_trace_budget_ok, bool)

    step_budget_worst = snapshot.get("step_budget_worst") if isinstance(snapshot, dict) else None
    step_budget_delta_ms = _as_int(snapshot.get("step_budget_delta_ms")) if isinstance(snapshot, dict) else None
    if not isinstance(step_budget_worst, str):
        step_budget_worst = "?"
    if step_budget_worst == "" and _as_bool(snapshot.get("step_budget_ok")) is True:
        step_budget_worst = "none"

    slowest_steps = snapshot.get("slowest_steps") if isinstance(snapshot, dict) else []
    rows = slowest_steps if isinstance(slowest_steps, list) else []

    swallowed_sites = snapshot.get("swallowed_sites") if isinstance(snapshot, dict) else []
    sites = swallowed_sites if isinstance(swallowed_sites, list) else []

    lines: list[str] = [
        f"# {payload.get('title', '?')}",
        f"- Package: {payload.get('package_version', '?')}",
        f"- Public API: {payload.get('public_api_semver', '?')}",
        (
            "- Verify: "
            f"ok={_text_bool(_as_bool(snapshot.get('verify_ok')) if isinstance(snapshot, dict) else None)}, "
            f"failing_steps={failing_steps_text}"
        ),
        f"- Bundle: {payload.get('bundle', '?')}",
        "",
        "## Budgets",
        (
            "- Exception budget: "
            f"{_text_int(_as_int(snapshot.get('exception_current')) if isinstance(snapshot, dict) else None)}/"
            f"{_text_int(_as_int(snapshot.get('exception_baseline')) if isinstance(snapshot, dict) else None)} "
            f"ok={_text_bool(_as_bool(snapshot.get('exception_ok')) if isinstance(snapshot, dict) else None)}"
        ),
        (
            "- Step budget: "
            f"ok={_text_bool(_as_bool(snapshot.get('step_budget_ok')) if isinstance(snapshot, dict) else None)} "
            f"worst={step_budget_worst} delta_ms={_text_int(step_budget_delta_ms)}"
        ),
    ]
    if include_trace_budget:
        lines.append(
            "- Authoring trace budget: "
            f"ok={_text_bool(_as_bool(authoring_trace_budget_ok))}"
        )
    lines.append(f"- Total verify ms: {_text_int(_as_int(snapshot.get('verify_total_ms')) if isinstance(snapshot, dict) else None)}")
    lines.append("")
    lines.append("## Slowest steps")
    lines.append("| step | ms | ok |")
    lines.append("| --- | ---: | :---: |")
    if rows:
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            ms = _as_int(row.get("ms"))
            ok = _as_bool(row.get("ok"))
            lines.append(f"| {name if isinstance(name, str) else '?'} | {_text_int(ms)} | {_text_bool(ok)} |")
    else:
        lines.append("| ? | ? | ? |")
    lines.append("")
    lines.append("## Runtime diagnostics")
    lines.append(
        "- Swallowed exceptions: "
        f"total={_text_int(_as_int(snapshot.get('swallowed_total')) if isinstance(snapshot, dict) else None)} "
        f"distinct={_text_int(_as_int(snapshot.get('swallowed_distinct')) if isinstance(snapshot, dict) else None)} "
        f"top sites: {_format_top_sites([row for row in sites if isinstance(row, dict)])}"
    )
    shadow_selected = snapshot.get("shadow_selected") if isinstance(snapshot, dict) else None
    shadow_reason = snapshot.get("shadow_reason") if isinstance(snapshot, dict) else None
    lines.append(
        "- Shadow backend: "
        f"selected={shadow_selected if isinstance(shadow_selected, str) else '?'} "
        f"reason={shadow_reason if isinstance(shadow_reason, str) else '?'}"
    )
    lines.append("")
    lines.append("## Files read")
    files_read = payload.get("files_read")
    if isinstance(files_read, list) and files_read:
        for name in sorted(str(item) for item in files_read):
            lines.append(f"- {name}")
    else:
        lines.append("- ?")
    return "\n".join(lines).rstrip() + "\n"


def _handle_release_notes(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_module()
    artifacts_dir = _resolve_artifacts_dir(repo_root, str(getattr(args, "artifacts", "artifacts") or "artifacts"))
    if not artifacts_dir.exists() or not artifacts_dir.is_dir():
        print(f"error: artifacts directory not found: {artifacts_dir.as_posix()}", file=sys.stderr)
        return 2

    title = str(getattr(args, "title", "") or "").strip() or None
    max_sites = int(getattr(args, "max_sites", 5) or 5)
    max_steps = int(getattr(args, "max_steps", 5) or 5)

    text = build_release_notes(
        artifacts_dir,
        title=title,
        max_sites=max_sites,
        max_steps=max_steps,
    )
    raw_out = str(getattr(args, "out", "") or "").strip()
    if raw_out:
        out_path = Path(raw_out)
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8", newline="\n")
        return 0
    sys.stdout.write(text)
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "release-notes",
        help="Generate deterministic release notes from verify artifacts",
    )
    parser.add_argument(
        "--artifacts",
        default="artifacts",
        help="Artifact directory containing verify outputs (default: artifacts)",
    )
    parser.add_argument("--out", default="", help="Optional markdown output path")
    parser.add_argument("--title", default="", help="Optional title override")
    parser.add_argument("--max-sites", type=int, default=5, help="Maximum swallowed exception sites to show")
    parser.add_argument("--max-steps", type=int, default=5, help="Maximum slow steps to show")
    parser.set_defaults(func=_handle_release_notes)


def handle(args: argparse.Namespace) -> int:
    return _handle_release_notes(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mesh release-notes")
    parser.add_argument("--artifacts", default="artifacts")
    parser.add_argument("--out", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--max-sites", type=int, default=5)
    parser.add_argument("--max-steps", type=int, default=5)
    args = parser.parse_args(argv)
    return _handle_release_notes(args)
