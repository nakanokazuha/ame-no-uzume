import json
import struct
from collections import deque
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from yume_api.assets.models import PackManifest

REQUIRED_ANCHORS = {"ceo", "memory", "research", "work", "automation", "lobby"}
REQUIRED_ANIMATIONS = {
    "yume-idle-sw",
    "yume-walk-sw",
    "yume-think-sw",
    "yume-work-sw",
    "yume-waiting-sw",
    "yume-success-sw",
    "yume-failed-sw",
    "scheduled-idle-sw",
    "scheduled-walk-sw",
    "scheduled-work-sw",
    "scheduled-waiting-sw",
    "scheduled-failed-sw",
    "worker-idle-sw",
    "worker-walk-sw",
    "worker-work-sw",
    "worker-enter-sw",
    "worker-exit-sw",
    "worker-report-sw",
    "worker-waiting-sw",
    "worker-failed-sw",
}
REQUIRED_MAP_LAYERS = {"floor", "walls", "furniture-low", "furniture-high"}
TILE_SIZE = (64, 32)
CHARACTER_SIZE = (32, 48)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_HEADER_SIZE = 24


class AssetPackError(ValueError):
    pass


def load_and_validate_pack(root: Path) -> PackManifest:
    root = _resolved_root(root)
    manifest_path = root / "pack.json"
    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise AssetPackError(f"invalid manifest: {manifest_path} ({error})") from error

    try:
        manifest = PackManifest.model_validate_json(manifest_text)
    except ValidationError as error:
        raise AssetPackError(f"invalid manifest: pack.json ({error})") from error

    validate_asset_pack(root, manifest)
    return manifest


def validate_asset_pack(root: Path, manifest: PackManifest) -> None:
    root = _resolved_root(root)
    if (manifest.tile.width, manifest.tile.height) != TILE_SIZE:
        raise AssetPackError("tile dimensions must be 64x32")
    if (manifest.character.width, manifest.character.height) != CHARACTER_SIZE:
        raise AssetPackError("character dimensions must be 32x48")

    map_path = _asset_file(root, root, manifest.map)
    atlas_path = _asset_file(root, root, manifest.atlas)
    if manifest.ui is not None:
        _asset_file(root, root, manifest.ui.image)
        _asset_file(root, root, manifest.ui.atlas)

    missing_anchors = REQUIRED_ANCHORS - set(manifest.anchors)
    if missing_anchors:
        raise AssetPackError(f"missing semantic anchors: {sorted(missing_anchors)}")

    map_data = _read_json(root, map_path, "map")
    if map_data.get("orientation") != "isometric":
        raise AssetPackError("map orientation must be isometric")
    _validate_map(root, map_path, map_data, manifest)

    missing_animations = REQUIRED_ANIMATIONS - set(manifest.animations)
    if missing_animations:
        raise AssetPackError(f"missing animation aliases: {sorted(missing_animations)}")

    atlas_data = _read_json(root, atlas_path, "atlas")
    frames = _validate_atlas(root, atlas_path, atlas_data, manifest)
    _validate_animation_frames(manifest, frames)


def _asset_file(root: Path, base: Path, relative: str) -> Path:
    if "\x00" in relative:
        raise AssetPackError(f"invalid asset path: {relative!r}")
    try:
        relative_path = Path(relative)
        if relative_path.is_absolute():
            raise AssetPackError(f"asset path escapes pack: {relative}")
        candidate = (base / relative_path).resolve()
    except AssetPackError:
        raise
    except (OSError, RuntimeError, UnicodeError, ValueError) as error:
        raise AssetPackError(f"invalid asset path: {relative!r} ({error})") from error

    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise AssetPackError(f"asset path escapes pack: {relative}") from error

    if not candidate.is_file():
        raise AssetPackError(f"missing asset: {_pack_path(root, candidate)}")
    return candidate


def _read_json(root: Path, path: Path, kind: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AssetPackError(f"invalid {kind}: {_pack_path(root, path)} ({error})") from error

    if not isinstance(data, dict):
        raise AssetPackError(f"invalid {kind}: {_pack_path(root, path)} must be an object")
    return data


def _validate_map(
    root: Path,
    map_path: Path,
    map_data: dict[str, Any],
    manifest: PackManifest,
) -> None:
    width = _positive_int(map_data.get("width"), "map width")
    height = _positive_int(map_data.get("height"), "map height")
    if (
        map_data.get("tilewidth"),
        map_data.get("tileheight"),
    ) != (manifest.tile.width, manifest.tile.height):
        raise AssetPackError("map tile dimensions must match manifest")

    layers = map_data.get("layers")
    if not isinstance(layers, list):
        raise AssetPackError("map layers must be a list")

    layers_by_name = {
        layer["name"]: layer
        for layer in layers
        if isinstance(layer, dict) and isinstance(layer.get("name"), str)
    }
    missing_layers = REQUIRED_MAP_LAYERS - set(layers_by_name)
    if missing_layers:
        raise AssetPackError(f"missing map layers: {sorted(missing_layers)}")

    layer_data: dict[str, list[int]] = {}
    for name in REQUIRED_MAP_LAYERS:
        layer = layers_by_name[name]
        if layer.get("type") != "tilelayer":
            raise AssetPackError(f"map layer {name} must be a tile layer")
        if (layer.get("width"), layer.get("height")) != (width, height):
            raise AssetPackError(f"map layer {name} dimensions must match the map")
        layer_data[name] = _tile_data(layer.get("data"), name, width * height)

    tilesets = map_data.get("tilesets")
    if not isinstance(tilesets, list) or not tilesets:
        raise AssetPackError("map must declare at least one tileset")
    for tileset in tilesets:
        if not isinstance(tileset, dict):
            raise AssetPackError("map tileset must be an object")
        if (
            tileset.get("tilewidth"),
            tileset.get("tileheight"),
        ) != (manifest.tile.width, manifest.tile.height):
            raise AssetPackError("tileset tile dimensions must match manifest")
        image = tileset.get("image")
        if not isinstance(image, str):
            raise AssetPackError("tileset image must be a path")
        image_path = _asset_file(root, map_path.parent, image)
        image_width, image_height = _png_dimensions(root, image_path)
        if (tileset.get("imagewidth"), tileset.get("imageheight")) != (
            image_width,
            image_height,
        ):
            raise AssetPackError("tileset image dimensions do not match its PNG")

    _validate_walkability(manifest, layer_data["floor"], width, height)


def _tile_data(value: Any, name: str, expected_length: int) -> list[int]:
    if not isinstance(value, list) or len(value) != expected_length:
        raise AssetPackError(f"map layer {name} must contain {expected_length} tiles")
    if any(type(tile) is not int for tile in value):
        raise AssetPackError(f"map layer {name} contains a non-integer tile")
    return value


def _validate_walkability(
    manifest: PackManifest,
    floor: list[int],
    width: int,
    height: int,
) -> None:
    anchor_indices: dict[str, int] = {}
    for name in REQUIRED_ANCHORS:
        anchor = manifest.anchors[name]
        if anchor.x >= width or anchor.y >= height:
            raise AssetPackError(f"anchor {name} is outside the map")
        index = anchor.y * width + anchor.x
        if floor[index] <= 0:
            raise AssetPackError(f"anchor {name} is not walkable")
        anchor_indices[name] = index

    lobby_index = anchor_indices["lobby"]
    reachable = {lobby_index}
    pending = deque([lobby_index])
    while pending:
        index = pending.popleft()
        x = index % width
        y = index // width
        for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not 0 <= next_x < width or not 0 <= next_y < height:
                continue
            next_index = next_y * width + next_x
            if floor[next_index] > 0 and next_index not in reachable:
                reachable.add(next_index)
                pending.append(next_index)

    unreachable = sorted(name for name, index in anchor_indices.items() if index not in reachable)
    if unreachable:
        raise AssetPackError(f"unreachable semantic anchors: {unreachable}")


def _validate_atlas(
    root: Path,
    atlas_path: Path,
    atlas_data: dict[str, Any],
    manifest: PackManifest,
) -> dict[str, Any]:
    meta = atlas_data.get("meta")
    if not isinstance(meta, dict) or not isinstance(meta.get("image"), str):
        raise AssetPackError("atlas meta.image must be a path")
    image_path = _asset_file(root, atlas_path.parent, meta["image"])
    image_width, image_height = _png_dimensions(root, image_path)

    frames = atlas_data.get("frames")
    if not isinstance(frames, dict) or not frames:
        raise AssetPackError("atlas frames must be a non-empty object")
    for name, frame_data in frames.items():
        if not isinstance(name, str) or not isinstance(frame_data, dict):
            raise AssetPackError("atlas frame entries must be named objects")
        frame = frame_data.get("frame")
        if not isinstance(frame, dict):
            raise AssetPackError(f"atlas frame {name} has no frame rectangle")
        x = _non_negative_int(frame.get("x"), f"atlas frame {name} x")
        y = _non_negative_int(frame.get("y"), f"atlas frame {name} y")
        width = _positive_int(frame.get("w"), f"atlas frame {name} width")
        height = _positive_int(frame.get("h"), f"atlas frame {name} height")
        if x + width > image_width or y + height > image_height:
            raise AssetPackError(f"atlas frame {name} is outside atlas image")

        source_size = frame_data.get("sourceSize")
        if not isinstance(source_size, dict) or (
            source_size.get("w"),
            source_size.get("h"),
        ) != (manifest.character.width, manifest.character.height):
            raise AssetPackError(f"atlas frame {name} source size must match character dimensions")
    return frames


def _validate_animation_frames(manifest: PackManifest, frames: dict[str, Any]) -> None:
    for animation, frame_indexes in manifest.animations.items():
        if not frame_indexes:
            raise AssetPackError(f"animation {animation} has no frames")
        for frame_index in frame_indexes:
            if f"frame-{frame_index}" not in frames:
                raise AssetPackError(
                    f"animation {animation} references missing frame-{frame_index}"
                )


def _png_dimensions(root: Path, path: Path) -> tuple[int, int]:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise AssetPackError(f"invalid PNG: {_pack_path(root, path)} ({error})") from error
    if len(data) < PNG_HEADER_SIZE or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise AssetPackError(f"invalid PNG: {_pack_path(root, path)}")
    width, height = struct.unpack(">II", data[16:PNG_HEADER_SIZE])
    if width == 0 or height == 0:
        raise AssetPackError(f"invalid PNG dimensions: {_pack_path(root, path)}")
    return width, height


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise AssetPackError(f"{label} must be a positive integer")
    return value


def _non_negative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise AssetPackError(f"{label} must be a non-negative integer")
    return value


def _pack_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _resolved_root(root: Path) -> Path:
    try:
        return root.resolve()
    except (OSError, RuntimeError, UnicodeError, ValueError) as error:
        raise AssetPackError(f"invalid asset pack root: {root!r} ({error})") from error
