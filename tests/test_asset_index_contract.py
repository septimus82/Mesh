"""Tests for Asset Index contract."""

from pathlib import Path
from engine.asset_index import scan_assets, filter_assets, AssetRow

def test_scan_assets(tmp_path):
    # Setup structure
    assets = tmp_path / "assets"
    assets.mkdir()
    
    # Create files
    (assets / "test.png").touch()
    (assets / "data.json").touch()
    (assets / "sound.wav").touch()
    (assets / "readme.txt").touch()
    
    # Subdirectory
    sub = assets / "sub"
    sub.mkdir()
    (sub / "nested.jpg").touch()
    
    # Scan
    rows = scan_assets(tmp_path)
    
    # Expect deterministic order: rel_path alphanumeric mostly if they are in same dir?
    # scan_assets walks. os.walk is topdown.
    # files sorted by casefold.
    
    # Expected order:
    # assets/data.json
    # assets/readme.txt
    # assets/sound.wav
    # assets/test.png
    # assets/sub/nested.jpg (because 'sub' is a dir, handled after files in 'assets'? No, walk yields root, dirs, files)
    
    # Wait, os.walk yields files in current dir. then recurses.
    # But I sorted os.walk! 
    # `sorted(os.walk(assets_dir, topdown=True), key=lambda t: t[0].lower())`
    # So it processes directories in order.
    # assets/ comes before assets/sub/
    
    paths = [r.rel_path for r in rows]
    expected = [
        "assets/data.json",
        "assets/readme.txt",
        "assets/sound.wav",
        "assets/test.png",
        "assets/sub/nested.jpg"
    ]
    
    # On windows separators might vary but posix was forced in implementation
    assert paths == expected
    
    # Check kinds
    kind_map = {r.display_name: r.kind for r in rows}
    assert kind_map["test.png"] == "image"
    assert kind_map["data.json"] == "json"
    assert kind_map["sound.wav"] == "audio"
    assert kind_map["readme.txt"] == "other"
    assert kind_map["nested.jpg"] == "image"

def test_filter_assets():
    rows = [
        AssetRow("assets/folder/image.png", "image", "image.png"),
        AssetRow("assets/folder/sound.wav", "audio", "sound.wav"),
        AssetRow("assets/config.json", "json", "config.json"),
    ]
    
    # Filter by text (partial match on path)
    res = filter_assets(rows, "folder")
    assert len(res) == 2
    assert res[0].display_name == "image.png"
    assert res[1].display_name == "sound.wav"
    
    # Filter by kind
    res = filter_assets(rows, "", "Audio")
    assert len(res) == 1
    assert res[0].kind == "audio"
    
    # Filter by both
    res = filter_assets(rows, "config", "Audio")
    assert len(res) == 0
    
    # Case insensitive
    res = filter_assets(rows, "IMAGE", "image")
    assert len(res) == 1
    assert res[0].display_name == "image.png"
