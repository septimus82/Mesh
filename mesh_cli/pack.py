from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from engine.persistence_io import write_json_atomic
from engine.tooling_runtime.pack_manifest import load_all_manifests, resolve_pack_order
from engine.tooling_runtime.pack_registry import build_asset_registry


@dataclass(frozen=True)
class PackValidationResult:
    ok: bool
    errors: int
    messages: list[str]
    presets_validated: int | None = None
    fx_errors: int | None = None


def run_pack_validate(*, with_fx: bool, emit: bool = True) -> PackValidationResult:
    manifests, errors = load_all_manifests()
    order, dep_errors = resolve_pack_order(manifests)
    all_errors = sorted(errors + dep_errors)
    messages: list[str] = []
    if all_errors:
        for err in all_errors:
            messages.append(f"[Mesh][Pack] ERROR: {err}")
        result = PackValidationResult(
            ok=False,
            errors=len(all_errors),
            messages=messages,
        )
        if emit:
            for line in messages:
                print(line)
        return result

    messages.append("[Mesh][Pack] OK")
    presets_validated = None
    fx_errors = None
    if with_fx:
        from . import fx as fx_commands

        pack_roots = [manifest.root for manifest in order]
        fx_result = fx_commands.run_fx_validation_result(pack_roots, order)
        presets_validated = fx_result.presets_validated
        fx_errors = fx_result.errors
        messages.extend(fx_result.messages)
        result = PackValidationResult(
            ok=fx_result.ok,
            errors=fx_result.errors,
            messages=messages,
            presets_validated=presets_validated,
            fx_errors=fx_errors,
        )
        if emit:
            for line in messages:
                print(line)
        return result

    result = PackValidationResult(
        ok=True,
        errors=0,
        messages=messages,
    )
    if emit:
        for line in messages:
            print(line)
    return result

def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    pack_parser = subparsers.add_parser("pack", help="Pack manifest tooling")
    pack_subs = pack_parser.add_subparsers(dest="pack_command", required=True)

    pack_list = pack_subs.add_parser("list", help="List pack manifests")
    pack_list.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    pack_validate = pack_subs.add_parser("validate", help="Validate pack manifests and dependencies")
    pack_validate.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    pack_validate.add_argument("--with-fx", action="store_true", help="Also validate FX presets")

    pack_registry = pack_subs.add_parser("build-registry", help="Build asset registry JSON")
    pack_registry.add_argument("--out", required=True, help="Output JSON path")
    pack_registry.add_argument("--include-unused", action="store_true", help="Include unused assets")

    pack_graph = pack_subs.add_parser("graph", help="Print pack dependency order")
    pack_graph.add_argument("--format", choices=["text", "json"], default="text", help="Output format")


def handle(args: argparse.Namespace) -> int:
    cmd = getattr(args, "pack_command", None)
    fmt = str(getattr(args, "format", "text") or "text").strip().lower()

    if cmd == "list":
        manifests, errors = load_all_manifests()
        if errors:
            for err in errors:
                print(f"[Mesh][Pack] ERROR: {err}")
            return 1
        if fmt == "json":
            payload = {
                "ok": True,
                "count": len(manifests),
                "packs": [
                    {
                        "id": m.id,
                        "version": m.version,
                        "path": m.path,
                        "implicit": bool(m.implicit),
                    }
                    for m in manifests
                ],
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        for manifest in manifests:
            implicit = " implicit" if manifest.implicit else ""
            print(f"{manifest.id} {manifest.version} path={manifest.path}{implicit}")
        return 0

    if cmd == "validate":
        manifests, errors = load_all_manifests()
        order, dep_errors = resolve_pack_order(manifests)
        all_errors = sorted(errors + dep_errors)
        if fmt == "json":
            payload = {
                "ok": not all_errors,
                "count": {"packs": len(manifests), "errors": len(all_errors)},
                "errors": all_errors,
                "order": [m.id for m in order],
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            if all_errors:
                for err in all_errors:
                    print(f"[Mesh][Pack] ERROR: {err}")
            else:
                print("[Mesh][Pack] OK")
        if all_errors:
            return 2
        if bool(getattr(args, "with_fx", False)):
            from . import fx as fx_commands

            pack_roots = [manifest.root for manifest in order]
            rc, lines = fx_commands.run_fx_validation(pack_roots, order)
            for line in lines:
                print(line)
            return rc
        return 0

    if cmd == "build-registry":
        out_path = str(getattr(args, "out", "") or "").strip()
        if not out_path:
            print("[Mesh][Pack] ERROR: missing --out")
            return 2
        manifests, errors = load_all_manifests()
        order, dep_errors = resolve_pack_order(manifests)
        all_errors = sorted(errors + dep_errors)
        if all_errors:
            for err in all_errors:
                print(f"[Mesh][Pack] ERROR: {err}")
            return 2
        registry = build_asset_registry(order, include_unused=bool(getattr(args, "include_unused", False)))
        out_path_obj = Path(out_path)
        write_json_atomic(out_path_obj, registry, indent=2, sort_keys=True, trailing_newline=True)
        print(f"[Mesh][Pack] Wrote asset registry: {out_path}")
        return 0

    if cmd == "graph":
        manifests, errors = load_all_manifests()
        order, dep_errors = resolve_pack_order(manifests)
        all_errors = sorted(errors + dep_errors)
        if all_errors:
            for err in all_errors:
                print(f"[Mesh][Pack] ERROR: {err}")
            return 2
        if fmt == "json":
            payload = {
                "ok": True,
                "order": [m.id for m in order],
                "dependencies": {
                    m.id: [dep.id for dep in m.dependencies]
                    for m in order
                    if m.dependencies
                },
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        print("load_order=" + " -> ".join(m.id for m in order))
        for manifest in order:
            if manifest.dependencies:
                deps = ", ".join(dep.id for dep in manifest.dependencies)
                print(f"{manifest.id}: requires {deps}")
        return 0

    print("[Mesh][Pack] ERROR: missing pack subcommand")
    return 2
