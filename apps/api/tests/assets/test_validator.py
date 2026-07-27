import json
from pathlib import Path
from shutil import copytree

import pytest
from yume_api.assets.validator import AssetPackError, load_and_validate_pack


def copy_placeholder_pack(tmp_path: Path) -> Path:
    root = tmp_path / "placeholder"
    copytree(Path("asset-packs/placeholder"), root)
    return root


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_placeholder_pack_is_valid() -> None:
    manifest = load_and_validate_pack(Path("asset-packs/placeholder"))

    assert manifest.tile.width == 64
    assert set(manifest.anchors) == {
        "ceo",
        "memory",
        "research",
        "work",
        "automation",
        "lobby",
    }


def test_missing_atlas_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "maps").mkdir()
    (tmp_path / "maps" / "office.json").write_text(
        '{"orientation":"isometric"}', encoding="utf-8"
    )
    (tmp_path / "pack.json").write_text(
        '{"schema_version":1,"id":"test","name":"Test",'
        '"tile":{"width":64,"height":32},'
        '"character":{"width":32,"height":48},'
        '"map":"maps/office.json","atlas":"atlases/missing.json",'
        '"anchors":{},"animations":{}}',
        encoding="utf-8",
    )

    with pytest.raises(AssetPackError, match="atlases/missing.json"):
        load_and_validate_pack(tmp_path)


def test_missing_semantic_anchor_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "maps").mkdir()
    (tmp_path / "atlases").mkdir()
    (tmp_path / "maps" / "office.json").write_text(
        '{"orientation":"isometric"}', encoding="utf-8"
    )
    (tmp_path / "atlases" / "characters.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pack.json").write_text(
        '{"schema_version":1,"id":"test","name":"Test",'
        '"tile":{"width":64,"height":32},'
        '"character":{"width":32,"height":48},'
        '"map":"maps/office.json","atlas":"atlases/characters.json",'
        '"anchors":{"ceo":{"x":0,"y":0}},"animations":{}}',
        encoding="utf-8",
    )

    with pytest.raises(AssetPackError, match="missing semantic anchors"):
        load_and_validate_pack(tmp_path)


def test_non_isometric_map_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "maps").mkdir()
    (tmp_path / "atlases").mkdir()
    (tmp_path / "maps" / "office.json").write_text(
        '{"orientation":"orthogonal"}', encoding="utf-8"
    )
    (tmp_path / "atlases" / "characters.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pack.json").write_text(
        '{"schema_version":1,"id":"test","name":"Test",'
        '"tile":{"width":64,"height":32},'
        '"character":{"width":32,"height":48},'
        '"map":"maps/office.json","atlas":"atlases/characters.json",'
        '"anchors":{"ceo":{"x":0,"y":0},"memory":{"x":0,"y":0},'
        '"research":{"x":0,"y":0},"work":{"x":0,"y":0},'
        '"automation":{"x":0,"y":0},"lobby":{"x":0,"y":0}},'
        '"animations":{}}',
        encoding="utf-8",
    )

    with pytest.raises(AssetPackError, match="map orientation must be isometric"):
        load_and_validate_pack(tmp_path)


def test_asset_path_outside_pack_is_rejected(tmp_path: Path) -> None:
    root = copy_placeholder_pack(tmp_path)
    manifest_path = root / "pack.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["map"] = "../outside-map.json"
    write_json(manifest_path, manifest)
    write_json(tmp_path / "outside-map.json", {"orientation": "isometric"})

    with pytest.raises(AssetPackError, match="path escapes pack"):
        load_and_validate_pack(root)


def test_missing_required_animation_is_rejected(tmp_path: Path) -> None:
    root = copy_placeholder_pack(tmp_path)
    manifest_path = root / "pack.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["animations"]["worker-failed-sw"]
    write_json(manifest_path, manifest)

    with pytest.raises(AssetPackError, match="missing animation aliases"):
        load_and_validate_pack(root)


def test_shared_tile_contract_is_required(tmp_path: Path) -> None:
    root = copy_placeholder_pack(tmp_path)
    manifest_path = root / "pack.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tile"] = {"width": 32, "height": 16}
    write_json(manifest_path, manifest)

    with pytest.raises(AssetPackError, match="tile dimensions must be 64x32"):
        load_and_validate_pack(root)


def test_shared_character_contract_is_required(tmp_path: Path) -> None:
    root = copy_placeholder_pack(tmp_path)
    manifest_path = root / "pack.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["character"] = {"width": 64, "height": 48}
    write_json(manifest_path, manifest)

    with pytest.raises(AssetPackError, match="character dimensions must be 32x48"):
        load_and_validate_pack(root)


def test_missing_atlas_image_is_rejected(tmp_path: Path) -> None:
    root = copy_placeholder_pack(tmp_path)
    atlas_path = root / "atlases" / "characters.json"
    atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
    atlas["meta"]["image"] = "missing.png"
    write_json(atlas_path, atlas)

    with pytest.raises(AssetPackError, match="atlases/missing.png"):
        load_and_validate_pack(root)


def test_atlas_image_outside_pack_is_rejected(tmp_path: Path) -> None:
    root = copy_placeholder_pack(tmp_path)
    atlas_path = root / "atlases" / "characters.json"
    atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
    atlas["meta"]["image"] = "../../outside.png"
    write_json(atlas_path, atlas)

    with pytest.raises(AssetPackError, match="path escapes pack"):
        load_and_validate_pack(root)


def test_animation_frame_missing_from_atlas_is_rejected(tmp_path: Path) -> None:
    root = copy_placeholder_pack(tmp_path)
    manifest_path = root / "pack.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["animations"]["worker-failed-sw"] = [99]
    write_json(manifest_path, manifest)

    with pytest.raises(AssetPackError, match="worker-failed-sw.*frame-99"):
        load_and_validate_pack(root)


def test_atlas_frame_outside_image_is_rejected(tmp_path: Path) -> None:
    root = copy_placeholder_pack(tmp_path)
    atlas_path = root / "atlases" / "characters.json"
    atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
    atlas["frames"]["frame-0"]["frame"]["w"] = 993
    write_json(atlas_path, atlas)

    with pytest.raises(AssetPackError, match="frame-0.*outside atlas image"):
        load_and_validate_pack(root)


def test_map_tile_size_must_match_manifest(tmp_path: Path) -> None:
    root = copy_placeholder_pack(tmp_path)
    map_path = root / "maps" / "office.json"
    map_data = json.loads(map_path.read_text(encoding="utf-8"))
    map_data["tilewidth"] = 32
    write_json(map_path, map_data)

    with pytest.raises(AssetPackError, match="map tile dimensions must match manifest"):
        load_and_validate_pack(root)


def test_missing_required_map_layer_is_rejected(tmp_path: Path) -> None:
    root = copy_placeholder_pack(tmp_path)
    map_path = root / "maps" / "office.json"
    map_data = json.loads(map_path.read_text(encoding="utf-8"))
    map_data["layers"] = [
        layer for layer in map_data["layers"] if layer["name"] != "furniture-high"
    ]
    write_json(map_path, map_data)

    with pytest.raises(AssetPackError, match="missing map layers"):
        load_and_validate_pack(root)


def test_tileset_image_outside_pack_is_rejected(tmp_path: Path) -> None:
    root = copy_placeholder_pack(tmp_path)
    map_path = root / "maps" / "office.json"
    map_data = json.loads(map_path.read_text(encoding="utf-8"))
    map_data["tilesets"][0]["image"] = "../../outside.png"
    write_json(map_path, map_data)

    with pytest.raises(AssetPackError, match="path escapes pack"):
        load_and_validate_pack(root)


def test_anchor_on_unwalkable_tile_is_rejected(tmp_path: Path) -> None:
    root = copy_placeholder_pack(tmp_path)
    map_path = root / "maps" / "office.json"
    map_data = json.loads(map_path.read_text(encoding="utf-8"))
    map_data["layers"][0]["data"][44] = 0
    write_json(map_path, map_data)

    with pytest.raises(AssetPackError, match="anchor lobby is not walkable"):
        load_and_validate_pack(root)


def test_unreachable_semantic_anchor_is_rejected(tmp_path: Path) -> None:
    root = copy_placeholder_pack(tmp_path)
    map_path = root / "maps" / "office.json"
    map_data = json.loads(map_path.read_text(encoding="utf-8"))
    floor = map_data["layers"][0]["data"]
    floor[:] = [0] * 144
    for x, y in [(2, 7), (3, 3), (8, 3), (9, 7), (3, 10), (8, 10)]:
        floor[y * 12 + x] = 1
    write_json(map_path, map_data)

    with pytest.raises(AssetPackError, match="unreachable semantic anchors"):
        load_and_validate_pack(root)


def test_invalid_manifest_is_reported_as_asset_pack_error(tmp_path: Path) -> None:
    (tmp_path / "pack.json").write_text("{", encoding="utf-8")

    with pytest.raises(AssetPackError, match="invalid manifest"):
        load_and_validate_pack(tmp_path)
