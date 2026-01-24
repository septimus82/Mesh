import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict


def extract_parser_info(parser: argparse.ArgumentParser) -> Dict[str, Any]:
    """Extract structure from an ArgumentParser."""
    usage = parser.format_usage().strip()
    # Normalize usage string to avoid terminal width wrapping issues
    usage = re.sub(r'\n\s+', ' ', usage)

    arguments: list[dict[str, Any]] = []
    subcommands: dict[str, Any] = {}
    info: dict[str, Any] = {
        "description": parser.description,
        "usage": usage,
        "arguments": arguments,
        "subcommands": subcommands,
    }

    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue

        if isinstance(action, argparse._SubParsersAction):
            for name, subparser in action.choices.items():
                subcommands[name] = extract_parser_info(subparser)
            continue

        arg_info = {
            "option_strings": action.option_strings,
            "dest": action.dest,
            "help": action.help,
            "required": action.required,
            "default": str(action.default) if action.default is not argparse.SUPPRESS else None,
            "type": str(action.type) if action.type else None,
            "choices": list(action.choices) if action.choices else None,
            "nargs": str(action.nargs) if action.nargs else None
        }
        arguments.append(arg_info)

    # Sort arguments for deterministic output
    arguments.sort(key=lambda x: x["dest"])
    return info

def cli_snapshot_command(args: argparse.Namespace) -> None:
    """Generate a snapshot of the CLI structure."""
    # Import here to avoid circular dependency
    from mesh_cli import create_parser

    parser = create_parser()
    snapshot = extract_parser_info(parser)

    output_json = json.dumps(snapshot, indent=2, sort_keys=True)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if args.verify:
            if not out_path.exists():
                print(f"[Mesh][Snapshot] FAILURE: Snapshot file '{out_path}' does not exist.")
                sys.exit(1)

            existing = out_path.read_text(encoding="utf-8")
            # Normalize newlines
            existing = existing.replace("\r\n", "\n")
            output_json = output_json.replace("\r\n", "\n")

            if existing.strip() != output_json.strip():
                print("[Mesh][Snapshot] FAILURE: CLI snapshot mismatch.")
                import difflib
                diff = difflib.unified_diff(
                    existing.strip().splitlines(),
                    output_json.strip().splitlines(),
                    fromfile='existing',
                    tofile='new',
                    lineterm=''
                )
                for line in diff:
                    print(line)
                print(f"Run 'mesh cli-snapshot --out {args.out}' to update.")
                sys.exit(1)
            else:
                print("[Mesh][Snapshot] CLI snapshot verified.")
        else:
            out_path.write_text(output_json, encoding="utf-8")
            print(f"[Mesh][Snapshot] Wrote CLI snapshot to {out_path}")
    else:
        print(output_json)

def add_cli_snapshot_command(subparsers) -> None:
    parser = subparsers.add_parser("cli-snapshot", help="Generate CLI structure snapshot")
    parser.add_argument("--out", help="Output JSON file path")
    parser.add_argument("--verify", action="store_true", help="Verify against existing snapshot")
    parser.set_defaults(func=cli_snapshot_command)
