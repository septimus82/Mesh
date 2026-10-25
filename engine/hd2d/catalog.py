"""A project's HD-2D structure catalogue (Milestone 16 Stage 5B): the Blender models it has imported, and the one
place that writes model files into a project.

Models live in ``assets/models/<id>.glb``, their preview pictures in ``assets/models/previews/<id>.png``, and what
the project knows about them in ``assets/models/catalog.json``::

    {"schema_version": 1, "models": [{"id": "cottage", "model": "assets/models/cottage.glb", "name": "Cottage",
      "category": "Buildings", "preview": "assets/models/previews/cottage.png", "scale": 1.0, "rotation": 0.0,
      "pixels": "sharp", "collision": {"solid": 1, "floor": 0, "wall": 4}, "floors": ["col_floor"],
      "notes": "", "license": "", "source": {"file": "...", "sha256": "...", "imported": "...Z"}}]}

Only ``id`` and ``model`` are required in an entry. A .glb in the project without an entry (every model from before
Stage 5B) is listed too, with defaults, and works as it always did: scenes name a model by its path
(``settings.hd2d.structures[].model``), so the catalogue only adds names, pictures and provenance, never a new way
of placing. Placed copies share the one file.

Writing is staged: every file an import or reimport writes goes beside its target under a temporary name, is
checked, and only then replaces the target; a failure part-way restores whatever was replaced and removes what was
new, so a project is never left half-imported.
"""

from __future__ import annotations

import datetime
import hashlib
import io
import json
import os
import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.hd2d.glb import COLLISION_KINDS, GlbError, Model, Report, contained, inspect_glb, load_glb, sharpen_textures
from engine.hd2d.settings import Hd2dSettingsError, asset_path

MODELS_DIR = "assets/models"
PREVIEWS_DIR = "assets/models/previews"
CATALOG = "assets/models/catalog.json"
SCHEMA_VERSION = 1
UNCATALOGUED = "Uncatalogued"
_TEXT_FIELDS = ("name", "category", "notes", "license")
_SKIP_DIRS = ("artifacts", "exports")


class CatalogError(ValueError):
    """An import, reimport or catalogue edit was refused; the message says why, for people and AIs."""


@dataclass
class ModelAsset:
    id: str
    model: str  # project-relative .glb
    name: str
    category: str = ""
    preview: str | None = None
    scale: float = 1.0
    rotation: float = 0.0
    pixels: str = "sharp"  # "sharp": textures sampled nearest; "as exported": as Blender wrote them
    collision: dict[str, int] = field(default_factory=dict)
    floors: list[str] = field(default_factory=list)
    notes: str = ""
    license: str = ""
    source: dict[str, Any] = field(default_factory=dict)
    catalogued: bool = True
    missing: bool = False  # the catalogue names a file that isn't there

    def as_dict(self) -> dict[str, Any]:
        """The listing an AI tool or a person reads (``read_project``'s ``models``)."""
        return {"id": self.id, "model": self.model, "name": self.name, "category": self.category or UNCATALOGUED,
                "scale": self.scale, "rotation": self.rotation, "collision": self.collision, "floors": self.floors,
                "notes": self.notes, "license": self.license, "catalogued": self.catalogued, "missing": self.missing}


# ------------------------------------------------------------------------------------------------- reading
def _read_catalog(root: Path) -> dict[str, Any]:
    path = root / CATALOG
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "models": []}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CatalogError(f"{CATALOG} can't be read ({exc}); fix or remove it.") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("models", []), list):
        raise CatalogError(f"{CATALOG} must be an object with a list of models.")
    doc.setdefault("models", [])
    return doc


def _number(entry: dict[str, Any], key: str, default: float) -> float:
    value = entry.get(key, default)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _asset(root: Path, entry: dict[str, Any]) -> ModelAsset | None:
    sid, model = entry.get("id"), entry.get("model")
    if not isinstance(sid, str) or not sid or not isinstance(model, str):
        return None
    try:
        model = asset_path(model, "model")
    except Hd2dSettingsError:
        return None
    raw_collision, raw_source = entry.get("collision"), entry.get("source")
    collision: dict[str, Any] = raw_collision if isinstance(raw_collision, dict) else {}
    source: dict[str, Any] = raw_source if isinstance(raw_source, dict) else {}
    return ModelAsset(
        sid, model, str(entry.get("name") or posixpath.splitext(posixpath.basename(model))[0]),
        str(entry.get("category") or ""), entry.get("preview") if isinstance(entry.get("preview"), str) else None,
        _number(entry, "scale", 1.0), _number(entry, "rotation", 0.0), str(entry.get("pixels") or "sharp"),
        {k: int(v) for k, v in collision.items() if k in COLLISION_KINDS and isinstance(v, int)},
        [str(f) for f in entry.get("floors", []) if isinstance(f, str)] if isinstance(entry.get("floors"), list) else [],
        str(entry.get("notes") or ""), str(entry.get("license") or ""), source,
        missing=not (root / model).is_file())


def glb_files(root: str | Path) -> list[str]:
    """Every .glb in the project (project-relative), outside dot-folders and build output."""
    base = Path(root)
    found = []
    for path in sorted(base.rglob("*.glb")):
        parts = path.relative_to(base).parts
        if not any(p.startswith(".") or p in _SKIP_DIRS for p in parts):
            found.append(path.relative_to(base).as_posix())
    return found


def assets(root: str | Path) -> list[ModelAsset]:
    """The catalogue's models, then any other .glb in the project (uncatalogued, with defaults), by name."""
    base = Path(root)
    listed: list[ModelAsset] = []
    for entry in _read_catalog(base)["models"]:
        asset = _asset(base, entry) if isinstance(entry, dict) else None
        if asset is not None and all(a.id != asset.id for a in listed):
            listed.append(asset)
    known = {a.model for a in listed}
    for rel in glb_files(base):
        if rel not in known:
            stem = posixpath.splitext(posixpath.basename(rel))[0]
            listed.append(ModelAsset(_unique_id(stem, {a.id for a in listed}), rel, stem.replace("_", " ").title(),
                                     catalogued=False))
    return sorted(listed, key=lambda a: (a.category or "~", a.name.lower(), a.id))


def find(root: str | Path, ref: str) -> ModelAsset | None:
    """A model by catalogue id or by project-relative path."""
    norm = str(ref).strip().replace("\\", "/")
    return next((a for a in assets(root) if a.id == norm or a.model == norm), None)


# ------------------------------------------------------------------------------------------------- checking
@dataclass
class Inspection:
    """What importing ``source`` would do, before anything is written."""

    source: Path
    report: Report | None = None
    model: Model | None = None
    problem: str | None = None  # why it can't be imported (None: it can)
    sharpened: list[str] = field(default_factory=list)  # materials whose texture "Keep pixels sharp" fixes
    duplicate_of: str | None = None  # an asset already imported from the same bytes
    asset_id: str = ""  # the id it would get

    @property
    def ok(self) -> bool:
        return self.problem is None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unique_id(name: str, taken: set[str]) -> str:
    from engine.project_ops import slug  # noqa: PLC0415

    base = slug(name) or "model"
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}_{n}", n + 1
    return candidate


def _taken_ids(root: Path) -> set[str]:
    """Ids no new model may take: the catalogue's, and every file name already in assets/models."""
    taken = {a.id for a in assets(root) if a.catalogued}
    folder = root / MODELS_DIR
    if folder.is_dir():
        taken |= {p.stem for p in folder.iterdir() if p.suffix.lower() in (".glb", ".gltf", ".bin")}
    return taken


def _source_path(source: str | Path) -> Path:
    return Path(str(source).strip().strip('"'))


def inspect_source(root: str | Path, source: str | Path, *, name: str = "", pixels: str = "sharp") -> Inspection:
    """Check a .glb before importing it: readable by Mesh's reader, what it holds, what it would be called."""
    base, path = Path(root), _source_path(source)
    found = Inspection(path)
    if not str(source).strip():
        found.problem = "Choose a .glb file exported from Blender (File > Export > glTF 2.0, format glTF Binary)."
        return found
    if path.suffix.lower() == ".gltf":
        found.problem = "That's a .gltf (separate files). Export as glTF Binary (.glb) so everything is in one file."
        return found
    if path.suffix.lower() != ".glb":
        found.problem = f"{path.name} isn't a .glb file (export from Blender as glTF Binary)."
        return found
    if not path.is_file():
        found.problem = f"There is no file at {path}."
        return found
    try:
        found.model, found.report = inspect_glb(path)
        data = path.read_bytes()
        if pixels == "sharp":
            _data, found.sharpened = sharpen_textures(data)
    except (GlbError, OSError) as exc:
        found.problem = str(exc)
        return found
    sha = _sha(data)
    found.duplicate_of = next((a.id for a in assets(base) if a.source.get("sha256") == sha and not a.missing), None)
    found.asset_id = _unique_id(name or path.stem, _taken_ids(base))
    return found


# ------------------------------------------------------------------------------------------------- writing
def _commit(root: Path, writes: dict[str, bytes]) -> None:
    """Write every file in ``writes`` (project-relative -> bytes) or none of them."""
    staged: dict[str, Path] = {}
    replaced: dict[str, bytes] = {}
    created: list[str] = []
    try:
        for rel, data in writes.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(f".{target.name}.mesh-staged")
            temp.write_bytes(data)
            staged[rel] = temp
        for rel, temp in staged.items():
            if rel.endswith(".glb"):
                load_glb(temp)  # what was written is what the game will read
        for rel, temp in staged.items():
            target = root / rel
            if target.is_file():
                replaced[rel] = target.read_bytes()
            else:
                created.append(rel)
            os.replace(temp, target)
    except BaseException:
        for rel, data in replaced.items():
            (root / rel).write_bytes(data)
        for rel in created:
            (root / rel).unlink(missing_ok=True)
        raise
    finally:
        for temp in staged.values():
            temp.unlink(missing_ok=True)


def _catalog_bytes(doc: dict[str, Any]) -> bytes:
    return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _preview_bytes(model: Model) -> bytes:
    from engine.hd2d.thumbnail import render  # noqa: PLC0415

    out = io.BytesIO()
    render(model).save(out, format="PNG")
    return out.getvalue()


def _check_destination(root: Path, rel: str) -> str:
    try:
        rel = asset_path(rel, "The model's place in the project")
    except Hd2dSettingsError as err:
        raise CatalogError(str(err)) from err
    if not contained(root, posixpath.dirname(rel) or "."):
        raise CatalogError(f"{posixpath.dirname(rel)} leads outside the project (a link?); models must stay inside it.")
    return rel


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _entry_facts(report: Report) -> dict[str, Any]:
    return {"collision": report.collision, "floors": report.floors}


def import_model(root: str | Path, source: str | Path, *, name: str = "", category: str = "", notes: str = "",
                 license: str = "", pixels: str = "sharp") -> ModelAsset:
    """Copy a Blender .glb into the project's model catalogue (``assets/models/<id>.glb``) with its preview, and
    return it. Refused (nothing written) if Mesh can't read it, it is already imported, or the place is unsafe.
    A .glb already inside the project is catalogued where it is, not copied."""
    base = Path(root)
    found = inspect_source(base, source, name=name, pixels=pixels)
    if found.problem or found.model is None or found.report is None:
        raise CatalogError(found.problem or "It can't be imported.")
    if found.duplicate_of:
        raise CatalogError(f"{found.source.name} is already imported, as '{found.duplicate_of}'.")
    original = found.source.read_bytes()
    data = sharpen_textures(original)[0] if pixels == "sharp" else original
    try:
        inside = found.source.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        inside = None
    if inside is not None and find(base, inside) is not None and find(base, inside).catalogued:  # type: ignore[union-attr]
        raise CatalogError(f"{inside} is already in the catalogue.")
    asset_id = found.asset_id
    rel = _check_destination(base, inside or f"{MODELS_DIR}/{asset_id}.glb")
    if inside is None and (base / rel).exists():
        raise CatalogError(f"{rel} already exists; it won't be overwritten.")  # _taken_ids should prevent this
    preview = f"{PREVIEWS_DIR}/{asset_id}.png"
    doc = _read_catalog(base)
    entry = {"id": asset_id, "model": rel, "name": (name or found.source.stem.replace("_", " ").title()).strip(),
             "category": category.strip(), "preview": preview, "scale": 1.0, "rotation": 0.0, "pixels": pixels,
             **_entry_facts(found.report), "notes": notes.strip(), "license": license.strip(),
             "source": {"file": str(found.source), "sha256": _sha(original), "imported": _now(),
                        **({"sharpened": found.sharpened} if found.sharpened and pixels == "sharp" else {})}}
    doc["models"] = [*doc["models"], entry]
    writes = {preview: _preview_bytes(found.model), CATALOG: _catalog_bytes(doc)}
    if inside is None or data != original:
        writes[rel] = data
    _commit(base, writes)
    asset = find(base, asset_id)
    assert asset is not None
    return asset


def set_properties(root: str | Path, ref: str, **fields: Any) -> ModelAsset:
    """Change a model's name, category, notes, licence, default ``scale`` or ``rotation`` (degrees). An
    uncatalogued model gets an entry (its file stays where it is)."""
    base = Path(root)
    asset = find(base, ref)
    if asset is None:
        raise CatalogError(f"There is no model '{ref}' in this project.")
    unknown = set(fields) - {*_TEXT_FIELDS, "scale", "rotation"}
    if unknown:
        raise CatalogError(f"Unknown model properties: {', '.join(sorted(unknown))}.")
    doc = _read_catalog(base)
    entry = next((e for e in doc["models"] if isinstance(e, dict) and e.get("id") == asset.id), None)
    if entry is None:
        entry = {"id": asset.id, "model": asset.model, "name": asset.name}
        doc["models"].append(entry)
    for key, value in fields.items():
        if key in ("scale", "rotation"):
            if isinstance(value, str):
                try:
                    value = float(value)
                except ValueError as exc:
                    raise CatalogError(f"The default {key} must be a number (got {value!r}).") from exc
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not value == value or abs(value) == float("inf"):
                raise CatalogError(f"The default {key} must be a finite number (got {value!r}).")
            if key == "scale" and not 0.01 <= value <= 100:
                raise CatalogError("The default scale must be between 0.01 and 100.")
            entry[key] = round(float(value) % 360.0 if key == "rotation" else float(value), 2)
        else:
            entry[key] = str(value).strip()
    _commit(base, {CATALOG: _catalog_bytes(doc)})
    updated = find(base, asset.id)
    assert updated is not None
    return updated


# ------------------------------------------------------------------------------------------------- reimport
@dataclass
class Reimport:
    """What reimporting a model changes, worked out before anything is written."""

    asset: ModelAsset
    inspection: Inspection
    changes: list[str] = field(default_factory=list)  # geometry, collision and floor changes
    warnings: list[str] = field(default_factory=list)  # characters or navigation the new shape affects

    @property
    def ok(self) -> bool:
        return self.inspection.ok


def _collider_changes(old: Model, new: Model) -> list[str]:
    before = {c.node: c for c in old.colliders}
    after = {c.node: c for c in new.colliders}
    lines = []
    for node in sorted(after.keys() - before.keys()):
        lines.append(f"New {after[node].kind} collider '{node}'.")
    for node in sorted(before.keys() - after.keys()):
        lines.append(f"Collider '{node}' ({before[node].kind}) is gone.")
    for node in sorted(before.keys() & after.keys()):
        a, b = before[node], after[node]
        if a.kind != b.kind:
            lines.append(f"Collider '{node}' was {a.kind}, now {b.kind}.")
        elif any(abs(p - q) > 0.01 for p, q in zip(a.lo + a.hi, b.lo + b.hi)):
            lines.append(f"Collider '{node}' ({b.kind}) changed shape.")
    return lines


def impact(root: str | Path, rooms: dict[str, dict[str, Any]], model_rel: str, old: Model, new: Model) -> list[str]:
    """Where swapping ``old`` for ``new`` matters in ``rooms`` (key -> scene): characters that stood validly and
    no longer would, walkable ground lost, floors that disappear from rooms using it."""
    import dataclasses  # noqa: PLC0415

    from engine.hd2d import world as hd2d_world  # noqa: PLC0415
    from engine.hd2d.settings import PIXELS_PER_METRE, parse_hd2d  # noqa: PLC0415

    base = Path(root)
    others: dict[str, Model | None] = {}
    lines: list[str] = []
    for key, scene in rooms.items():
        settings = scene.get("settings") or {}
        try:
            hd2d = parse_hd2d(settings.get("hd2d")) if settings.get("hd2d") is not None else None
        except Hd2dSettingsError:
            continue
        if hd2d is None or all(st.model != model_rel for st in hd2d.structures):
            continue
        for st in hd2d.structures:  # the room's other models count for collision too
            if st.model != model_rel and st.model not in others:
                try:
                    others[st.model] = load_glb(base / st.model) if contained(base, st.model) else None
                except GlbError:
                    others[st.model] = None
        usable = {m: others[m] for m in others if others[m] is not None}
        kept = tuple(st for st in hd2d.structures if st.model == model_rel or st.model in usable)
        room = dataclasses.replace(hd2d, structures=kept)
        world_old = hd2d_world.World(room, {**usable, model_rel: old})  # type: ignore[dict-item]
        world_new = hd2d_world.World(room, {**usable, model_rel: new})  # type: ignore[dict-item]
        users = [st.id for st in kept if st.model == model_rel]
        hw, hh = hd2d_world.NAV_HALF
        for entity in scene.get("entities", []):
            if not isinstance(entity, dict):
                continue
            try:
                x, y = float(entity.get("x", 0)) / PIXELS_PER_METRE, float(entity.get("y", 0)) / PIXELS_PER_METRE
                z = float(entity.get("elevation", 0) or 0) / PIXELS_PER_METRE
            except (TypeError, ValueError):
                continue
            if world_old.stand(x, y, z, hw, hh) is not None and world_new.stand(x, y, z, hw, hh) is None:
                who = entity.get("name") or entity.get("id") or "a character"
                lines.append(f"Room '{key}': {who} at ({x:.1f} m, {y:.1f} m) would have nowhere to stand (inside a "
                             f"wall now, or off a floor); move it after reimporting.")
        spots_old, spots_new = world_old.walkable(), world_new.walkable()
        if spots_new < spots_old:
            lines.append(f"Room '{key}': walkable ground around {', '.join(users)} shrinks ({spots_old} -> {spots_new} "
                         f"spots of {hd2d_world.NAV_CELL} m); check characters' routes.")
        lost = sorted({c.node for c in old.colliders if c.kind != "wall"} - {c.node for c in new.colliders if c.kind != "wall"})
        if lost:
            lines.append(f"Room '{key}': floors {', '.join(f'{u}/{n}' for u in users for n in lost)} no longer exist.")
    return lines


def plan_reimport(root: str | Path, ref: str, source: str | Path | None = None, *,
                  rooms: dict[str, dict[str, Any]] | None = None) -> Reimport:
    """Check a reimport of model ``ref`` from ``source`` (default: where it was imported from) and say what it
    would change. Writes nothing."""
    base = Path(root)
    asset = find(base, ref)
    if asset is None:
        raise CatalogError(f"There is no model '{ref}' in this project.")
    src = source if source is not None and str(source).strip() else asset.source.get("file", "")
    found = inspect_source(base, src, name=asset.id, pixels=asset.pixels)
    plan = Reimport(asset, found)
    if not found.ok or found.model is None:
        return plan
    found.duplicate_of = None  # the same bytes again is a valid (no-op) reimport
    try:
        old = load_glb(base / asset.model)
    except GlbError:
        old = None  # the current file is broken or missing: the reimport is the repair
    if old is None:
        plan.changes.append("The current file can't be read; the reimport replaces it.")
        return plan
    lo0, hi0 = old.bounds()
    lo1, hi1 = found.model.bounds()
    size0 = tuple(h - lo for lo, h in zip(lo0, hi0))
    size1 = tuple(h - lo for lo, h in zip(lo1, hi1))
    if any(abs(a - b) > 0.01 for a, b in zip(size0, size1)):
        plan.changes.append("Size {:.1f} x {:.1f} x {:.1f} m -> {:.1f} x {:.1f} x {:.1f} m.".format(*size0, *size1))
    tris0 = sum(len(p.indices) // 3 for p in old.parts)
    tris1 = sum(len(p.indices) // 3 for p in found.model.parts)
    if tris0 != tris1:
        plan.changes.append(f"{tris0} -> {tris1} triangles.")
    plan.changes += _collider_changes(old, found.model)
    if not plan.changes:
        plan.changes.append("Same shape and collision (textures or materials may differ).")
    plan.warnings = impact(base, rooms or {}, asset.model, old, found.model)
    return plan


def reimport_model(root: str | Path, ref: str, source: str | Path | None = None, *,
                   rooms: dict[str, dict[str, Any]] | None = None) -> Reimport:
    """Replace model ``ref``'s file with a new export (``source``; default: where it was imported from), keeping
    its id, path and every placed copy (scenes aren't touched). The model, its preview and the catalogue change
    together or not at all. Returns what changed."""
    base = Path(root)
    plan = plan_reimport(base, ref, source, rooms=rooms)
    found, asset = plan.inspection, plan.asset
    if not found.ok or found.model is None or found.report is None:
        raise CatalogError(found.problem or "It can't be reimported.")
    original = found.source.read_bytes()
    data = sharpen_textures(original)[0] if asset.pixels == "sharp" else original
    rel = _check_destination(base, asset.model)
    doc = _read_catalog(base)
    entry = next((e for e in doc["models"] if isinstance(e, dict) and e.get("id") == asset.id), None)
    if entry is None:  # an uncatalogued model gets its entry now
        entry = {"id": asset.id, "model": rel, "name": asset.name}
        doc["models"].append(entry)
    preview = str(entry["preview"]) if isinstance(entry.get("preview"), str) else f"{PREVIEWS_DIR}/{asset.id}.png"
    entry.update({"preview": preview, **_entry_facts(found.report),
                  "source": {"file": str(found.source), "sha256": _sha(original), "imported": _now(),
                             **({"sharpened": found.sharpened} if found.sharpened and asset.pixels == "sharp" else {})}})
    _commit(base, {rel: data, _check_destination(base, preview): _preview_bytes(found.model), CATALOG: _catalog_bytes(doc)})
    plan.asset = find(base, asset.id) or asset
    return plan
