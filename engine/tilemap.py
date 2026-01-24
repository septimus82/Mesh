"""Tilemap loader that converts Tiled JSON into Arcade sprite layers."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence
import engine.optional_arcade as optional_arcade
from PIL import Image

from .assets import AssetManager
from .paths import resolve_path

FLIP_HORIZONTAL = 0x80000000
FLIP_VERTICAL = 0x40000000
FLIP_DIAGONAL = 0x20000000
FLIP_MASK = FLIP_HORIZONTAL | FLIP_VERTICAL | FLIP_DIAGONAL


@dataclass(slots=True)
class TilemapLayerConfig:
    """Normalized configuration for a scene-declared tile layer."""

    name: str
    draw: bool = True
    collision: bool = False
    z: int = -100
    parallax: float = 1.0
    collision_tag: str | None = "terrain"
    properties: dict[str, Any] = field(default_factory=dict)

    def z_bucket(self) -> str:
        return "foreground" if int(self.z) >= 0 else "background"


@dataclass(slots=True)
class TilemapDrawLayer:
    """Drawable sprite layer with deterministic metadata."""

    id: str
    z: int
    parallax: float
    sprites: optional_arcade.arcade.SpriteList


@dataclass(slots=True)
class TilemapInstance:
    """Runtime tilemap payload consumed by GameWindow."""

    background_layers: list[optional_arcade.arcade.SpriteList] = field(default_factory=list)
    foreground_layers: list[optional_arcade.arcade.SpriteList] = field(default_factory=list)
    draw_layers: list[TilemapDrawLayer] = field(default_factory=list)
    collision_sprites: optional_arcade.arcade.SpriteList = field(
        default_factory=lambda: optional_arcade.arcade.SpriteList(use_spatial_hash=True)
    )
    map_size: tuple[int, int] = (0, 0)
    tile_size: tuple[int, int] = (0, 0)
    layer_names: list[str] = field(default_factory=list)
    layer_data: dict[str, list[int]] = field(default_factory=dict)
    layer_offsets: dict[str, tuple[float, float]] = field(default_factory=dict)
    layer_dimensions: tuple[int, int] = (0, 0)
    layer_lookup: dict[str, optional_arcade.arcade.SpriteList] = field(default_factory=dict)
    tilesets: list["Tileset"] = field(default_factory=list)


@dataclass(slots=True)
class Tileset:
    """Resolved tileset metadata used for slicing textures."""

    name: str
    first_gid: int
    tile_width: int
    tile_height: int
    spacing: int
    margin: int
    columns: int
    tile_count: int
    image_path: str
    image_width: int
    image_height: int
    tile_properties: dict[int, dict[str, Any]] = field(default_factory=dict)

    def contains(self, gid: int) -> bool:
        return self.first_gid <= gid < self.first_gid + self.tile_count

    def slice_coordinates(self, local_id: int) -> tuple[int, int]:
        col = local_id % max(1, self.columns)
        row = local_id // max(1, self.columns)
        source_x = self.margin + col * (self.tile_width + self.spacing)
        source_y_top = self.margin + row * (self.tile_height + self.spacing)
        source_y = self.image_height - source_y_top - self.tile_height
        return int(source_x), int(source_y)


class TilemapManager:
    """Loads Tiled JSON and produces Arcade sprite layers."""

    def __init__(self, assets: AssetManager) -> None:
        self.assets = assets
        self._tile_texture_cache: dict[tuple[str, int, bool, bool], optional_arcade.arcade.Texture] = {}
        self._tileset_images: dict[str, Image.Image] = {}

    def load_map(
        self,
        map_path: str,
        layer_configs: Sequence[dict[str, Any]] | Sequence[TilemapLayerConfig],
        overrides: dict[str, Any] | None = None,
    ) -> TilemapInstance | None:
        path = resolve_path(map_path)
        if not path.exists():
            print(f"[Mesh][Tilemap] ERROR: Map '{map_path}' does not exist")
            return None

        try:
            payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"[Mesh][Tilemap] ERROR: Could not parse '{map_path}': {exc}")
            return None

        if str(payload.get("orientation", "")).lower() != "orthogonal":
            print(f"[Mesh][Tilemap] ERROR: Map '{map_path}' must be orthogonal")
            return None

        width = int(payload.get("width", 0))
        height = int(payload.get("height", 0))
        tile_width = int(payload.get("tilewidth", 0))
        tile_height = int(payload.get("tileheight", 0))
        if width <= 0 or height <= 0 or tile_width <= 0 or tile_height <= 0:
            print(f"[Mesh][Tilemap] ERROR: Map '{map_path}' has invalid dimensions")
            return None

        tilesets = self._load_tilesets(path.parent, payload.get("tilesets", []))
        if not tilesets:
            print(f"[Mesh][Tilemap] ERROR: Map '{map_path}' has no tilesets")
            return None

        configs = self._normalize_layer_configs(layer_configs)
        if not configs:
            print(f"[Mesh][Tilemap] WARNING: Map '{map_path}' has no matching layer configs")
            return None

        layer_lookup = {
            str(layer.get("name")): layer for layer in payload.get("layers", []) if isinstance(layer, dict)
        }
        if overrides and isinstance(overrides.get("layers"), dict):
            for lname, override_data in overrides["layers"].items():
                raw = layer_lookup.get(lname)
                if raw is not None and isinstance(override_data, list):
                    raw["data"] = override_data

        instance = TilemapInstance(
            map_size=(width, height),
            tile_size=(tile_width, tile_height),
            layer_dimensions=(width, height),
            tilesets=list(tilesets),
        )
        map_pixel_height = height * tile_height

        for config in configs:
            raw_layer = layer_lookup.get(config.name)
            if raw_layer is None:
                print(f"[Mesh][Tilemap] WARNING: Layer '{config.name}' not found in map")
                continue
            layer_type = str(raw_layer.get("type"))
            sprites = optional_arcade.arcade.SpriteList(use_spatial_hash=True)
            if layer_type == "tilelayer":
                sprites = self._build_tile_layer(
                    raw_layer,
                    tilesets,
                    tile_width,
                    tile_height,
                    map_pixel_height,
                    config,
                )
                instance.layer_data[config.name] = self._decode_layer_data(raw_layer)
                instance.layer_offsets[config.name] = (
                    float(raw_layer.get("offsetx", 0.0)),
                    float(raw_layer.get("offsety", 0.0)),
                )
            elif layer_type == "objectgroup":
                sprites = self._build_object_layer(
                    raw_layer,
                    tile_width,
                    tile_height,
                    map_pixel_height,
                    config,
                )
            else:
                print(f"[Mesh][Tilemap] WARNING: Layer '{config.name}' uses unsupported type '{layer_type}'")
                continue

            if len(sprites) == 0:
                continue

            instance.layer_names.append(config.name)
            instance.layer_lookup[config.name] = sprites

            if config.draw:
                instance.draw_layers.append(
                    TilemapDrawLayer(
                        id=config.name,
                        z=int(config.z),
                        parallax=float(config.parallax),
                        sprites=sprites,
                    )
                )

            if config.collision:
                for sprite in sprites:
                    sprite.mesh_is_solid = True  # type: ignore[attr-defined]
                    sprite.mesh_tag = config.collision_tag or "terrain"  # type: ignore[attr-defined]
                instance.collision_sprites.extend(sprite for sprite in sprites)

        instance.draw_layers = sort_tilemap_draw_layers(instance.draw_layers)
        instance.background_layers = [layer.sprites for layer in instance.draw_layers if layer.z < 0]
        instance.foreground_layers = [layer.sprites for layer in instance.draw_layers if layer.z >= 0]

        if not instance.background_layers and not instance.foreground_layers:
            print(f"[Mesh][Tilemap] WARNING: Map '{map_path}' produced no drawable layers")
        return instance

    def _normalize_layer_configs(
        self,
        configs: Sequence[dict[str, Any]] | Sequence[TilemapLayerConfig],
    ) -> list[TilemapLayerConfig]:
        normalized: list[TilemapLayerConfig] = []
        for entry in configs:
            if isinstance(entry, TilemapLayerConfig):
                normalized.append(entry)
                continue
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("id") or entry.get("name") or entry.get("layer") or "").strip()
            if not name:
                continue
            properties = entry.get("properties")
            properties_dict = dict(properties) if isinstance(properties, dict) else {}
            normalized.append(
                TilemapLayerConfig(
                    name=name,
                    draw=bool(entry.get("draw", True)),
                    collision=bool(entry.get("collision", False)),
                    z=_parse_layer_z(entry.get("z")),
                    parallax=_parse_layer_parallax(entry.get("parallax")),
                    collision_tag=entry.get("collision_tag"),
                    properties=properties_dict,
                )
            )
        return normalized

    def _load_tilesets(self, map_dir: Path, tilesets: Iterable[Any]) -> list[Tileset]:
        resolved: list[Tileset] = []
        for entry in tilesets:
            if not isinstance(entry, dict):
                continue
            first_gid = int(entry.get("firstgid", 1))
            source = entry.get("source")
            if isinstance(source, str) and source.strip():
                tileset_path = (map_dir / source).resolve()
                tileset_data = self._load_external_tileset(tileset_path)
            else:
                tileset_data = dict(entry)
                tileset_path = map_dir
            if not tileset_data:
                continue
            tileset = self._build_tileset(first_gid, tileset_data, tileset_path)
            if tileset is not None:
                resolved.append(tileset)
        resolved.sort(key=lambda ts: ts.first_gid)
        return resolved

    def _load_external_tileset(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            print(f"[Mesh][Tilemap] WARNING: Tileset '{path}' missing")
            return None
        if path.suffix.lower() == ".tsx":
            try:
                tree = ET.parse(path)
                root = tree.getroot()
            except Exception as exc:  # noqa: BLE001
                print(f"[Mesh][Tilemap] WARNING: Failed to parse TSX '{path}': {exc}")
                return None
            return self._tileset_from_tsx(root, path)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"[Mesh][Tilemap] WARNING: Failed to parse tileset '{path}': {exc}")
            return None

    def _tileset_from_tsx(self, root: ET.Element, path: Path) -> dict[str, Any]:
        image = root.find("image")
        return {
            "name": root.get("name"),
            "tilewidth": root.get("tilewidth"),
            "tileheight": root.get("tileheight"),
            "spacing": root.get("spacing"),
            "margin": root.get("margin"),
            "tilecount": root.get("tilecount"),
            "columns": root.get("columns"),
            "image": image.get("source") if image is not None else None,
            "imagewidth": image.get("width") if image is not None else None,
            "imageheight": image.get("height") if image is not None else None,
            "_base_path": str(path.parent),
        }

    def _build_tileset(self, first_gid: int, data: dict[str, Any], base_path: Path) -> Tileset | None:
        tile_width = int(data.get("tilewidth", 0))
        tile_height = int(data.get("tileheight", 0))
        image_path = data.get("image")
        image_width = int(data.get("imagewidth", 0))
        image_height = int(data.get("imageheight", 0))
        if not image_path or tile_width <= 0 or tile_height <= 0 or image_width <= 0 or image_height <= 0:
            print("[Mesh][Tilemap] WARNING: Tileset missing required fields")
            return None
        spacing = int(data.get("spacing", 0) or 0)
        margin = int(data.get("margin", 0) or 0)
        columns = int(data.get("columns", 0) or 0)
        tile_count = int(data.get("tilecount", 0) or 0)
        if columns <= 0:
            usable_width = max(0, image_width - margin * 2 + spacing)
            columns = max(1, usable_width // (tile_width + spacing) if tile_width else 1)
        if tile_count <= 0:
            rows = max(1, (image_height - margin * 2 + spacing) // (tile_height + spacing))
            tile_count = columns * rows
        source_base = Path(data.get("_base_path") or base_path)
        resolved_image = (source_base / image_path).resolve()
        per_tile_properties = {}
        tile_entries = data.get("tiles")
        if isinstance(tile_entries, list):
            for tile_entry in tile_entries:
                if not isinstance(tile_entry, dict):
                    continue
                local_id = tile_entry.get("id")
                if not isinstance(local_id, int) or local_id < 0:
                    continue
                props = self._properties_to_dict(tile_entry.get("properties"))
                if props:
                    per_tile_properties[local_id] = props

        return Tileset(
            name=str(data.get("name") or "tileset"),
            first_gid=first_gid,
            tile_width=tile_width,
            tile_height=tile_height,
            spacing=spacing,
            margin=margin,
            columns=columns,
            tile_count=tile_count,
            image_path=str(resolved_image),
            image_width=image_width,
            image_height=image_height,
            tile_properties=per_tile_properties,
        )

    def _build_tile_layer(
        self,
        layer: dict[str, Any],
        tilesets: list[Tileset],
        tile_width: int,
        tile_height: int,
        map_pixel_height: int,
        config: TilemapLayerConfig,
    ) -> optional_arcade.arcade.SpriteList:
        sprites = optional_arcade.arcade.SpriteList(use_spatial_hash=True)
        data = self._decode_layer_data(layer)
        if not data:
            return sprites
        width = int(layer.get("width", 0))
        height = int(layer.get("height", 0))
        offset_x = float(layer.get("offsetx", 0.0))
        offset_y = float(layer.get("offsety", 0.0))
        layer_properties = self._merge_properties(config.properties, self._properties_to_dict(layer.get("properties")))
        if width <= 0 or height <= 0:
            return sprites
        for index, raw_gid in enumerate(data):
            gid = int(raw_gid or 0)
            if gid == 0:
                continue
            flips = gid & FLIP_MASK
            gid &= ~FLIP_MASK
            tileset = self._find_tileset(tilesets, gid)
            if tileset is None:
                continue
            local_id = gid - tileset.first_gid
            texture = self._get_tile_texture(tileset, local_id)
            if texture is None:
                continue
            col = index % width
            row = index // width
            center_x = (col + 0.5) * tile_width + offset_x
            center_y = map_pixel_height - ((row + 0.5) * tile_height) + offset_y
            sprite = optional_arcade.arcade.Sprite()
            sprite.texture = texture
            sprite.center_x = center_x
            sprite.center_y = center_y
            sprite.scale = 1.0
            if flips:
                print("[Mesh][Tilemap] WARNING: Tile flips are not fully supported; rendering may not match Tiled")
            tile_props = tileset.tile_properties.get(local_id, {})
            properties = self._merge_properties(layer_properties, tile_props)
            self._apply_tile_metadata(sprite, properties)
            sprites.append(sprite)
        return sprites

    def _build_object_layer(
        self,
        layer: dict[str, Any],
        tile_width: int,
        tile_height: int,
        map_pixel_height: int,
        config: TilemapLayerConfig,
    ) -> optional_arcade.arcade.SpriteList:
        sprites = optional_arcade.arcade.SpriteList(use_spatial_hash=True)
        layer_properties = self._merge_properties(config.properties, self._properties_to_dict(layer.get("properties")))
        objects = layer.get("objects")
        if not isinstance(objects, list):
            return sprites
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            if obj.get("visible", True) is False:
                continue
            width = float(obj.get("width", 0.0)) or tile_width
            height = float(obj.get("height", 0.0)) or tile_height
            center_x = float(obj.get("x", 0.0)) + width / 2.0
            base_y = float(obj.get("y", 0.0))
            center_y = map_pixel_height - base_y - height / 2.0
            sprite = optional_arcade.arcade.SpriteSolidColor(int(max(1.0, width)), int(max(1.0, height)), color=(0, 0, 0, 0))
            sprite.center_x = center_x
            sprite.center_y = center_y
            obj_props = self._properties_to_dict(obj.get("properties"))
            properties = self._merge_properties(layer_properties, obj_props)
            self._apply_tile_metadata(sprite, properties)
            sprites.append(sprite)
        return sprites

    def _decode_layer_data(self, layer: dict[str, Any]) -> list[int]:
        data = layer.get("data")
        if isinstance(data, list):
            return [int(value or 0) for value in data]
        if isinstance(data, str):
            encoding = layer.get("encoding")
            compression = layer.get("compression")
            if compression:
                print("[Mesh][Tilemap] WARNING: Compressed tile layers are not supported")
                return []
            if encoding == "csv":
                numbers: list[int] = []
                for chunk in data.replace("\n", "").split(","):
                    chunk = chunk.strip()
                    if not chunk:
                        continue
                    try:
                        numbers.append(int(chunk))
                    except ValueError:
                        numbers.append(0)
                return numbers
            print("[Mesh][Tilemap] WARNING: Unsupported tile layer encoding")
            return []
        return []

    def _find_tileset(self, tilesets: list[Tileset], gid: int) -> Tileset | None:
        candidate: Tileset | None = None
        for tileset in tilesets:
            if tileset.contains(gid):
                candidate = tileset
        return candidate

    def _get_tile_texture(self, tileset: Tileset, local_id: int) -> optional_arcade.arcade.Texture | None:
        key = (tileset.image_path, local_id, False, False)
        if key in self._tile_texture_cache:
            return self._tile_texture_cache[key]
        source_x, source_y = tileset.slice_coordinates(local_id)
        source_image = self._get_tileset_image(tileset.image_path)
        if source_image is None:
            return None
        try:
            cropped = source_image.crop(
                (
                    source_x,
                    source_y,
                    source_x + tileset.tile_width,
                    source_y + tileset.tile_height,
                )
            )
            texture = optional_arcade.arcade.Texture(cropped)
        except Exception as exc:  # noqa: BLE001
            print(f"[Mesh][Tilemap] WARNING: Failed to crop tile {local_id} from '{tileset.image_path}': {exc}")
            return None
        self._tile_texture_cache[key] = texture
        return texture

    def _get_tileset_image(self, image_path: str) -> Image.Image | None:
        cached = self._tileset_images.get(image_path)
        if cached is not None:
            return cached
        try:
            resolved = resolve_path(image_path)
            with Image.open(resolved) as img:
                loaded = img.convert("RGBA")
        except Exception as exc:  # noqa: BLE001
            print(f"[Mesh][Tilemap] WARNING: Failed to load tileset image '{image_path}': {exc}")
            return None
        self._tileset_images[image_path] = loaded
        return loaded

    def clear_texture_cache(self) -> int:
        count = len(self._tile_texture_cache)
        self._tile_texture_cache.clear()
        return count

    def clear_tileset_images(self) -> int:
        count = len(self._tileset_images)
        self._tileset_images.clear()
        return count

    def _merge_properties(self, *sources: dict[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for source in sources:
            if not source:
                continue
            for key, value in source.items():
                merged[key] = value
        return merged

    def _apply_tile_metadata(self, sprite: optional_arcade.arcade.Sprite, properties: dict[str, Any]) -> None:
        if not properties:
            return
        sprite.mesh_tile_properties = dict(properties)  # type: ignore[attr-defined]
        tile_tag = properties.get("tile_tag") or properties.get("tag")
        if isinstance(tile_tag, str) and tile_tag.strip():
            sprite.mesh_tag = tile_tag.strip()  # type: ignore[attr-defined]

    def _properties_to_dict(self, raw_properties: Any) -> dict[str, Any]:
        if isinstance(raw_properties, dict):
            return dict(raw_properties)
        if isinstance(raw_properties, list):
            resolved: dict[str, Any] = {}
            for entry in raw_properties:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue
                value = entry.get("value")
                declared_type = entry.get("type")
                resolved[name.strip()] = self._coerce_property_value(declared_type, value)
            return resolved
        return {}

    def _coerce_property_value(self, declared_type: Any, value: Any) -> Any:
        if declared_type is None:
            return value
        kind = str(declared_type).lower()
        try:
            if kind == "bool":
                if isinstance(value, str):
                    return value.strip().lower() in {"true", "1", "yes", "on"}
                return bool(value)
            if kind == "int":
                return int(value)
            if kind == "float":
                return float(value)
        except (TypeError, ValueError):
            return value
        return value


def sort_tilemap_draw_layers(layers: Sequence[TilemapDrawLayer]) -> list[TilemapDrawLayer]:
    return sorted(layers, key=lambda layer: (int(layer.z), str(layer.id)))


def compute_parallax_camera_position(
    camera_position: tuple[float, float],
    parallax: float,
) -> tuple[float, float]:
    factor = float(parallax)
    return (float(camera_position[0]) * factor, float(camera_position[1]) * factor)


def _parse_layer_z(value: Any) -> int:
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"foreground", "front"}:
            return 100
        if text in {"background", "back"}:
            return -100
        try:
            return int(text)
        except ValueError:
            return -100
    return -100


def _parse_layer_parallax(value: Any) -> float:
    if value is None:
        return 1.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0
