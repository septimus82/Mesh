"""FX preset registry for ParticleEmitter configuration."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

_PRESETS_REL_PATH = Path("fx") / "presets.json"


@dataclass(frozen=True)
class PresetRecord:
    pack_id: str
    preset_name: str
    preset_dict: dict[str, Any]
    file_path: Path


@dataclass(frozen=True)
class ValidationError:
    pack_id: str
    preset_name: str
    file_path: str
    message: str
    key_path: str | None = None


def load_presets_from_pack(pack_root: Path) -> dict[str, dict[str, Any]]:
    presets_path = pack_root / _PRESETS_REL_PATH
    if not presets_path.exists():
        return {}
    try:
        payload = json.loads(presets_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: malformed fx preset JSON should raise a clear ValueError without aborting fx preset loading with raw parser errors
        raise ValueError(f"{presets_path.as_posix()}: failed to parse presets.json: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{presets_path.as_posix()}: presets.json root must be an object")
    schema_version = payload.get("schema_version")
    if schema_version != 1:
        raise ValueError(f"{presets_path.as_posix()}: schema_version must be 1")
    raw_presets = payload.get("presets")
    if not isinstance(raw_presets, dict):
        raise ValueError(f"{presets_path.as_posix()}: presets must be an object")

    presets: dict[str, dict[str, Any]] = {}
    for raw_name, raw_config in raw_presets.items():
        name = _coerce_name(raw_name)
        if name is None:
            raise ValueError(f"{presets_path.as_posix()}: preset ids must be non-empty strings")
        if not isinstance(raw_config, dict):
            raise ValueError(f"{presets_path.as_posix()}: preset '{name}' must be an object")
        if name in presets:
            raise ValueError(f"{presets_path.as_posix()}: duplicate preset id '{name}'")
        presets[name] = dict(raw_config)
    return presets


def iter_all_presets(
    pack_roots: Iterable[Path],
    pack_order: Iterable[Any] | None,
) -> Iterable[PresetRecord]:
    records, _ = collect_presets_and_errors(pack_roots, pack_order)
    return records


def collect_presets_and_errors(
    pack_roots: Iterable[Path],
    pack_order: Iterable[Any] | None,
) -> tuple[list[PresetRecord], list[ValidationError]]:
    records: list[PresetRecord] = []
    errors: list[ValidationError] = []
    for pack_id, root in _collect_pack_entries(pack_roots, pack_order):
        file_path = root / _PRESETS_REL_PATH
        try:
            presets = load_presets_from_pack(root)
        except ValueError as exc:
            errors.append(
                ValidationError(
                    pack_id=pack_id,
                    preset_name="<file>",
                    file_path=file_path.as_posix(),
                    message=str(exc),
                )
            )
            continue
        for preset_name in sorted(presets.keys()):
            records.append(
                PresetRecord(
                    pack_id=pack_id,
                    preset_name=preset_name,
                    preset_dict=presets[preset_name],
                    file_path=file_path,
                )
            )
    return records, errors


def validate_all_presets(records: Iterable[PresetRecord]) -> list[ValidationError]:
    from engine.behaviours.particle_emitter import validate_particle_emitter_config

    errors: list[ValidationError] = []
    sorted_records = sorted(records, key=lambda r: (r.pack_id, r.preset_name))
    for record in sorted_records:
        issues = validate_particle_emitter_config(record.preset_dict, allow_preset=False)
        for issue in issues:
            errors.append(
                ValidationError(
                    pack_id=record.pack_id,
                    preset_name=record.preset_name,
                    file_path=record.file_path.as_posix(),
                    message=issue,
                )
            )
    return errors


class FxPresetRegistry:
    def __init__(self, pack_map: dict[str, Path], order: list[str]) -> None:
        self._pack_map = dict(pack_map)
        self._order = list(order)
        self._cache: dict[str, dict[str, dict[str, Any]]] = {}

    @classmethod
    def from_pack_roots(
        cls,
        pack_roots: Iterable[Path],
        pack_order: Iterable[Any] | None,
    ) -> "FxPresetRegistry":
        pack_map: dict[str, Path] = {}
        order: list[str] = []

        for entry in pack_order or []:
            pack_id, root = _coerce_pack_entry(entry)
            if pack_id is None or root is None:
                continue
            if pack_id not in pack_map:
                pack_map[pack_id] = root
                order.append(pack_id)

        for root in pack_roots:
            root_path = root if isinstance(root, Path) else Path(str(root))
            pack_id = root_path.name
            pack_map.setdefault(pack_id, root_path)

        missing = [pack_id for pack_id in pack_map.keys() if pack_id not in order]
        order.extend(sorted(missing))
        return cls(pack_map, order)

    def resolve(self, name: str, *, context_pack_id: str | None = None) -> dict[str, Any]:
        raw_name = _coerce_name(name)
        if raw_name is None:
            raise ValueError("preset name must be a non-empty string")
        pack_id, preset_id = _split_preset_name(raw_name)
        if pack_id is not None:
            return self._resolve_from_pack(pack_id, preset_id)

        search_order = self._build_search_order(context_pack_id)
        for candidate in search_order:
            presets = self._load_pack_presets(candidate)
            if preset_id in presets:
                return copy.deepcopy(presets[preset_id])

        raise ValueError(f"Unknown preset '{preset_id}'")

    def _resolve_from_pack(self, pack_id: str, preset_id: str) -> dict[str, Any]:
        presets = self._load_pack_presets(pack_id)
        if preset_id not in presets:
            raise ValueError(f"Unknown preset '{preset_id}' in pack '{pack_id}'")
        return copy.deepcopy(presets[preset_id])

    def _build_search_order(self, context_pack_id: str | None) -> list[str]:
        order: list[str] = []
        ctx = _coerce_name(context_pack_id)
        if ctx is not None and ctx in self._pack_map:
            order.append(ctx)
        for pack_id in self._order:
            if pack_id not in order:
                order.append(pack_id)
        return order

    def _load_pack_presets(self, pack_id: str) -> dict[str, dict[str, Any]]:
        if pack_id not in self._pack_map:
            raise ValueError(f"Unknown pack id '{pack_id}'")
        if pack_id not in self._cache:
            self._cache[pack_id] = load_presets_from_pack(self._pack_map[pack_id])
        return self._cache[pack_id]


def build_fx_preset_registry() -> FxPresetRegistry:
    from .content_packs import discover_packs
    from .paths import get_content_roots

    packs = discover_packs(get_content_roots())
    pack_roots = [pack.root for pack in packs]
    return FxPresetRegistry.from_pack_roots(pack_roots, packs)


def _coerce_pack_entry(entry: Any) -> tuple[str | None, Path | None]:
    if entry is None:
        return None, None
    pack_id = getattr(entry, "id", None)
    root = getattr(entry, "root", None)
    if isinstance(entry, dict):
        pack_id = entry.get("id", pack_id)
        root = entry.get("root", root)
    pack_id = _coerce_name(pack_id)
    if root is None:
        return pack_id, None
    root_path = root if isinstance(root, Path) else Path(str(root))
    return pack_id, root_path


def _collect_pack_entries(
    pack_roots: Iterable[Path],
    pack_order: Iterable[Any] | None,
) -> list[tuple[str, Path]]:
    pack_map: dict[str, Path] = {}
    for entry in pack_order or []:
        pack_id, root = _coerce_pack_entry(entry)
        if pack_id is None or root is None:
            continue
        pack_map.setdefault(pack_id, root)
    for root in pack_roots:
        root_path = root if isinstance(root, Path) else Path(str(root))
        pack_id = root_path.name
        pack_map.setdefault(pack_id, root_path)
    return sorted(pack_map.items(), key=lambda item: item[0])


def _split_preset_name(name: str) -> tuple[str | None, str]:
    if ":" not in name:
        return None, name
    pack_id, preset_id = name.split(":", 1)
    pack_id = pack_id.strip()
    preset_id = preset_id.strip()
    if not pack_id or not preset_id:
        raise ValueError(f"Invalid preset reference '{name}'")
    return pack_id, preset_id


def _coerce_name(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value if value else None
