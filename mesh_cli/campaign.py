"""Campaign replay-check CLI commands for Mesh CLI."""

from __future__ import annotations

import argparse
from pathlib import Path


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register campaign commands."""
    campaign_parser = subparsers.add_parser(
        "campaign",
        help="Campaign tooling",
        description="Campaign replay-check and determinism verification",
    )
    campaign_subparsers = campaign_parser.add_subparsers(
        dest="campaign_command", help="Campaign subcommand",
    )

    replay_parser = campaign_subparsers.add_parser(
        "replay-check",
        help="Run deterministic campaign replay check",
        description=(
            "Execute two scripted headless playthroughs, record digest traces "
            "and checkpoint snapshots, then diff the runs.  Exit 0 if identical."
        ),
    )
    replay_parser.add_argument(
        "--campaign",
        default="mini_campaign_01",
        help="Campaign id (selects script from tests/fixtures/campaign_scripts/)",
    )
    replay_parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory for output artifacts (default: artifacts/campaign_replay/<campaign>)",
    )
    replay_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit diff output as JSON instead of text",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle campaign commands."""
    sub = getattr(args, "campaign_command", None)
    if sub == "replay-check":
        return _handle_replay_check(args)
    print("[Mesh][CLI] Error: missing campaign subcommand")
    return 2


def _handle_replay_check(args: argparse.Namespace) -> int:
    """Run the campaign replay-check pipeline."""

    from engine.persistence_io import dumps_json_deterministic, write_json_atomic

    try:
        from engine.repo_root import get_repo_root
        repo_root = get_repo_root()
    except (OSError, ValueError):
        repo_root = Path.cwd()

    campaign_id: str = getattr(args, "campaign", "mini_campaign_01")
    out_dir_raw = getattr(args, "out_dir", None)
    emit_json: bool = bool(getattr(args, "json", False))

    if out_dir_raw:
        out_dir = Path(out_dir_raw)
        if not out_dir.is_absolute():
            out_dir = repo_root / out_dir
    else:
        out_dir = repo_root / "artifacts" / "campaign_replay" / campaign_id

    out_dir.mkdir(parents=True, exist_ok=True)

    # Late import to keep CLI parsing fast
    from tooling.campaign_replay import (
        diff_traces,
        format_diff_text,
        load_campaign_script,
        run_campaign_replay,
    )

    # Load script
    try:
        script = load_campaign_script(campaign_id)
    except FileNotFoundError as exc:
        print(f"[Mesh][Campaign] {exc}")
        return 2

    print(f"[Mesh][Campaign] replay-check '{campaign_id}'")

    # Run 1
    print("[Mesh][Campaign] Run 1 ...")
    result_1 = run_campaign_replay(script)
    trace_1 = result_1.to_trace_dict()

    # Run 2
    print("[Mesh][Campaign] Run 2 ...")
    result_2 = run_campaign_replay(script)
    trace_2 = result_2.to_trace_dict()

    # Write digest traces
    write_json_atomic(
        out_dir / "run_1_digest_trace.json", trace_1,
        sort_keys=True, trailing_newline=True,
    )
    write_json_atomic(
        out_dir / "run_2_digest_trace.json", trace_2,
        sort_keys=True, trailing_newline=True,
    )

    # Write checkpoint bundles
    for label, cp in result_1.checkpoints.items():
        write_json_atomic(
            out_dir / f"debug_bundle_checkpoint_{label}.json", cp,
            sort_keys=True, trailing_newline=True,
        )

    # Diff
    diff = diff_traces(trace_1, trace_2)

    if emit_json:
        diff_text = dumps_json_deterministic(diff, sort_keys=True, trailing_newline=True)
        write_json_atomic(
            out_dir / "digest_diff.json", diff,
            sort_keys=True, trailing_newline=True,
        )
        print(diff_text, end="")
    else:
        txt = format_diff_text(diff)
        (out_dir / "digest_diff.txt").write_text(txt, encoding="utf-8")
        print(txt, end="")

    if diff["identical"]:
        print(f"[Mesh][Campaign] OK — deterministic ({diff['total_ticks']} ticks)")
        return 0
    else:
        print(
            f"[Mesh][Campaign] FAIL — divergence at tick {diff['first_divergence_tick']}"
        )
        return 1
