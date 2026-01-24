from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
import tomllib


def _read_pygbag_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _extract_output_dir(config: dict) -> str | None:
    cfg = config.get("pygbag")
    if isinstance(cfg, dict):
        output = cfg.get("output")
        if isinstance(output, str) and output.strip():
            return output
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a WebAssembly bundle via pygbag.")
    parser.add_argument("entrypoint", nargs="?", default="web_main.py", help="Entry point script.")
    parser.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="Extra argument passed through to pygbag (repeatable).",
    )
    args = parser.parse_args(argv)

    pygbag_toml = Path("pygbag.toml")
    config = _read_pygbag_toml(pygbag_toml)
    output_dir = _extract_output_dir(config)
    if pygbag_toml.exists():
        print(f"[Mesh][Web] Using {pygbag_toml.as_posix()}")
    if output_dir:
        print(f"[Mesh][Web] Output directory: {output_dir}")

    cmd = [sys.executable, "-m", "pygbag", args.entrypoint]
    cmd.extend(args.extra_arg)
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
