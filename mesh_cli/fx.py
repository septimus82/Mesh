from __future__ import annotations

import argparse
from dataclasses import dataclass

from engine.fx_presets import collect_presets_and_errors, validate_all_presets
from engine.tooling_runtime.pack_manifest import load_all_manifests, resolve_pack_order


@dataclass(frozen=True)
class FxValidationResult:
    ok: bool
    presets_validated: int
    errors: int
    messages: list[str]


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    fx_parser = subparsers.add_parser("fx", help="FX tooling")
    fx_subs = fx_parser.add_subparsers(dest="fx_command", required=True)
    fx_subs.add_parser("validate", help="Validate FX preset definitions")


def handle(args: argparse.Namespace) -> int:
    cmd = getattr(args, "fx_command", None)
    if cmd == "validate":
        return _handle_fx_validate()
    print("[Mesh][FX] ERROR: missing fx subcommand")
    return 2


def _handle_fx_validate() -> int:
    try:
        manifests, manifest_errors = load_all_manifests()
        order, dep_errors = resolve_pack_order(manifests)
        pack_roots = [manifest.root for manifest in order]
        result = run_fx_validation_result(
            pack_roots,
            order,
            manifest_errors=manifest_errors,
            dep_errors=dep_errors,
        )
        for line in result.messages:
            print(line)
        return 0 if result.ok else 2
    except Exception as exc:  # noqa: BLE001
        print(f"[Mesh][FX] ERROR: {exc}")
        return 1


def run_fx_validation(
    pack_roots: list,
    pack_order: list,
    *,
    manifest_errors: list[str] | None = None,
    dep_errors: list[str] | None = None,
) -> tuple[int, list[str]]:
    result = run_fx_validation_result(
        pack_roots,
        pack_order,
        manifest_errors=manifest_errors,
        dep_errors=dep_errors,
    )
    return (0 if result.ok else 2), list(result.messages)


def run_fx_validation_result(
    pack_roots: list,
    pack_order: list,
    *,
    manifest_errors: list[str] | None = None,
    dep_errors: list[str] | None = None,
) -> FxValidationResult:
    records, load_errors = collect_presets_and_errors(pack_roots, pack_order)
    validation_errors = validate_all_presets(records)

    messages: list[str] = []
    for err in sorted((manifest_errors or []) + (dep_errors or [])):
        messages.append(f"[Mesh][FX] ERROR pack manifests: {err}")

    for item in sorted(load_errors, key=_error_sort_key):
        messages.append(_format_error(item))

    for item in sorted(validation_errors, key=_error_sort_key):
        messages.append(_format_error(item))

    if messages:
        return FxValidationResult(
            ok=False,
            presets_validated=len(records),
            errors=len(messages),
            messages=messages,
        )

    return FxValidationResult(
        ok=True,
        presets_validated=len(records),
        errors=0,
        messages=[f"[Mesh][FX] OK ({len(records)} presets)"],
    )


def _format_error(item) -> str:
    key = f"{item.pack_id}:{item.preset_name}"
    path = item.file_path
    message = item.message
    return f"[Mesh][FX] ERROR {key} ({path}): {message}"


def _error_sort_key(item) -> tuple[str, str, str, str]:
    return (item.pack_id, item.preset_name, item.file_path, item.message)
