from __future__ import annotations

import zipfile
from pathlib import Path


def test_release_web_demo_contract(tmp_path: Path, monkeypatch) -> None:
    import tooling.release_web_demo as release_web_demo

    build_root = tmp_path / "build" / "web"
    build_root.mkdir(parents=True, exist_ok=True)
    (build_root / "index.html").write_text("<html></html>", encoding="utf-8")
    data_dir = build_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "blob.bin").write_bytes(b"\x00\x01")
    assets_dir = build_root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "asset.txt").write_text("ok", encoding="utf-8")

    (tmp_path / "web_main.py").touch()
    monkeypatch.chdir(tmp_path)

    def _fake_run(*args, **kwargs):  # noqa: ARG001
        return None

    monkeypatch.setattr(release_web_demo.subprocess, "run", _fake_run)

    zip_path = release_web_demo.build_release("web_main.py")
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path) as handle:
        names = sorted(handle.namelist())

    assert "index.html" in names
    assert "data/blob.bin" in names
    assert "assets/asset.txt" in names
    assert "README.txt" in names
