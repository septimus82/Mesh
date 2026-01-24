from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.macro_specs import get_builtin_macro_spec, list_builtin_macro_ids, normalize_macro_id
from engine.paths import get_content_roots, resolve_path


@dataclass(frozen=True, slots=True)
class MacroAsset:
    pack_id: str
    id: str
    macro_id: str
    defaults: dict[str, Any]
    steps: list[dict[str, Any]]
    path: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MacroAssetSummary:
    pack_id: str
    id: str
    macro_id: str
    step_count: int
    path: str


@dataclass(frozen=True, slots=True)
class MacroAssetIssue:
    path: str
    code: str
    detail: str


def _norm_rel_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def _extract_pack_id(rel_path: str) -> str:
    parts = [p for p in str(rel_path).split("/") if p]
    if len(parts) >= 3 and parts[0] == "packs" and parts[2] == "macros":
        return parts[1]
    if len(parts) >= 2 and parts[0] == "packs":
        return parts[1]
    return "unknown"


def iter_macro_paths(*, pack_id: str | None = None) -> list[str]:
    """Return relative macro asset paths under packs/*/macros/*.json (forward slashes)."""
    wanted_pack = str(pack_id).strip() if isinstance(pack_id, str) and str(pack_id).strip() else None
    results: set[str] = set()
    for root in get_content_roots():
        root_path = Path(root)
        packs_dir = root_path / "packs"
        if not packs_dir.exists():
            continue
        for macros_dir in packs_dir.glob("*/*"):
            if not macros_dir.is_dir() or macros_dir.name != "macros":
                continue
            pack = macros_dir.parent.name
            if wanted_pack is not None and pack != wanted_pack:
                continue
            for candidate in macros_dir.glob("*.json"):
                try:
                    rel = candidate.relative_to(root_path)
                except Exception:
                    rel = candidate
                results.add(_norm_rel_path(rel))
    return sorted(results)


def load_macro_asset(path: str) -> dict[str, Any]:
    resolved = resolve_path(str(path))
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("macro asset JSON root must be an object")
    return payload


def summarize_macro_asset(payload: dict[str, Any], *, rel_path: str) -> MacroAssetSummary:
    mid = normalize_macro_id(payload.get("macro_id"))
    asset_id = str(payload.get("id") or "").strip()
    rel = _norm_rel_path(Path(str(rel_path)))
    return MacroAssetSummary(
        pack_id=_extract_pack_id(rel),
        id=asset_id,
        macro_id=mid,
        step_count=len(payload.get("steps") or []) if isinstance(payload.get("steps"), list) else 0,
        path=rel,
    )


def validate_macro_asset(payload: Any, *, rel_path: str) -> list[MacroAssetIssue]:
    rel = _norm_rel_path(Path(str(rel_path)))
    issues: list[MacroAssetIssue] = []

    if not isinstance(payload, dict):
        return [MacroAssetIssue(rel, "macro_asset.root_type", "root must be an object")]

    asset_id = payload.get("id")
    if not isinstance(asset_id, str) or not asset_id.strip():
        issues.append(MacroAssetIssue(rel, "macro_asset.id.required", "id must be a non-empty string"))

    t = payload.get("type")
    if t is not None and t != "macro":
        issues.append(MacroAssetIssue(rel, "macro_asset.type.invalid", "type must be 'macro' when provided"))
    if t is None:
        issues.append(MacroAssetIssue(rel, "macro_asset.type.required", "type is required and must be 'macro'"))

    macro_id = normalize_macro_id(payload.get("macro_id"))
    if not macro_id:
        issues.append(MacroAssetIssue(rel, "macro_asset.macro_id.required", "macro_id must be a non-empty string"))
        spec = None
    else:
        spec = get_builtin_macro_spec(macro_id)
        if spec is None:
            allowed = ", ".join(list_builtin_macro_ids())
            issues.append(
                MacroAssetIssue(rel, "macro_asset.macro_id.unknown", f"unknown macro_id {macro_id!r} (known: {allowed})"),
            )

    defaults = payload.get("defaults", {})
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict):
        issues.append(MacroAssetIssue(rel, "macro_asset.defaults.type", "defaults must be an object when provided"))
        defaults = {}

    steps = payload.get("steps", [])
    if steps is None:
        steps = []
    if not isinstance(steps, list):
        issues.append(MacroAssetIssue(rel, "macro_asset.steps.type", "steps must be an array when provided"))
        steps = []

    allowed_keys = set(spec.allowed_keys) if spec is not None else set()
    required_keys = set(spec.required_keys) if spec is not None else set()

    if spec is not None:
        for key in defaults.keys():
            if not isinstance(key, str):
                issues.append(MacroAssetIssue(rel, "macro_asset.defaults.key_type", "defaults keys must be strings"))
                continue
            k = key.strip()
            if not k or k not in allowed_keys:
                issues.append(MacroAssetIssue(rel, "macro_asset.unknown_arg", f"defaults key not allowed: {k!r}"))

    seen_step_keys: set[str] = set()
    step_keys: set[str] = set()
    for idx, entry in enumerate(steps):
        if not isinstance(entry, dict):
            issues.append(MacroAssetIssue(rel, "macro_asset.steps.entry_type", f"steps[{idx}] must be an object"))
            continue
        key = entry.get("key")
        if not isinstance(key, str) or not key.strip():
            issues.append(MacroAssetIssue(rel, "macro_asset.steps.key.required", f"steps[{idx}].key required"))
            continue
        key = key.strip()
        if key in seen_step_keys:
            issues.append(MacroAssetIssue(rel, "macro_asset.steps.key.duplicate", f"duplicate steps key: {key!r}"))
            continue
        seen_step_keys.add(key)
        step_keys.add(key)

        if spec is not None and key not in allowed_keys:
            issues.append(MacroAssetIssue(rel, "macro_asset.steps.key_invalid", f"steps[{idx}].key not allowed: {key!r}"))

        kind = entry.get("kind")
        if not isinstance(kind, str) or kind.strip().lower() not in {"text", "pick"}:
            issues.append(MacroAssetIssue(rel, "macro_asset.steps.kind.invalid", f"steps[{idx}].kind must be 'text' or 'pick'"))
            continue
        kind = kind.strip().lower()

        source = entry.get("source")
        options = entry.get("options")
        if kind == "pick":
            if source is None and options is None:
                issues.append(MacroAssetIssue(rel, "macro_asset.steps.pick.missing_source", f"steps[{idx}] pick requires source or options"))
            if source is not None and not (isinstance(source, str) and source.strip()):
                issues.append(MacroAssetIssue(rel, "macro_asset.steps.pick.source_type", f"steps[{idx}].source must be non-empty string"))
            if source is not None and isinstance(source, str):
                src = source.strip()
                if src not in {"known_scenes"}:
                    issues.append(MacroAssetIssue(rel, "macro_asset.steps.pick.source_invalid", f"steps[{idx}].source invalid: {src!r}"))
            if options is not None:
                if not isinstance(options, list) or any(not isinstance(v, str) or not v.strip() for v in options):
                    issues.append(MacroAssetIssue(rel, "macro_asset.steps.pick.options_type", f"steps[{idx}].options must be array of strings"))
                else:
                    norm = [v.strip() for v in options if isinstance(v, str) and v.strip()]
                    if len(set(norm)) != len(norm):
                        issues.append(MacroAssetIssue(rel, "macro_asset.steps.pick.options_unique", f"steps[{idx}].options must be unique"))
                    if key == "anchor":
                        allowed_anchors = {"primary", "cursor", "player"}
                        bad = [v for v in norm if v not in allowed_anchors]
                        if bad:
                            issues.append(MacroAssetIssue(rel, "macro_asset.steps.pick.options_invalid", f"steps[{idx}].options invalid for anchor: {bad!r}"))
        else:
            if source is not None:
                issues.append(MacroAssetIssue(rel, "macro_asset.steps.text.no_source", f"steps[{idx}].source not allowed for text"))
            if options is not None:
                issues.append(MacroAssetIssue(rel, "macro_asset.steps.text.no_options", f"steps[{idx}].options not allowed for text"))

    if spec is not None:
        for req in required_keys:
            if req in step_keys:
                continue
            if req in defaults:
                continue
            issues.append(MacroAssetIssue(rel, "macro_asset.missing_arg", f"missing required key {req!r} (provide in defaults or steps)"))

    issues.sort(key=lambda i: (i.path, i.code, i.detail))
    return issues


def list_macros(*, pack_id: str | None = None) -> list[MacroAssetSummary]:
    summaries: list[MacroAssetSummary] = []
    for rel_path in iter_macro_paths(pack_id=pack_id):
        try:
            payload = load_macro_asset(rel_path)
        except Exception:
            continue
        summary = summarize_macro_asset(payload, rel_path=rel_path)
        if not summary.id or not summary.macro_id:
            continue
        summaries.append(summary)
    summaries.sort(key=lambda s: (s.pack_id, s.id, s.path))
    return summaries


def parse_macro_asset(payload: dict[str, Any], *, rel_path: str) -> MacroAsset:
    rel = _norm_rel_path(Path(str(rel_path)))
    pack_id = _extract_pack_id(rel)
    asset_id = str(payload.get("id") or "").strip()
    macro_id = normalize_macro_id(payload.get("macro_id"))
    defaults = payload.get("defaults", {})
    defaults = defaults if isinstance(defaults, dict) else {}
    steps = payload.get("steps", [])
    steps = steps if isinstance(steps, list) else []
    metadata = payload.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    return MacroAsset(
        pack_id=pack_id,
        id=asset_id,
        macro_id=macro_id,
        defaults=dict(defaults),
        steps=[dict(s) for s in steps if isinstance(s, dict)],
        path=rel,
        metadata=dict(metadata),
    )
