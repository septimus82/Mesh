"""CLI tools for managing prefabs."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List

from engine.paths import resolve_path
from engine.prefabs import get_prefab_manager
from engine.validators.prefab_validator import PrefabValidator
from engine.validators.variant_validator import VariantValidator


def handle_list(args: argparse.Namespace) -> int:
    """List all available prefabs."""
    manager = get_prefab_manager()
    manager.load()

    print(f"Found {len(manager.prefabs)} prefabs:")
    for pid in sorted(manager.prefabs.keys()):
        prefab = manager.prefabs[pid]
        base = prefab.get("base", "")
        base_str = f" (extends {base})" if base else ""
        print(f"  - {pid}{base_str}")
    return 0


def handle_show(args: argparse.Namespace) -> int:
    """Show resolved details of a prefab."""
    manager = get_prefab_manager()
    manager.load()

    pid = args.id
    if pid not in manager.prefabs:
        print(f"Error: Prefab '{pid}' not found.")
        return 1

    resolved = manager.get_prefab(pid)
    print(json.dumps(resolved, indent=2))
    return 0


def handle_validate(args: argparse.Namespace) -> int:
    """Run prefab validation."""
    p_validator = PrefabValidator()
    v_validator = VariantValidator()

    ok_p = p_validator.validate()
    p_validator.print_report()

    ok_v = v_validator.validate()
    # VariantValidator doesn't have print_report, it prints as it goes or stores in errors
    if v_validator.errors:
        for e in v_validator.errors:
            print(f"[ERR] {e}")
    if v_validator.warnings:
        for w in v_validator.warnings:
            print(f"[WARN] {w}")

    if ok_p and ok_v:
        print("All prefab checks passed.")
        return 0
    else:
        print("Prefab checks failed.")
        return 1


def handle_sources(_args: argparse.Namespace) -> int:
    """List prefab source files in merge order."""
    manager = get_prefab_manager()
    sources = manager.get_prefab_sources()
    if getattr(_args, "json", False):
        payload: dict[str, Any] = {
            "cmd": "prefab_sources",
            "sources": [str(path) for path in sources],
            "ok": True,
        }
        print(json.dumps(payload, separators=(",", ":")))
        return 0
    for path in sources:
        print(str(path))
    return 0


def handle_validate_all(_args: argparse.Namespace) -> int:
    """Validate prefabs for base and pack-local sources."""
    json_enabled = bool(getattr(_args, "json", False))
    manager = get_prefab_manager()
    sources = manager.get_prefab_sources()

    ok_all = True
    results: list[dict[str, object]] = []
    for path in sources:
        validator = PrefabValidator()
        if json_enabled:
            import contextlib
            import io

            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                ok = validator.validate_path(path)
        else:
            ok = validator.validate_path(path)
        if json_enabled:
            entry: dict[str, object] = {"file": str(path), "ok": bool(ok)}
            if not ok:
                error = ""
                if validator.errors:
                    error = str(validator.errors[0])
                elif validator.warnings:
                    error = str(validator.warnings[0])
                else:
                    error = "unknown error"
                entry["error"] = error
            results.append(entry)
        elif ok:
            print(f"[Mesh][Validator] OK: {path}")
        else:
            ok_all = False
            print(f"[Mesh][Validator] FAILED: {path}")
            validator.print_report()
        ok_all = ok_all and bool(ok)
    if json_enabled:
        payload: dict[str, Any] = {
            "cmd": "prefab_validate_all",
            "ok": bool(ok_all),
            "results": results,
        }
        print(json.dumps(payload, separators=(",", ":")))
        return 0 if ok_all else 1
    if ok_all:
        print("All prefab checks passed.")
        return 0
    print("Prefab checks failed.")
    return 1


def handle_explain(args: argparse.Namespace) -> int:
    """Explain prefab source and resolved payload."""
    manager = get_prefab_manager()
    manager.load(force=True)
    prefab_id = str(args.id)
    if prefab_id not in manager.prefabs:
        if getattr(args, "json", False):
            payload: dict[str, Any] = {
                "prefab_id": prefab_id,
                "source": None,
                "chain": [],
                "prefab": None,
                "ok": False,
            }
            print(json.dumps(payload, separators=(",", ":")))
        else:
            print(f"Prefab '{prefab_id}' not found.")
        return 2

    prefab_source_raw = manager.prefab_sources.get(prefab_id, "")
    source: str | None
    if isinstance(prefab_source_raw, str) and prefab_source_raw.strip():
        source = prefab_source_raw
    else:
        source = None
    chain_raw = manager.prefab_source_chain.get(prefab_id, [])
    chain = [entry for entry in chain_raw if isinstance(entry, str) and entry.strip()]
    resolved = manager.get_prefab(prefab_id)
    if getattr(args, "json", False):
        response_payload: dict[str, Any] = {
            "prefab_id": prefab_id,
            "source": source,
            "chain": chain,
            "prefab": resolved or {},
            "ok": True,
        }
        print(json.dumps(response_payload, separators=(",", ":")))
        return 0
    print(f"prefab_id: {prefab_id}")
    print(f"source: {source or ''}")
    print(json.dumps(resolved or {}, indent=2))
    return 0


def _resolve_allow_path(raw_path: str | None) -> Path:
    if raw_path:
        return resolve_path(str(raw_path))
    return resolve_path(".mesh/prefab_overrides_allow.json")


def _load_allow_entries(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    if not path.exists():
        return [], None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], f"allow.parse_error: {exc}"
    if not isinstance(payload, dict):
        return [], "allow.invalid: root must be object"
    raw = payload.get("allow")
    if raw is None:
        return [], None
    if not isinstance(raw, list):
        return [], "allow.invalid: allow must be list"
    entries: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, dict):
            entries.append(entry)
    return entries, None


def _collect_override_records() -> list[dict[str, Any]]:
    manager = get_prefab_manager()
    manager.load(force=True)
    overrides: list[dict[str, Any]] = []
    for prefab_id in sorted(manager.prefab_source_chain.keys()):
        chain_raw = manager.prefab_source_chain.get(prefab_id, [])
        chain = [str(entry) for entry in chain_raw if isinstance(entry, str) and entry.strip()]
        if len(chain) < 2:
            continue
        winner = manager.prefab_sources.get(prefab_id, "")
        if not isinstance(winner, str):
            winner = str(winner or "")
        overrides.append(
            {
                "prefab_id": str(prefab_id),
                "chain": chain,
                "winner": winner,
            }
        )
    return overrides


def _allow_override(record: dict[str, Any], allow_entries: list[dict[str, Any]]) -> bool:
    prefab_id = record.get("prefab_id")
    winner = record.get("winner")
    if not isinstance(prefab_id, str):
        return False
    for entry in allow_entries:
        if entry.get("prefab_id") != prefab_id:
            continue
        allow_winner = entry.get("winner")
        if allow_winner is None:
            return True
        if isinstance(allow_winner, str) and isinstance(winner, str) and allow_winner == winner:
            return True
    return False


def compute_lint_overrides(allow_path_raw: str | None = None) -> tuple[dict[str, Any], bool]:
    allow_path = _resolve_allow_path(allow_path_raw)
    allow_entries, allow_error = _load_allow_entries(allow_path)
    overrides = _collect_override_records()

    allowed: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []
    for record in overrides:
        if _allow_override(record, allow_entries):
            allowed.append(record)
        else:
            unexpected.append(record)

    ok = not unexpected and allow_error is None
    payload: dict[str, Any] = {
        "cmd": "prefab_lint_overrides",
        "ok": bool(ok),
        "unexpected": unexpected,
        "allowed": allowed,
        "allow_path": str(allow_path.as_posix()),
        "count": {
            "overrides": int(len(overrides)),
            "unexpected": int(len(unexpected)),
            "allowed": int(len(allowed)),
        },
    }
    if allow_error:
        payload["error"] = allow_error
    return payload, ok


def handle_lint_overrides(args: argparse.Namespace) -> int:
    json_enabled = bool(getattr(args, "json", False))
    allow_path_raw = getattr(args, "allow", None)
    from engine.logging_tools import suppress_stdout

    with suppress_stdout():
        payload, ok = compute_lint_overrides(allow_path_raw)
    if json_enabled:
        print(json.dumps(payload, separators=(",", ":")))
    else:
        unexpected = payload.get("unexpected") or []
        for record in unexpected if isinstance(unexpected, list) else []:
            if not isinstance(record, dict):
                continue
            prefab_id = record.get("prefab_id", "")
            winner = record.get("winner", "")
            chain = record.get("chain", [])
            chain_str = " -> ".join([str(entry) for entry in chain if entry])
            print(f"[Prefab] override id={prefab_id} winner={winner} chain={chain_str}")
        allowed = payload.get("allowed") or []
        for record in allowed if isinstance(allowed, list) else []:
            if not isinstance(record, dict):
                continue
            prefab_id = record.get("prefab_id", "")
            winner = record.get("winner", "")
            chain = record.get("chain", [])
            chain_str = " -> ".join([str(entry) for entry in chain if entry])
            print(f"[Prefab] override allowed id={prefab_id} winner={winner} chain={chain_str}")
        if payload.get("error"):
            print(f"[Prefab] override allow error: {payload['error']}")
    return 0 if ok else 2


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Prefab management tools")
    subparsers = parser.add_subparsers(dest="command", help="Sub-command to run")

    subparsers.add_parser("list", help="List all prefabs")

    show_parser = subparsers.add_parser("show", help="Show resolved prefab")
    show_parser.add_argument("id", help="Prefab ID")

    subparsers.add_parser("validate", help="Validate prefabs and variants")
    validate_all_parser = subparsers.add_parser("validate-all", help="Validate base + pack prefab sources")
    validate_all_parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    sources_parser = subparsers.add_parser("sources", help="List prefab sources in merge order")
    sources_parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    explain_parser = subparsers.add_parser("explain", help="Explain prefab source and resolved data")
    explain_parser.add_argument("id", help="Prefab ID")
    explain_parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    lint_parser = subparsers.add_parser("lint-overrides", help="Lint unexpected prefab overrides")
    lint_parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    lint_parser.add_argument("--strict", action="store_true", help="Fail on unexpected overrides")
    lint_parser.add_argument("--allow", help="Allowlist JSON path (default .mesh/prefab_overrides_allow.json)")

    args = parser.parse_args(argv)

    if args.command == "list":
        return handle_list(args)
    elif args.command == "show":
        return handle_show(args)
    elif args.command == "validate":
        return handle_validate(args)
    elif args.command == "validate-all":
        return handle_validate_all(args)
    elif args.command == "sources":
        return handle_sources(args)
    elif args.command == "explain":
        return handle_explain(args)
    elif args.command == "lint-overrides":
        return handle_lint_overrides(args)
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
