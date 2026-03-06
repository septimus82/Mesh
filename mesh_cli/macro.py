from __future__ import annotations

import argparse
import json
from typing import Any
from engine.logging_tools import get_logger

_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)



def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    macro_parser = subparsers.add_parser("macro", help="Macro asset discovery and validation")
    macro_subparsers = macro_parser.add_subparsers(dest="macro_command", help="Macro subcommand")
    macro_list = macro_subparsers.add_parser("list", help="List available macro assets under packs/*/macros")
    macro_list.add_argument("--pack", dest="pack", help="Optional pack id filter")
    macro_list.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    macro_validate = macro_subparsers.add_parser("validate-all", help="Validate all macro assets (quality gate)")
    macro_validate.add_argument("--pack", dest="pack", help="Optional pack id filter")
    macro_preview = macro_subparsers.add_parser("preview", help="Preview a macro asset JSON")
    macro_preview.add_argument("macro_path", help="Path to macro asset JSON")
    macro_preview.add_argument("--format", choices=["text", "json"], default="text", help="Output format")


def handle(args: argparse.Namespace) -> int:
    from engine.paths import resolve_path
    from engine.tooling_runtime.macro_assets import (
        MacroAssetIssue,
        iter_macro_paths,
        load_macro_asset,
        parse_macro_asset,
        summarize_macro_asset,
        validate_macro_asset,
    )

    macro_cmd = getattr(args, "macro_command", None)
    pack = getattr(args, "pack", None)
    format_value = str(getattr(args, "format", "text") or "text").strip().lower()

    if macro_cmd == "list":
        macro_summaries = []
        for rel_path in iter_macro_paths(pack_id=pack):
            try:
                payload = load_macro_asset(rel_path)
            except Exception:
                _log_swallow("MCRO-001", "mesh_cli/macro.py blanket swallow", once=True)
                continue
            macro_summary = summarize_macro_asset(payload, rel_path=rel_path)
            if not macro_summary.id or not macro_summary.macro_id:
                continue
            macro_summaries.append(macro_summary)
        macro_summaries.sort(key=lambda s: (s.pack_id, s.id, s.path))

        if format_value == "json":
            payload = {
                "ok": True,
                "count": len(macro_summaries),
                "macros": [
                    {
                        "pack_id": s.pack_id,
                        "id": s.id,
                        "macro_id": s.macro_id,
                        "step_count": int(s.step_count),
                        "path": s.path,
                    }
                    for s in macro_summaries
                ],
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        for macro_s in macro_summaries:
            print(
                f"{macro_s.pack_id} {macro_s.id} macro_id={macro_s.macro_id} "
                f"steps={int(macro_s.step_count)} path={macro_s.path}"
            )
        return 0

    if macro_cmd == "validate-all":
        macro_issues: list[MacroAssetIssue] = []
        seen: dict[tuple[str, str], list[str]] = {}
        for rel_path in iter_macro_paths(pack_id=pack):
            full_path = resolve_path(rel_path)
            try:
                payload = json.loads(full_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                _log_swallow("MCRO-002", "mesh_cli/macro.py blanket swallow", once=True)
                macro_issues.append(MacroAssetIssue(path=rel_path, code="macro_asset.parse_error", detail=str(exc)))
                continue
            macro_issues.extend(validate_macro_asset(payload, rel_path=rel_path))
            if isinstance(payload, dict):
                try:
                    asset = parse_macro_asset(payload, rel_path=rel_path)
                except Exception:
                    _log_swallow("MCRO-003", "mesh_cli/macro.py blanket swallow", once=True)
                    asset = None
                if asset is not None and asset.id:
                    seen.setdefault((asset.pack_id, asset.id), []).append(rel_path)

        for (pack_id2, asset_id2), paths in sorted(seen.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            if len(paths) > 1:
                paths_sorted = sorted(str(p).replace("\\", "/") for p in paths)
                macro_issues.append(
                    MacroAssetIssue(
                        path=paths_sorted[0],
                        code="macro_asset.duplicate_id",
                        detail=f"duplicate id {asset_id2!r} in pack {pack_id2!r}: {paths_sorted!r}",
                    )
                )

        macro_issues.sort(key=lambda issue: (issue.path, issue.code, issue.detail))
        if macro_issues:
            for macro_issue in macro_issues:
                print(f"[Mesh][Macro] ERROR: {macro_issue.path} :: {macro_issue.code} :: {macro_issue.detail}")
            return 1
        return 0

    if macro_cmd == "preview":
        macro_path_raw = str(getattr(args, "macro_path", "") or "").strip()
        if not macro_path_raw:
            print("[Mesh][Macro] ERROR: missing macro_path")
            return 1
        macro_path = resolve_path(macro_path_raw)
        if not macro_path.exists():
            print(f"[Mesh][Macro] ERROR: {macro_path_raw} :: macro_asset.missing :: macro not found")
            return 1
        try:
            payload = load_macro_asset(str(macro_path))
        except Exception as exc:  # noqa: BLE001
            _log_swallow("MCRO-004", "mesh_cli/macro.py blanket swallow", once=True)
            print(f"[Mesh][Macro] ERROR: {macro_path_raw} :: macro_asset.parse_error :: {exc}")
            return 1

        rel = macro_path_raw.replace("\\", "/")
        issues = validate_macro_asset(payload, rel_path=rel)
        if issues:
            first = issues[0]
            print(f"[Mesh][Macro] ERROR: {first.path} :: {first.code} :: {first.detail}")
            return 1

        asset = parse_macro_asset(payload, rel_path=rel)
        entity_change_count: int = 0
        config_change_count: int = 0
        try:
            world_data = json.loads(resolve_path("worlds/main_world.json").read_text(encoding="utf-8"))
        except Exception:
            _log_swallow("MCRO-005", "mesh_cli/macro.py blanket swallow", once=True)
            world_data = {}
        if isinstance(world_data, dict):
            cases = world_data.get("macro_audit_cases")
            if isinstance(cases, list):
                wanted = asset.path
                match = next(
                    (
                        c
                        for c in cases
                        if isinstance(c, dict)
                        and str(c.get("macro_path") or "").replace("\\", "/") == wanted
                    ),
                    None,
                )
                if isinstance(match, dict):
                    scene_path = str(match.get("scene_path") or "").strip()
                    args_value = match.get("args")
                    args_payload: dict[str, Any] = (
                        {str(k): v for k, v in args_value.items()} if isinstance(args_value, dict) else {}
                    )
                    if scene_path:
                        try:
                            from engine.tooling_runtime.macro_apply_report import compute_scene_macro_report

                            scene_payload = json.loads(resolve_path(scene_path).read_text(encoding="utf-8"))
                            merged = dict(asset.defaults or {})
                            merged.update(args_payload)
                            raw_args = [
                                f"{k}={json.dumps(v, sort_keys=True) if not isinstance(v, str) else v}"
                                for k, v in merged.items()
                            ]
                            report = compute_scene_macro_report(
                                scene_payload=scene_payload if isinstance(scene_payload, dict) else {},
                                scene_path=scene_path,
                                macro_path=asset.path,
                                raw_args=raw_args,
                                anchor_override=None,
                            ).report
                            entity_change_count = int(len(report.get("entity_changes") or []))
                            config_change_count = int(len(report.get("config_changes") or []))
                        except Exception:
                            _log_swallow("MCRO-006", "mesh_cli/macro.py blanket swallow", once=True)
                            entity_change_count = 0
                            config_change_count = 0

        if format_value == "json":
            out = {
                "ok": True,
                "pack_id": asset.pack_id,
                "id": asset.id,
                "macro_id": asset.macro_id,
                "defaults": asset.defaults,
                "steps": asset.steps,
                "metadata": asset.metadata,
                "path": asset.path,
                "entity_change_count": int(entity_change_count),
                "config_change_count": int(config_change_count),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
            return 0

        print(f"{asset.pack_id} {asset.id} macro_id={asset.macro_id} path={asset.path}")
        print(f"preview entity_changes={int(entity_change_count)} config_changes={int(config_change_count)}")
        if asset.defaults:
            print("defaults=" + json.dumps(asset.defaults, sort_keys=True))
        if asset.steps:
            print("steps=" + json.dumps(asset.steps, sort_keys=True))
        return 0

    print("[Mesh][Macro] ERROR: missing macro subcommand")
    return 2
