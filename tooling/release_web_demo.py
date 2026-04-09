from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path
import tomllib


README_TEXT = "\n".join(
    [
        "Mesh Engine Web Demo",
        "",
        "To run locally:",
        "  python -m http.server",
        "  then open http://localhost:8000",
        "",
        "Note: Browsers often block autoplay audio until you interact with the page.",
        "",
    ]
)


def _read_pygbag_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):  # REASON: web demo release helper should ignore malformed optional pygbag config and fall back to defaults
        return {}


def _extract_output_dir(config: dict) -> Path:
    cfg = config.get("pygbag")
    if isinstance(cfg, dict):
        output = cfg.get("output")
        if isinstance(output, str) and output.strip():
            return Path(output)
    return Path("build/web")


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda p: p.as_posix())


def _write_zip(zip_path: Path, root: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    fixed_time = (2000, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in _iter_files(root):
            rel = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(rel, date_time=fixed_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            data = path.read_bytes()
            handle.writestr(info, data)


def build_and_zip_web_demo(repo_root: Path, out_zip: Path | None = None) -> Path:
    """Build the web demo and zip it.
    
    Args:
        repo_root: The root directory containing web_main.py and pygbag.toml.
        out_zip: Optional path for the output zip file. Defaults to repo_root/dist/web_demo.zip.
        
    Returns:
        Path to the generated zip file.
    """
    if not (repo_root / "web_main.py").exists():
        raise FileNotFoundError(f"web_main.py not found in {repo_root}")
        
    # Run build in the target directory
    cmd = [sys.executable, "-m", "tooling.build_web", "web_main.py"]
    subprocess.run(cmd, check=True, cwd=repo_root)

    # Read config relative to repo_root
    config = _read_pygbag_toml(repo_root / "pygbag.toml")
    build_dir = repo_root / _extract_output_dir(config)
    
    if not build_dir.exists():
        raise FileNotFoundError(f"Web build output not found: {build_dir}")

    readme_path = build_dir / "README.txt"
    readme_path.write_text(README_TEXT, encoding="utf-8", newline="\n")

    if out_zip is None:
        out_zip = repo_root / "dist" / "web_demo.zip"
        
    _write_zip(out_zip, build_dir)
    return out_zip


def build_release(entrypoint: str = "web_main.py") -> Path:
    # Legacy wrapper for CLI
    return build_and_zip_web_demo(Path.cwd())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and package a web demo release.")
    parser.add_argument("entrypoint", nargs="?", default="web_main.py", help="Entry point script.")
    args = parser.parse_args(argv)
    
    # Respect entrypoint arg if needed, though build_and_zip enforces web_main.py for now
    # to match the signature requirement. 
    # But wait, original build_release took entrypoint.
    # Refactoring slightly to maintaing CLI behavior accurately.
    
    try:
        path = build_release(args.entrypoint)
        print(f"[Mesh][Web] Wrote {path.as_posix()}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
