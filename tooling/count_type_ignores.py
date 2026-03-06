from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_TYPE_IGNORE_RE = re.compile(r"#\s*type:\s*ignore(?:\[[^\]]+\])?")


def _iter_python_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(path for path in root.rglob("*.py") if path.is_file())
    return sorted(files, key=lambda path: path.as_posix())


def _scan_file(path: Path) -> dict[str, Any] | None:
    line_numbers: list[int] = []
    for index, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if _TYPE_IGNORE_RE.search(line):
            line_numbers.append(index)
    if not line_numbers:
        return None
    return {
        "file": path.as_posix(),
        "count": len(line_numbers),
        "line_numbers": line_numbers,
    }


def _build_report(roots: list[Path], *, top_n: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in _iter_python_files(roots):
        row = _scan_file(path)
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda row: row["file"])
    top_offenders = sorted(rows, key=lambda row: (-int(row["count"]), row["file"]))[:top_n]
    return {
        "schema_version": 1,
        "roots": [root.as_posix() for root in roots],
        "total_files_with_ignores": len(rows),
        "total_ignores": int(sum(int(row["count"]) for row in rows)),
        "top_n": top_n,
        "top_offenders": top_offenders,
        "results": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Count # type: ignore usage.")
    parser.add_argument("--roots", nargs="*", default=["engine", "mesh_cli"], help="Roots to scan")
    parser.add_argument("--top-n", type=int, default=10, help="Top offender count")
    parser.add_argument(
        "--out",
        default="artifacts/type_ignore_inventory.json",
        help="Output JSON artifact path",
    )
    args = parser.parse_args(argv)

    top_n = max(0, int(args.top_n))
    roots = [Path(root) for root in args.roots]
    payload = _build_report(roots, top_n=top_n)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for row in payload["top_offenders"]:
        print(f"{row['count']}\t{row['file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
