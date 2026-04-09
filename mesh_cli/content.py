from __future__ import annotations

import argparse
from pathlib import Path

from engine.persistence_io import write_json_atomic, write_text_atomic

from .content_scaffold import apply_episode_scaffold, build_episode_scaffold_plan
from .content_integrity import (
    content_audit_report_to_json,
    format_content_audit_text,
    run_content_audit,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    content_parser = subparsers.add_parser(
        "content",
        help="Content scaffolding commands",
        description="Create deterministic content scaffolds",
    )
    content_subparsers = content_parser.add_subparsers(dest="content_command", help="Content subcommand")

    audit_parser = content_subparsers.add_parser(
        "audit",
        help="Run deterministic content integrity audit",
        description="Validate content registries and cross-file references deterministically",
    )
    audit_parser.add_argument("--out-dir", required=True, help="Directory to write content audit reports")
    audit_parser.add_argument("--json", action="store_true", dest="audit_json", help="Print JSON report to stdout")
    audit_parser.add_argument("--quiet", action="store_true", help="Suppress stdout summary")

    episode_parser = content_subparsers.add_parser(
        "episode",
        help="Episode content commands",
        description="Scaffold deterministic episode content files",
    )
    episode_subparsers = episode_parser.add_subparsers(dest="content_episode_command", help="Episode subcommand")

    new_parser = episode_subparsers.add_parser(
        "new",
        help="Generate a new episode scaffold",
        description="Generate scene, docs, tests, and registry stubs for a new episode",
    )
    new_parser.add_argument("--id", dest="episode_id", required=True, help="Episode identifier (for example: ep02)")
    new_parser.add_argument("--title", required=True, help="Episode display title")
    new_parser.add_argument("--out-dir", required=True, help="Repository root to patch")
    new_parser.add_argument("--seed", type=int, default=123, help="Deterministic seed metadata (default: 123)")
    new_parser.add_argument("--dry-run", action="store_true", help="Validate and print planned edits without writing")


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "content_command", None)
    if command == "audit":
        return _handle_content_audit(args)
    if command != "episode":
        print("[Mesh][Content] Error: missing content subcommand")
        return 2
    episode_command = getattr(args, "content_episode_command", None)
    if episode_command != "new":
        print("[Mesh][Content] Error: missing episode subcommand")
        return 2
    return _handle_episode_new(args)


def _handle_episode_new(args: argparse.Namespace) -> int:
    try:
        plan = build_episode_scaffold_plan(
            episode_id=str(getattr(args, "episode_id", "") or ""),
            title=str(getattr(args, "title", "") or ""),
            out_dir=Path(str(getattr(args, "out_dir", "") or "")),
            seed=int(getattr(args, "seed", 123)),
        )
        actions = apply_episode_scaffold(plan, dry_run=bool(getattr(args, "dry_run", False)))
    except ValueError as exc:
        print(f"[Mesh][Content] ERROR: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001  # REASON: content scaffold CLI should collapse unexpected scaffold failures into a deterministic nonzero exit with context
        print(f"[Mesh][Content] ERROR: {type(exc).__name__}: {exc}")
        return 1

    dry_run = bool(getattr(args, "dry_run", False))
    prefix = "[Mesh][Content][dry-run]" if dry_run else "[Mesh][Content]"
    for rel_path, summary in actions:
        print(f"{prefix} {rel_path}: {summary}")
    if not dry_run:
        print(f"[Mesh][Content] Episode scaffold created: {plan.scene_rel_path.as_posix()}")
    return 0


def _handle_content_audit(args: argparse.Namespace) -> int:
    from engine.repo_root import get_repo_root

    repo_root = get_repo_root(start=Path.cwd(), strict=False)
    out_dir = Path(str(getattr(args, "out_dir", "") or "").strip()).resolve()
    json_stdout = bool(getattr(args, "audit_json", False))
    quiet = bool(getattr(args, "quiet", False))

    out_dir.mkdir(parents=True, exist_ok=True)
    report = run_content_audit(repo_root)

    json_path = out_dir / "content_audit_report.json"
    txt_path = out_dir / "content_audit_report.txt"
    write_json_atomic(
        json_path,
        report.to_dict(),
        indent=2,
        sort_keys=True,
        trailing_newline=True,
        durable=True,
    )
    write_text_atomic(
        txt_path,
        format_content_audit_text(report),
        encoding="utf-8",
        durable=True,
    )

    if not quiet:
        if json_stdout:
            print(content_audit_report_to_json(report), end="")
        else:
            print(format_content_audit_text(report), end="")
            print(f"[Mesh][Content] Report JSON: {json_path.as_posix()}")
            print(f"[Mesh][Content] Report TXT: {txt_path.as_posix()}")
    return 0 if report.ok else 1
