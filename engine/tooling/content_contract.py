from __future__ import annotations

import glob
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from engine.fx_presets import FxPresetRegistry
from engine.paths import resolve_path
from engine.swallowed_exceptions import _log_swallow
from engine.tooling_runtime.pack_manifest import load_all_manifests, resolve_pack_order
from engine.logging_tools import get_logger



@dataclass(frozen=True)
class ContractError:
    file_path: str
    json_path: str
    message: str
    pack_id: str | None = None


@dataclass(frozen=True)
class ParticleEmitterRecord:
    json_path: str
    cfg: Any


@dataclass(frozen=True)
class ContentContractResult:
    ok: bool
    files_checked: int
    errors: int
    messages: list[str]


@dataclass(frozen=True)
class PrefabRefRecord:
    json_path: str
    prefab_ref: str


@dataclass(frozen=True)
class BehaviourRefRecord:
    json_path: str
    name: str


def collect_contract_files(raw_paths: list[str] | None, repo_root: Path) -> list[Path]:
    if raw_paths:
        files: list[Path] = []
        for entry in raw_paths:
            files.extend(_expand_path(entry, repo_root))
        return _unique_sorted(files, repo_root)
    return _unique_sorted(_collect_default_files(repo_root), repo_root)


def validate_content_contract(
    paths: list[Path],
    repo_root: Path,
    *,
    fx_registry: FxPresetRegistry | None = None,
    asset_registry: dict[str, Any] | None = None,
    with_prefabs: bool = False,
    with_behaviours: bool = False,
) -> list[ContractError]:
    errors: list[ContractError] = []
    pack_order = _load_pack_order() if fx_registry is None or with_prefabs else None
    registry = fx_registry or _build_fx_registry(pack_order)
    asset_paths = _asset_registry_paths(asset_registry)
    prefab_index = None
    if with_prefabs:
        prefab_index, prefab_errors = _build_prefab_index(pack_order or [], repo_root)
        errors.extend(prefab_errors)

    behaviour_lookup = None
    if with_behaviours:
        behaviour_lookup = _build_behaviour_lookup()

    for file_path in _unique_sorted(paths, repo_root):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001  # REASON: malformed content payloads should record a contract error and skip only that file
            _log_swallow("CNCT-001", "engine/tooling/content_contract.py blanket swallow", once=True)
            errors.append(
                ContractError(
                    file_path=_display_path(file_path, repo_root),
                    json_path="/",
                    message=f"failed to parse JSON: {exc}",
                    pack_id=_infer_pack_id(file_path, repo_root),
                )
            )
            continue

        context_pack_id = _infer_pack_id(file_path, repo_root)
        if with_prefabs and prefab_index is not None:
            for prefab in find_prefab_refs(payload):
                _, prefab_error = _resolve_prefab_ref(
                    prefab.prefab_ref,
                    context_pack_id=context_pack_id,
                    pack_order=pack_order or [],
                    prefab_index=prefab_index,
                )
                if prefab_error:
                    errors.append(
                        ContractError(
                            file_path=_display_path(file_path, repo_root),
                            json_path=prefab.json_path,
                            message=prefab_error,
                            pack_id=context_pack_id,
                        )
                    )
        if with_behaviours and behaviour_lookup is not None:
            for behaviour in find_behaviour_names(payload):
                if not behaviour_lookup(behaviour.name):
                    errors.append(
                        ContractError(
                            file_path=_display_path(file_path, repo_root),
                            json_path=behaviour.json_path,
                            message=f"Unknown behaviour '{behaviour.name}'",
                            pack_id=context_pack_id,
                        )
                    )
        records = find_particle_emitters(payload)
        for record in records:
            cfg = record.cfg
            json_path = record.json_path
            if not isinstance(cfg, dict):
                errors.append(
                    ContractError(
                        file_path=_display_path(file_path, repo_root),
                        json_path=json_path,
                        message="ParticleEmitter config must be an object",
                        pack_id=context_pack_id,
                    )
                )
                continue

            inline_config = dict(cfg)
            preset_name = _coerce_non_empty_str(inline_config.get("preset"))
            preset_cfg: dict[str, Any] = {}
            if preset_name is not None:
                try:
                    preset_cfg = registry.resolve(preset_name, context_pack_id=context_pack_id)
                except ValueError as exc:
                    errors.append(
                        ContractError(
                            file_path=_display_path(file_path, repo_root),
                            json_path=f"{json_path}/preset",
                            message=str(exc),
                            pack_id=context_pack_id,
                        )
                    )

            merged = dict(preset_cfg)
            for key, value in inline_config.items():
                if key == "preset":
                    continue
                merged[key] = value

            from engine.behaviours.particle_emitter import validate_particle_emitter_config

            for issue in validate_particle_emitter_config(merged, allow_preset=False):
                errors.append(
                    ContractError(
                        file_path=_display_path(file_path, repo_root),
                        json_path=json_path,
                        message=issue,
                        pack_id=context_pack_id,
                    )
                )

            sprite_path = _coerce_non_empty_str(merged.get("sprite"))
            if sprite_path is None:
                sprite_path = _coerce_non_empty_str(merged.get("sprite_path"))
            if sprite_path is not None:
                if not _sprite_exists(sprite_path, repo_root, asset_paths):
                    errors.append(
                        ContractError(
                            file_path=_display_path(file_path, repo_root),
                            json_path=f"{json_path}/sprite",
                            message=f"sprite '{sprite_path}' not found",
                            pack_id=context_pack_id,
                        )
                    )

    return sorted(errors, key=lambda err: (err.file_path, err.json_path, err.message))


def run_content_contract(
    paths: list[Path],
    repo_root: Path,
    *,
    fx_registry: FxPresetRegistry | None = None,
    asset_registry: dict[str, Any] | None = None,
    with_prefabs: bool = False,
    with_behaviours: bool = False,
) -> ContentContractResult:
    files = _unique_sorted(paths, repo_root)
    errors = validate_content_contract(
        files,
        repo_root,
        fx_registry=fx_registry,
        asset_registry=asset_registry,
        with_prefabs=with_prefabs,
        with_behaviours=with_behaviours,
    )
    if errors:
        messages = [_format_contract_error(err) for err in errors]
    else:
        messages = [f"[Mesh][Contract] OK ({len(files)} files checked)"]
    return ContentContractResult(
        ok=not errors,
        files_checked=len(files),
        errors=len(errors),
        messages=messages,
    )


def iter_json_paths(obj: Any) -> Iterable[tuple[list[Any], Any, Any]]:
    def _walk(value: Any, path: list[Any], parent: Any) -> Iterable[tuple[list[Any], Any, Any]]:
        yield path, value, parent
        if isinstance(value, dict):
            for key in sorted(value.keys(), key=lambda item: str(item)):
                yield from _walk(value[key], path + [key], value)
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                yield from _walk(item, path + [idx], value)

    return _walk(obj, [], None)


def find_particle_emitters(obj: Any) -> list[ParticleEmitterRecord]:
    records: list[ParticleEmitterRecord] = []
    seen: set[str] = set()

    for path, value, _parent in iter_json_paths(obj):
        if not isinstance(value, dict):
            continue

        behaviour_cfg = value.get("behaviour_config")
        behaviours = value.get("behaviours")
        if isinstance(behaviour_cfg, dict):
            has_emitter = False
            if isinstance(behaviours, list):
                has_emitter = any(str(entry) == "ParticleEmitter" for entry in behaviours)
            if has_emitter or "ParticleEmitter" in behaviour_cfg:
                cfg = behaviour_cfg.get("ParticleEmitter", {})
                ptr = _json_pointer(path + ["behaviour_config", "ParticleEmitter"])
                if ptr not in seen:
                    seen.add(ptr)
                    records.append(ParticleEmitterRecord(json_path=ptr, cfg=cfg))

        if "ParticleEmitter" in value and isinstance(value.get("ParticleEmitter"), dict):
            ptr = _json_pointer(path + ["ParticleEmitter"])
            if ptr not in seen:
                seen.add(ptr)
                records.append(ParticleEmitterRecord(json_path=ptr, cfg=value.get("ParticleEmitter")))

    return records


def find_prefab_refs(obj: Any) -> list[PrefabRefRecord]:
    records: list[PrefabRefRecord] = []
    seen: set[str] = set()
    for path, value, _parent in iter_json_paths(obj):
        if not isinstance(value, dict):
            continue
        for key in ("prefab_id", "prefab"):
            if key not in value:
                continue
            prefab_ref = _coerce_non_empty_str(value.get(key))
            if prefab_ref is None:
                continue
            ptr = _json_pointer(path + [key])
            if ptr in seen:
                continue
            seen.add(ptr)
            records.append(PrefabRefRecord(json_path=ptr, prefab_ref=prefab_ref))
    return records


def find_behaviour_names(obj: Any) -> list[BehaviourRefRecord]:
    records: list[BehaviourRefRecord] = []
    seen: set[str] = set()

    for path, value, _parent in iter_json_paths(obj):
        if not isinstance(value, dict):
            continue
        behaviours = value.get("behaviours")
        if isinstance(behaviours, list):
            for idx, entry in enumerate(behaviours):
                name = _extract_behaviour_name(entry)
                if name is None:
                    continue
                ptr = _json_pointer(path + ["behaviours", idx])
                if ptr in seen:
                    continue
                seen.add(ptr)
                records.append(BehaviourRefRecord(json_path=ptr, name=name))
            continue
        if isinstance(behaviours, dict):
            for key in sorted(behaviours.keys(), key=lambda item: str(item)):
                name = _coerce_non_empty_str(key)
                if name is None:
                    continue
                ptr = _json_pointer(path + ["behaviours", key])
                if ptr in seen:
                    continue
                seen.add(ptr)
                records.append(BehaviourRefRecord(json_path=ptr, name=name))
            continue
        behaviour_cfg = value.get("behaviour_config")
        if isinstance(behaviour_cfg, dict):
            for key in sorted(behaviour_cfg.keys(), key=lambda item: str(item)):
                name = _coerce_non_empty_str(key)
                if name is None:
                    continue
                ptr = _json_pointer(path + ["behaviour_config", key])
                if ptr in seen:
                    continue
                seen.add(ptr)
                records.append(BehaviourRefRecord(json_path=ptr, name=name))

    return records


def _json_pointer(path: list[Any]) -> str:
    if not path:
        return "/"
    return "/" + "/".join(_json_escape(str(part)) for part in path)


def _json_escape(text: str) -> str:
    return text.replace("~", "~0").replace("/", "~1")


def _format_contract_error(err: ContractError) -> str:
    message = err.message
    if err.pack_id:
        message = f"{message} (pack={err.pack_id})"
    return f"[Mesh][Contract] ERROR {err.file_path}:{err.json_path}: {message}"


def _expand_path(raw: str, repo_root: Path) -> list[Path]:
    text = str(raw or "").strip()
    if not text:
        return []
    base_path = Path(text)
    if not base_path.is_absolute():
        base_path = repo_root / base_path
    if _has_glob(text):
        return [Path(p) for p in glob.glob(str(base_path), recursive=True) if Path(p).is_file()]
    if base_path.is_dir():
        return [p for p in base_path.rglob("*.json") if p.is_file()]
    if base_path.is_file():
        return [base_path]
    return []


def _has_glob(text: str) -> bool:
    return any(ch in text for ch in ("*", "?", "["))


def _collect_default_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    packs_root = repo_root / "packs"
    if packs_root.exists():
        for pack_dir in sorted([p for p in packs_root.iterdir() if p.is_dir()], key=lambda p: p.name):
            scenes_dir = pack_dir / "scenes"
            if scenes_dir.exists():
                files.extend([p for p in scenes_dir.rglob("*.json") if p.is_file()])

    scenes_root = repo_root / "scenes"
    if scenes_root.exists():
        files.extend([p for p in scenes_root.rglob("*.json") if p.is_file()])

    worlds_root = repo_root / "worlds"
    if worlds_root.exists():
        files.extend([p for p in worlds_root.rglob("*.json") if p.is_file()])

    return files


def _unique_sorted(paths: Iterable[Path], repo_root: Path) -> list[Path]:
    seen: dict[str, Path] = {}
    for path in paths:
        key = _display_path(path, repo_root)
        seen[key] = path
    return [seen[key] for key in sorted(seen.keys())]


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
        return rel.as_posix()
    except Exception:
        _log_swallow("CNCT-002", "engine/tooling/content_contract.py blanket swallow", once=True)
        return path.as_posix()


def _infer_pack_id(path: Path, repo_root: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
        parts = rel.parts
    except Exception:
        _log_swallow("CNCT-003", "engine/tooling/content_contract.py blanket swallow", once=True)
        parts = path.parts
    for idx, part in enumerate(parts):
        if part.lower() == "packs" and idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def _load_pack_order() -> list[Any]:
    manifests, _ = load_all_manifests()
    order, _ = resolve_pack_order(manifests)
    return order


def _build_fx_registry(pack_order: list[Any] | None) -> FxPresetRegistry:
    if pack_order is None:
        pack_order = _load_pack_order()
    pack_roots = [manifest.root for manifest in pack_order]
    return FxPresetRegistry.from_pack_roots(pack_roots, pack_order)


@dataclass(frozen=True)
class PrefabIndex:
    ids_by_pack: dict[str, set[str]]
    pack_roots: dict[str, Path]
    root_pack_id: str | None


def _build_prefab_index(pack_order: list[Any], repo_root: Path) -> tuple[PrefabIndex, list[ContractError]]:
    errors: list[ContractError] = []
    ids_by_pack: dict[str, set[str]] = {}
    pack_roots: dict[str, Path] = {}
    root_pack_id = _find_root_pack_id(pack_order, repo_root)

    for entry in pack_order:
        pack_id = getattr(entry, "id", None)
        root = getattr(entry, "root", None)
        if isinstance(entry, dict):
            pack_id = entry.get("id", pack_id)
            root = entry.get("root", root)
        pack_id = _coerce_non_empty_str(pack_id)
        if pack_id is None or root is None:
            continue
        root_path = root if isinstance(root, Path) else Path(str(root))
        pack_roots.setdefault(pack_id, root_path)
        ids_by_pack.setdefault(pack_id, set())

    base_path = repo_root / "assets" / "prefabs.json"
    base_ids, base_error = _load_prefab_ids(base_path)
    if base_error:
        errors.append(
            ContractError(
                file_path=_display_path(base_path, repo_root),
                json_path="/",
                message=base_error,
                pack_id=root_pack_id,
            )
        )
    if base_ids:
        if root_pack_id is not None:
            ids_by_pack.setdefault(root_pack_id, set()).update(base_ids)
        else:
            ids_by_pack.setdefault("<base>", set()).update(base_ids)
            pack_roots.setdefault("<base>", repo_root)

    for pack_id, root_path in pack_roots.items():
        prefabs_path = root_path / "data" / "prefabs.json"
        ids, err = _load_prefab_ids(prefabs_path)
        if err:
            errors.append(
                ContractError(
                    file_path=_display_path(prefabs_path, repo_root),
                    json_path="/",
                    message=err,
                    pack_id=pack_id,
                )
            )
        if ids:
            ids_by_pack.setdefault(pack_id, set()).update(ids)

    return PrefabIndex(ids_by_pack=ids_by_pack, pack_roots=pack_roots, root_pack_id=root_pack_id), errors


def _load_prefab_ids(prefabs_path: Path) -> tuple[set[str], str | None]:
    if not prefabs_path.exists():
        return set(), None
    try:
        payload = json.loads(prefabs_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: malformed prefabs.json payloads should report a prefab index error and skip only that prefab file
        _log_swallow("CNCT-004", "engine/tooling/content_contract.py blanket swallow", once=True)
        return set(), f"failed to parse prefabs.json: {exc}"
    if not isinstance(payload, list):
        return set(), "prefabs.json must be a list"
    ids: set[str] = set()
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        prefab_id = _coerce_non_empty_str(entry.get("id"))
        if prefab_id is not None:
            ids.add(prefab_id)
    return ids, None


def _find_root_pack_id(pack_order: list[Any], repo_root: Path) -> str | None:
    repo_resolved = repo_root.resolve()
    for entry in pack_order:
        root = getattr(entry, "root", None)
        pack_id = getattr(entry, "id", None)
        if isinstance(entry, dict):
            root = entry.get("root", root)
            pack_id = entry.get("id", pack_id)
        if root is None:
            continue
        try:
            root_path = root if isinstance(root, Path) else Path(str(root))
            if root_path.resolve() == repo_resolved:
                return _coerce_non_empty_str(pack_id)
        except Exception:
            _log_swallow("CNCT-005", "engine/tooling/content_contract.py blanket swallow", once=True)
            continue
    return None


def _resolve_prefab_ref(
    prefab_ref: str,
    *,
    context_pack_id: str | None,
    pack_order: list[Any],
    prefab_index: PrefabIndex,
) -> tuple[str | None, str | None]:
    pack_id, prefab_id, error = _split_prefab_ref(prefab_ref)
    if error is not None:
        return None, error

    if pack_id is not None:
        if pack_id not in prefab_index.pack_roots:
            return None, f"Unknown pack id '{pack_id}' for prefab '{prefab_id}'"
        if prefab_id in prefab_index.ids_by_pack.get(pack_id, set()):
            return pack_id, None
        return None, f"Prefab '{prefab_id}' not found in pack '{pack_id}'"

    search_order: list[str] = []
    ctx = _coerce_non_empty_str(context_pack_id)
    if ctx is not None:
        search_order.append(ctx)
    for entry in pack_order:
        pack_name = getattr(entry, "id", None)
        if isinstance(entry, dict):
            pack_name = entry.get("id", pack_name)
        pack_name = _coerce_non_empty_str(pack_name)
        if pack_name is None or pack_name in search_order:
            continue
        search_order.append(pack_name)

    for candidate in search_order:
        if prefab_id in prefab_index.ids_by_pack.get(candidate, set()):
            return candidate, None

    return None, f"Unknown prefab '{prefab_id}'"


def _split_prefab_ref(prefab_ref: str) -> tuple[str | None, str, str | None]:
    raw = _coerce_non_empty_str(prefab_ref)
    if raw is None:
        return None, "", "prefab reference must be a non-empty string"
    if ":" not in raw:
        return None, raw, None
    pack_id, prefab_id = raw.split(":", 1)
    pack_id = pack_id.strip()
    prefab_id = prefab_id.strip()
    if not pack_id or not prefab_id:
        return None, raw, f"Invalid prefab reference '{raw}'"
    return pack_id, prefab_id, None


def _extract_behaviour_name(entry: Any) -> str | None:
    if isinstance(entry, str):
        return _coerce_non_empty_str(entry)
    if isinstance(entry, dict):
        for key in ("type", "name"):
            name = _coerce_non_empty_str(entry.get(key))
            if name is not None:
                return name
    return None


def _build_behaviour_lookup():
    from engine.behaviours import get_behaviour_info, load_builtin_behaviours

    load_builtin_behaviours()

    def _is_known(name: str) -> bool:
        return get_behaviour_info(name) is not None

    return _is_known


def _coerce_non_empty_str(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value if value else None


def _sprite_exists(sprite_path: str, repo_root: Path, asset_paths: set[str] | None) -> bool:
    candidate = Path(sprite_path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    if candidate.exists():
        return True
    resolved = resolve_path(sprite_path)
    if resolved.exists():
        return True
    if asset_paths is not None:
        normalized = sprite_path.replace("\\", "/")
        return normalized in asset_paths
    return False


def _asset_registry_paths(asset_registry: dict[str, Any] | None) -> set[str] | None:
    if not isinstance(asset_registry, dict):
        return None
    assets = asset_registry.get("assets")
    if not isinstance(assets, list):
        return None
    paths: set[str] = set()
    for entry in assets:
        if isinstance(entry, dict):
            path = entry.get("path")
            if isinstance(path, str) and path.strip():
                paths.add(path.replace("\\", "/"))
    return paths
