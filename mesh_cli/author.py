"""``mesh author``: change a Mesh project from the command line, through the same operations as
Mesh Studio and the MCP tools (engine.authoring_session). Any tool or AI that can run a command
can use it; output is JSON.

  mesh author ops                          what can be changed (generated from the engine)
  mesh author read    [--project DIR]      every room (live from Mesh Studio if it has it open)
  mesh author apply   CHANGES [--project DIR] [--dry-run]
  mesh author propose CHANGES [--project DIR] [--title T] [--base-revision N]
  mesh author status  PROPOSAL_ID [--project DIR]

CHANGES is a JSON file (or ``-`` for stdin) holding a list of changes or ``{"changes": [...]}``.
``apply`` writes the files unless Mesh Studio has the project open, in which case the changes go
to Studio as a proposal for the person to review.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("author", help="Change a project through Mesh's authoring operations (JSON in, JSON out)")
    sub = parser.add_subparsers(dest="author_command", help="author subcommand")
    sub.add_parser("ops", help="List every operation and its settings")
    read = sub.add_parser("read", help="Print every room of the project")
    apply = sub.add_parser("apply", help="Apply changes (or propose them, if Mesh Studio has the project open)")
    apply.add_argument("changes", help="JSON file of changes, or - for stdin")
    apply.add_argument("--dry-run", action="store_true", help="Only say what would change")
    propose = sub.add_parser("propose", help="Propose changes to the Mesh Studio that has the project open")
    propose.add_argument("changes", help="JSON file of changes, or - for stdin")
    propose.add_argument("--title", default="", help="A short title for the person reviewing it")
    propose.add_argument("--base-revision", type=int, default=None, help="The revision your changes are based on (from read)")
    status = sub.add_parser("status", help="What happened to a proposal")
    status.add_argument("proposal_id")
    for p in (read, apply, propose, status):
        p.add_argument("--project", default=".", help="The project folder (default: here)")


def _changes(source: str) -> Any:
    text = sys.stdin.read() if source == "-" else open(source, encoding="utf-8").read()  # noqa: SIM115
    data = json.loads(text)
    return data.get("changes") if isinstance(data, dict) else data


def handle(args: argparse.Namespace) -> int:
    from engine import authoring_session  # noqa: PLC0415

    command = getattr(args, "author_command", None)
    try:
        if command == "ops":
            result = authoring_session.operations()
        elif command == "read":
            result = authoring_session.read_project(args.project)
        elif command == "apply":
            result = authoring_session.apply(args.project, _changes(args.changes), dry_run=args.dry_run, source="mesh author")
        elif command == "propose":
            result = authoring_session.propose(args.project, _changes(args.changes), title=args.title,
                                               base_revision=args.base_revision, source="mesh author")
        elif command == "status":
            result = authoring_session.proposal_status(args.project, args.proposal_id)
        else:
            print("usage: mesh author {ops,read,apply,propose,status} ...", file=sys.stderr)
            return 2
    except (OSError, ValueError) as exc:
        result = {"ok": False, "reason": "bad_input", "message": str(exc)}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1
